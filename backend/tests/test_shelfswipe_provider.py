import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch, MagicMock
import httpx
import pytest

from app.db.models.shelfswipe import SSSeller, SSShop, SSProduct, SSExtractionJob
from app.services.shelfswipe.channel3_client import (
    Channel3Client,
    Channel3ClientError,
    Channel3RateLimitError,
    Channel3TimeoutError,
)
from app.services.shelfswipe.channel3_provider import (
    Channel3CatalogProvider,
    Channel3NoProductsError,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "channel3"


def load_fixture(name: str):
    with open(FIXTURES_DIR / f"{name}.json", "r", encoding="utf-8") as f:
        return json.load(f)


# =========================================================
# Part 1: Channel3Client Unit Tests (with MockTransport)
# =========================================================

def test_channel3_client_plain_json():
    def handler(request: httpx.Request):
        req_data = json.loads(request.content)
        if req_data.get("method") == "initialize":
            return httpx.Response(
                200,
                headers={"Mcp-Session-Id": "sess-123", "Content-Type": "application/json"},
                json={"jsonrpc": "2.0", "id": req_data.get("id"), "result": {"protocolVersion": "2024-11-05"}},
            )
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            json={"jsonrpc": "2.0", "id": req_data.get("id"), "result": {"structuredContent": {"products": [{"id": "p1"}]}}},
        )

    transport = httpx.MockTransport(handler)
    client = Channel3Client(base_url="https://mock.channel3/mcp", transport=transport)
    res = client.call_tool("lookup_catalog", {"catalog": {"urls": ["https://example.com/p1"]}})
    assert res == {"products": [{"id": "p1"}]}
    assert client.session_id == "sess-123"


def test_channel3_client_sse_stream():
    def handler(request: httpx.Request):
        sse_text = (
            "event: message\n"
            "data: {\"jsonrpc\": \"2.0\", \"id\": 1, \"result\": {\"structuredContent\": {\"products\": [{\"id\": \"p_sse\"}]}}}\n\n"
            "data: [DONE]\n\n"
        )
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            text=sse_text,
        )

    transport = httpx.MockTransport(handler)
    client = Channel3Client(base_url="https://mock.channel3/mcp", transport=transport)
    client.session_id = "existing-sess"
    res = client.call_tool("lookup_catalog", {"catalog": {}})
    assert res == {"products": [{"id": "p_sse"}]}


def test_channel3_client_rate_limit_429():
    def handler(request: httpx.Request):
        return httpx.Response(429, headers={"Retry-After": "30"}, text="Too Many Requests")

    transport = httpx.MockTransport(handler)
    client = Channel3Client(base_url="https://mock.channel3/mcp", transport=transport)
    with pytest.raises(Channel3RateLimitError) as exc_info:
        client.call_tool("search_catalog", {})
    assert "429" in str(exc_info.value)
    assert "30s" in str(exc_info.value)


def test_channel3_client_error_response():
    def handler(request: httpx.Request):
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            json={"jsonrpc": "2.0", "id": 1, "error": {"code": -32600, "message": "Invalid Request"}},
        )

    transport = httpx.MockTransport(handler)
    client = Channel3Client(base_url="https://mock.channel3/mcp", transport=transport)
    client.session_id = "s"
    with pytest.raises(Channel3ClientError) as exc_info:
        client.call_tool("test", {})
    assert "Invalid Request" in str(exc_info.value)


# =========================================================
# Part 2: Channel3CatalogProvider Unit Tests
# =========================================================

def test_channel3_provider_maps_fixture_found():
    found_data = load_fixture("lookup_found")
    mock_client = MagicMock()
    mock_client.call_tool.return_value = found_data

    provider = Channel3CatalogProvider(client=mock_client)
    catalog = provider.fetch_catalog(
        shop_url="https://carlyleavenue.com",
        product_urls=["https://buy.trychannel3.com/UA9jdyJ-ZPZn-public_ucp?o=01M20JKFBC4T375JY8878TRVBY"],
    )

    assert catalog.source == "channel3"
    assert catalog.source_domain == "carlyleavenue.com"
    assert catalog.shop_name == "Carlyle Avenue"
    assert len(catalog.products) == 1

    p = catalog.products[0]
    assert p.id == "01M245A4XE96D5P54JV8EHGFD3"
    assert p.name == "Nagai Handmade Ceramic Mug"
    # Price was 5600 cents -> 56.00 USD
    assert p.price == Decimal("56.00")
    assert p.currency == "USD"
    assert p.source == "channel3"
    assert p.source_url == "https://buy.trychannel3.com/UA9jdyJ-ZPZn-public_ucp?o=01M20JKFBC4T375JY8878TRVBY"
    assert p.image_url == "https://cdn.trychannel3.com/28abd181-fc15-438c-b141-95f6148d7afc"
    assert p.stock == 0


def test_channel3_provider_raises_on_not_found():
    not_found_data = load_fixture("lookup_not_found")
    mock_client = MagicMock()
    mock_client.call_tool.return_value = not_found_data

    provider = Channel3CatalogProvider(client=mock_client)
    with pytest.raises(Channel3NoProductsError):
        provider.fetch_catalog(
            shop_url="https://carlyleavenue.com",
            product_urls=["https://carlyleavenue.com/products/missing"],
        )


# =========================================================
# Part 3: API Endpoints (Onboard, Edit, Approve) Tests
# =========================================================

def test_onboard_channel3_requires_ownership_attestation(client):
    res = client.post(
        "/api/v1/shelfswipe/sellers/onboard",
        json={
            "shop_url": "https://carlyleavenue.com",
            "consent": True,
            "provider": "channel3",
            "ownership_attested": False,
        },
    )
    assert res.status_code == 400
    assert "ownership attestation is required" in res.json()["detail"].lower()


def test_onboard_channel3_requires_http_url(client):
    res = client.post(
        "/api/v1/shelfswipe/sellers/onboard",
        json={
            "shop_url": "shelfswipe://fixtures/not_real",
            "consent": True,
            "provider": "channel3",
            "ownership_attested": True,
        },
    )
    assert res.status_code == 400
    assert "http or https" in res.json()["detail"].lower()


@patch("app.api.routes.shelfswipe.Channel3CatalogProvider")
def test_onboard_channel3_success(mock_provider_cls, client, db_session):
    found_data = load_fixture("lookup_found")
    mock_provider_instance = MagicMock()
    mock_provider_cls.return_value = mock_provider_instance

    real_provider = Channel3CatalogProvider(client=MagicMock())
    with patch.object(real_provider.client, "call_tool", return_value=found_data):
        mock_provider_instance.fetch_catalog.side_effect = real_provider.fetch_catalog

        res = client.post(
            "/api/v1/shelfswipe/sellers/onboard",
            json={
                "shop_url": "https://carlyleavenue.com",
                "consent": True,
                "provider": "channel3",
                "ownership_attested": True,
                "product_urls": ["https://buy.trychannel3.com/sample"],
            },
        )
        assert res.status_code == 201
        data = res.json()
        assert data["products_created"] == 1

        seller_id = data["seller_id"]
        shop_id = data["shop_id"]

        # Verify shop is NOT demo
        shop = db_session.query(SSShop).filter(SSShop.id == shop_id).first()
        assert shop.is_demo is False
        assert shop.source_domain == "carlyleavenue.com"

        # Verify product created
        prod = db_session.query(SSProduct).filter(SSProduct.shop_id == shop_id).first()
        assert prod.source == "channel3"
        assert prod.price == Decimal("56.00")
        assert "confirm_stock" in prod.review_flags
        assert "stock_unknown" in prod.review_flags

        # Check draft endpoint
        draft_res = client.get(f"/api/v1/shelfswipe/sellers/{seller_id}/draft")
        assert draft_res.status_code == 200
        draft_data = draft_res.json()
        assert draft_data["is_demo"] is False
        assert draft_data["products"][0]["data_source"] == "channel3"


def test_product_patch_and_recompute_flags(client, db_session):
    # Setup seller, shop, and product with review flags
    seller = SSSeller(name="Edit Merchant", source_url="https://edit-test.com")
    db_session.add(seller)
    db_session.flush()

    shop = SSShop(seller_id=seller.id, name="Edit Shop", is_demo=False)
    db_session.add(shop)
    db_session.flush()

    prod = SSProduct(
        shop_id=shop.id,
        external_id="edit-prod-1",
        name="Rough Draft Item",
        price=Decimal("0.00"),  # invalid_price flag
        currency="USD",
        image_url=None,         # missing_image flag
        description="",         # missing_description flag
        category="Misc",
        tags=[],                # no_tags flag
        stock=0,
        status="draft",
        source="channel3",
        review_flags=["missing_image", "missing_description", "no_tags", "invalid_price", "confirm_stock", "stock_unknown"],
    )
    db_session.add(prod)
    db_session.commit()

    # 1. Negative price validation
    err_res = client.patch(
        f"/api/v1/shelfswipe/sellers/{seller.id}/products/{prod.id}",
        json={"price": -5.00},
    )
    assert err_res.status_code == 422

    # 2. Patch valid price, image, description, tags
    patch_res = client.patch(
        f"/api/v1/shelfswipe/sellers/{seller.id}/products/{prod.id}",
        json={
            "name": "Polished Handcrafted Bowl",
            "price": 34.50,
            "image_url": "https://images.example.com/bowl.jpg",
            "description": "A beautiful handmade ceramic bowl.",
            "tags": ["bowl", "ceramic"],
        },
    )
    assert patch_res.status_code == 200
    updated_prod = patch_res.json()
    assert updated_prod["name"] == "Polished Handcrafted Bowl"
    assert updated_prod["price"] == 34.50
    # Flags missing_image, missing_description, no_tags, invalid_price must be removed!
    flags = updated_prod["review_flags"]
    assert "missing_image" not in flags
    assert "missing_description" not in flags
    assert "no_tags" not in flags
    assert "invalid_price" not in flags
    assert "confirm_stock" in flags


def test_shop_patch_location_and_notes(client, db_session):
    seller = SSSeller(name="Shop Edit Merchant", source_url="https://shop-edit.com")
    db_session.add(seller)
    db_session.flush()

    shop = SSShop(seller_id=seller.id, name="Shop To Edit", is_demo=False)
    db_session.add(shop)
    db_session.commit()

    # Invalid latitude > 90
    err_res = client.patch(
        f"/api/v1/shelfswipe/sellers/{seller.id}/shop",
        json={"latitude": 120.0},
    )
    assert err_res.status_code == 422

    # Valid patch
    patch_res = client.patch(
        f"/api/v1/shelfswipe/sellers/{seller.id}/shop",
        json={
            "latitude": 37.7891,
            "longitude": -122.4014,
            "pickup_notes": "Curbside pickup on weekdays 10am-4pm",
        },
    )
    assert patch_res.status_code == 200
    shop_data = patch_res.json()
    assert shop_data["latitude"] == 37.7891
    assert shop_data["longitude"] == -122.4014
    assert shop_data["pickup_notes"] == "Curbside pickup on weekdays 10am-4pm"


def test_batch_approve_flow(client, db_session):
    seller = SSSeller(name="Approve Merchant", source_url="https://approve-test.com")
    db_session.add(seller)
    db_session.flush()

    shop = SSShop(seller_id=seller.id, name="Approve Shop", is_demo=False)
    db_session.add(shop)
    db_session.flush()

    # Product 1: Valid draft product
    p1 = SSProduct(
        shop_id=shop.id,
        external_id="p1",
        name="Valid Mug",
        price=Decimal("20.00"),
        description="Great mug",
        category="Home",
        stock=0,
        status="draft",
        review_flags=["confirm_stock"],
    )
    # Product 2: Invalid price draft product
    p2 = SSProduct(
        shop_id=shop.id,
        external_id="p2",
        name="Free item",
        price=Decimal("0.00"),
        description="Invalid price item",
        category="Home",
        stock=0,
        status="draft",
        review_flags=["invalid_price", "confirm_stock"],
    )
    # Product 3: Already live product
    p3 = SSProduct(
        shop_id=shop.id,
        external_id="p3",
        name="Live Vase",
        price=Decimal("50.00"),
        description="Already live",
        category="Home",
        stock=5,
        status="live",
        review_flags=[],
    )
    db_session.add_all([p1, p2, p3])
    db_session.commit()

    # Approve request
    res = client.post(
        f"/api/v1/shelfswipe/sellers/{seller.id}/approve",
        json={
            "items": [
                {"product_id": str(p1.id), "confirmed_stock": 12},
                {"product_id": str(p2.id), "confirmed_stock": 5},
                {"product_id": str(p3.id), "confirmed_stock": 10},
                {"product_id": "nonexistent-id", "confirmed_stock": 1},
            ]
        },
    )
    assert res.status_code == 200
    data = res.json()

    assert str(p1.id) in data["approved"]
    rejections = {item["id"]: item["reason"] for item in data["rejected"]}
    assert rejections[str(p2.id)] == "invalid_price"
    assert rejections[str(p3.id)] == "already_live"
    assert rejections["nonexistent-id"] == "not_found"

    # p1 should now be live, stock=12, confirm_stock removed
    db_session.refresh(p1)
    assert p1.status == "live"
    assert p1.stock == 12
    assert "confirm_stock" not in p1.review_flags

    # still_draft_count should be 1 (p2 is still draft)
    assert data["still_draft_count"] == 1

    # Idempotent re-approval: approving p1 again rejects with already_live
    res2 = client.post(
        f"/api/v1/shelfswipe/sellers/{seller.id}/approve",
        json={"items": [{"product_id": str(p1.id), "confirmed_stock": 15}]},
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert len(data2["approved"]) == 0
    assert data2["rejected"][0]["id"] == str(p1.id)
    assert data2["rejected"][0]["reason"] == "already_live"


def test_approve_removes_stock_unknown_flag(client, db_session):
    seller = SSSeller(name="Stock Test Merchant", source_url="https://stock-unknown-test.com")
    db_session.add(seller)
    db_session.flush()

    shop = SSShop(seller_id=seller.id, name="Stock Test Shop", is_demo=False)
    db_session.add(shop)
    db_session.flush()

    p = SSProduct(
        shop_id=shop.id,
        external_id="channel3-stock-item",
        name="Channel3 Product",
        price=Decimal("45.00"),
        description="Nice item",
        category="Apparel",
        stock=0,
        status="draft",
        review_flags=["confirm_stock", "stock_unknown"],
    )
    db_session.add(p)
    db_session.commit()

    res = client.post(
        f"/api/v1/shelfswipe/sellers/{seller.id}/approve",
        json={"items": [{"product_id": str(p.id), "confirmed_stock": 7}]},
    )
    assert res.status_code == 200
    assert str(p.id) in res.json()["approved"]

    db_session.refresh(p)
    assert p.status == "live"
    assert p.stock == 7
    assert "confirm_stock" not in p.review_flags
    assert "stock_unknown" not in p.review_flags


def test_manual_product_entry_and_validation(client, db_session):
    seller = SSSeller(name="Manual Merchant", source_url="https://manual-entry.com")
    db_session.add(seller)
    db_session.flush()

    shop = SSShop(seller_id=seller.id, name="Manual Shop", is_demo=False)
    db_session.add(shop)
    db_session.flush()

    # 1. 404 for unknown seller
    res_404 = client.post(
        "/api/v1/shelfswipe/sellers/nonexistent-seller/products",
        json={"name": "Handmade Bowl", "price": 25.00, "stock": 5},
    )
    assert res_404.status_code == 404

    # 2. Validation error for negative price
    res_invalid_price = client.post(
        f"/api/v1/shelfswipe/sellers/{seller.id}/products",
        json={"name": "Handmade Bowl", "price": -5.00, "stock": 5},
    )
    assert res_invalid_price.status_code == 422

    # 3. Successful manual product entry
    res_ok = client.post(
        f"/api/v1/shelfswipe/sellers/{seller.id}/products",
        json={
            "name": "Hand-carved Wooden Spoon",
            "price": 18.50,
            "description": "Locally carved maple wood spoon.",
            "category": "Kitchen",
            "tags": ["wooden", "handmade"],
            "image_url": "https://example.com/spoon.jpg",
            "stock": 4,
        },
    )
    assert res_ok.status_code == 201
    data = res_ok.json()
    assert data["name"] == "Hand-carved Wooden Spoon"
    assert data["price"] == 18.50
    assert data["data_source"] == "manual"
    assert data["status"] == "draft"
    assert data["external_id"].startswith("manual-")
    # Should have confirm_stock flag
    assert "confirm_stock" in data["review_flags"]
    assert "invalid_price" not in data["review_flags"]
    assert "missing_image" not in data["review_flags"]

    # 4. Product with missing image and 0 price flags
    res_flags = client.post(
        f"/api/v1/shelfswipe/sellers/{seller.id}/products",
        json={
            "name": "Free Sample",
            "price": 0.00,
            "description": "",
            "tags": [],
            "stock": 0,
        },
    )
    assert res_flags.status_code == 201
    flags = res_flags.json()["review_flags"]
    assert "confirm_stock" in flags
    assert "missing_image" in flags
    assert "missing_description" in flags
    assert "no_tags" in flags
    assert "invalid_price" in flags


def test_get_seller_draft_status_filtering(client, db_session):
    seller = SSSeller(name="Filter Merchant", source_url="https://filter-test.com")
    db_session.add(seller)
    db_session.flush()

    shop = SSShop(seller_id=seller.id, name="Filter Shop", is_demo=False)
    db_session.add(shop)
    db_session.flush()

    p_draft = SSProduct(
        shop_id=shop.id,
        external_id="prod-draft",
        name="Draft Product",
        price=Decimal("15.00"),
        description="Draft item",
        category="Home",
        stock=0,
        status="draft",
    )
    p_live = SSProduct(
        shop_id=shop.id,
        external_id="prod-live",
        name="Live Product",
        price=Decimal("30.00"),
        description="Live item",
        category="Home",
        stock=10,
        status="live",
    )
    db_session.add_all([p_draft, p_live])
    db_session.commit()

    # Default (draft)
    res_default = client.get(f"/api/v1/shelfswipe/sellers/{seller.id}/draft")
    assert res_default.status_code == 200
    ids_default = [p["external_id"] for p in res_default.json()["products"]]
    assert ids_default == ["prod-draft"]

    # Explicit ?status=draft
    res_draft = client.get(f"/api/v1/shelfswipe/sellers/{seller.id}/draft?status=draft")
    assert res_draft.status_code == 200
    ids_draft = [p["external_id"] for p in res_draft.json()["products"]]
    assert ids_draft == ["prod-draft"]

    # Explicit ?status=live
    res_live = client.get(f"/api/v1/shelfswipe/sellers/{seller.id}/draft?status=live")
    assert res_live.status_code == 200
    ids_live = [p["external_id"] for p in res_live.json()["products"]]
    assert ids_live == ["prod-live"]

    # Explicit ?status=all
    res_all = client.get(f"/api/v1/shelfswipe/sellers/{seller.id}/draft?status=all")
    assert res_all.status_code == 200
    ids_all = [p["external_id"] for p in res_all.json()["products"]]
    assert set(ids_all) == {"prod-draft", "prod-live"}


def test_channel3_store_search_flow_and_compact_job_summary(db_session):
    from app.services.shelfswipe.importer import import_shop

    # Mock Channel3 search_catalog tool call with website_ids filter & pagination
    mock_client = MagicMock()

    page1_data = {
        "products": [
            {
                "id": "prod-1",
                "title": "Matcha Whisk",
                "description": {"plain": "Bamboo whisk"},
                "category": "Tea",
                "options": [{"name": "Size"}],
                "variants": [
                    {
                        "id": "var-1",
                        "seller": {"domain": "aprikamatcha.com", "name": "Aprika Matcha"},
                        "price": {"amount": 2500, "currency": "usd"},
                        "url": "https://aprikamatcha.com/products/whisk",
                        "media": [{"url": "https://cdn.example.com/whisk.jpg", "type": "image"}],
                    }
                ],
            },
            {
                "id": "prod-2-skip",
                "title": "Other Seller Mug",
                "variants": [
                    {
                        "id": "var-2",
                        "seller": {"domain": "diffseller.com", "name": "Diff Seller"},
                        "price": {"amount": 1500, "currency": "usd"},
                    }
                ],
            },
        ],
        "pagination": {"has_next_page": False, "cursor": None},
    }

    mock_client.call_tool.return_value = page1_data

    provider = Channel3CatalogProvider(client=mock_client)
    res = import_shop(
        db=db_session,
        shop_url="https://aprikamatcha.com",
        consent=True,
        seller_name="Aprika Matcha",
        provider=provider,
        product_urls=None,
    )

    assert res.products_created == 1
    assert res.products_skipped == 1  # prod-2-skip skipped due to seller domain mismatch

    # Verify extraction job raw_result is compact summary (not full catalog payload)
    job = db_session.query(SSExtractionJob).filter(SSExtractionJob.id == res.job_id).first()
    assert job is not None
    assert job.status == "succeeded"
    assert "total_products_extracted" in job.raw_result
    assert job.raw_result["total_products_extracted"] == 1
    assert job.raw_result["products_created"] == 1
    assert job.raw_result["products_skipped"] == 1
    assert job.raw_result["provider_refs"] == ["var-1"]
    assert "products" not in job.raw_result  # compact summary, not full catalog payload!



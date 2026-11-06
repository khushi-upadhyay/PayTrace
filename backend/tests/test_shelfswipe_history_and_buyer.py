from decimal import Decimal

from app.db.models.shelfswipe import SSSeller, SSShop, SSProduct


def _make_shop(db_session, shop_name, source_url, is_demo=False):
    seller = SSSeller(name=f"{shop_name} Merchant", source_url=source_url)
    db_session.add(seller)
    db_session.flush()

    shop = SSShop(seller_id=seller.id, name=shop_name, is_demo=is_demo)
    db_session.add(shop)
    db_session.flush()
    return seller, shop


def _make_product(db_session, shop, name, status="draft", price="10.00", stock=5, category="General"):
    prod = SSProduct(
        shop_id=shop.id,
        external_id=f"ext-{name}",
        name=name,
        price=Decimal(price),
        description=f"{name} description",
        category=category,
        stock=stock,
        status=status,
        review_flags=[] if status == "live" else ["confirm_stock"],
    )
    db_session.add(prod)
    db_session.flush()
    return prod


def test_list_sellers_reflects_onboarded_shops_with_counts(client, db_session):
    seller1, shop1 = _make_shop(db_session, "Aprika", "https://aprika-test.com")
    _make_product(db_session, shop1, "Matcha Bowl", status="draft")
    _make_product(db_session, shop1, "Matcha Whisk", status="live")

    seller2, shop2 = _make_shop(db_session, "GreenHome", "https://greenhome-test.com", is_demo=True)
    _make_product(db_session, shop2, "Planter", status="draft")
    db_session.commit()

    res = client.get("/api/v1/shelfswipe/sellers")
    assert res.status_code == 200
    data = res.json()

    by_url = {s["source_url"]: s for s in data["sellers"]}
    assert by_url["https://aprika-test.com"]["draft_count"] == 1
    assert by_url["https://aprika-test.com"]["live_count"] == 1
    assert by_url["https://greenhome-test.com"]["draft_count"] == 1
    assert by_url["https://greenhome-test.com"]["is_demo"] is True
    assert data["total_shops"] == 2
    assert data["total_live_products"] == 1


def test_list_all_products_spans_multiple_shops(client, db_session):
    seller1, shop1 = _make_shop(db_session, "ShopA", "https://shopa-test.com")
    p1 = _make_product(db_session, shop1, "Item A1", status="draft")

    seller2, shop2 = _make_shop(db_session, "ShopB", "https://shopb-test.com")
    p2 = _make_product(db_session, shop2, "Item B1", status="draft")
    db_session.commit()

    res = client.get("/api/v1/shelfswipe/products", params={"status": "draft"})
    assert res.status_code == 200
    data = res.json()

    ids_to_shop = {item["id"]: item["shop_name"] for item in data["products"]}
    assert ids_to_shop[str(p1.id)] == "ShopA"
    assert ids_to_shop[str(p2.id)] == "ShopB"
    assert data["total_matches"] == 2


def test_buyer_deck_only_returns_live_products_and_respects_shop_filter(client, db_session):
    seller1, shop1 = _make_shop(db_session, "LiveShop", "https://liveshop-test.com")
    live_prod = _make_product(db_session, shop1, "Live Candle", status="live")
    _make_product(db_session, shop1, "Draft Candle", status="draft")

    seller2, shop2 = _make_shop(db_session, "OtherShop", "https://othershop-test.com")
    other_live = _make_product(db_session, shop2, "Other Live Item", status="live")
    db_session.commit()

    # No filter: both live products across both shops
    res_all = client.get("/api/v1/shelfswipe/buyer/deck")
    assert res_all.status_code == 200
    all_ids = {item["id"] for item in res_all.json()["deck"]}
    assert str(live_prod.id) in all_ids
    assert str(other_live.id) in all_ids
    assert len(all_ids) == 2  # draft product excluded

    # Scoped to shop1 only
    res_shop = client.get("/api/v1/shelfswipe/buyer/deck", params={"shop_id": str(shop1.id)})
    assert res_shop.status_code == 200
    shop_ids = {item["id"] for item in res_shop.json()["deck"]}
    assert shop_ids == {str(live_prod.id)}


def test_buyer_swipe_creates_buyer_profile_once_and_records_swipe(client, db_session):
    seller, shop = _make_shop(db_session, "SwipeShop", "https://swipeshop-test.com")
    prod = _make_product(db_session, shop, "Swipeable Mug", status="live")
    db_session.commit()

    buyer_id = "11111111-1111-4111-8111-111111111111"

    res1 = client.post(
        "/api/v1/shelfswipe/buyer/swipe",
        json={"buyer_id": buyer_id, "product_id": str(prod.id), "direction": "right"},
    )
    assert res1.status_code == 200
    assert res1.json()["status"] == "recorded"

    # Second swipe from the same buyer should reuse the same profile, not error
    res2 = client.post(
        "/api/v1/shelfswipe/buyer/swipe",
        json={"buyer_id": buyer_id, "product_id": str(prod.id), "direction": "left"},
    )
    assert res2.status_code == 200


def test_buyer_swipe_rejects_draft_product(client, db_session):
    seller, shop = _make_shop(db_session, "DraftOnlyShop", "https://draftonly-test.com")
    prod = _make_product(db_session, shop, "Still Draft Item", status="draft")
    db_session.commit()

    res = client.post(
        "/api/v1/shelfswipe/buyer/swipe",
        json={"buyer_id": "22222222-2222-4222-8222-222222222222", "product_id": str(prod.id), "direction": "right"},
    )
    assert res.status_code == 404


def test_end_to_end_approved_product_appears_in_buyer_deck(client, db_session):
    seller, shop = _make_shop(db_session, "E2EShop", "https://e2eshop-test.com")
    prod = _make_product(db_session, shop, "E2E Candle", status="draft")
    db_session.commit()

    # Not visible to buyers yet
    res_before = client.get("/api/v1/shelfswipe/buyer/deck", params={"shop_id": str(shop.id)})
    assert res_before.json()["total_matches"] == 0

    # Approve it
    approve_res = client.post(
        f"/api/v1/shelfswipe/sellers/{seller.id}/approve",
        json={"items": [{"product_id": str(prod.id), "confirmed_stock": 7}]},
    )
    assert approve_res.status_code == 200
    assert str(prod.id) in approve_res.json()["approved"]

    # Now visible to buyers
    res_after = client.get("/api/v1/shelfswipe/buyer/deck", params={"shop_id": str(shop.id)})
    data = res_after.json()
    assert data["total_matches"] == 1
    assert data["deck"][0]["name"] == "E2E Candle"
    assert data["deck"][0]["stock"] == 7

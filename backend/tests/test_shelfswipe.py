def test_shelfswipe_deck_seeds_deterministic_demo_catalog(client):
    first = client.get(
        "/api/v1/shelfswipe/deck",
        params={"query": "birthday gift under $40", "buyer_ref": "test-buyer"},
    )
    assert first.status_code == 200
    first_data = first.json()
    assert first_data["total_matches"] >= 5
    assert first_data["deck"][0]["id"]
    assert first_data["query"] == "birthday gift under $40"

    second = client.get("/api/v1/shelfswipe/deck", params={"buyer_ref": "test-buyer"})
    assert second.status_code == 200
    assert {item["id"] for item in first_data["deck"]} == {
        item["id"] for item in second.json()["deck"]
    }


def test_shelfswipe_records_valid_swipe(client):
    deck = client.get("/api/v1/shelfswipe/deck").json()["deck"]
    response = client.post(
        "/api/v1/shelfswipe/swipe",
        json={"buyer_ref": "test-buyer", "product_id": deck[0]["id"], "direction": "right"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "recorded"


def test_shelfswipe_search_can_return_an_empty_deck(client):
    response = client.get(
        "/api/v1/shelfswipe/deck",
        params={"query": "nonexistent-material-xyz", "buyer_ref": "test-buyer"},
    )
    assert response.status_code == 200
    assert response.json()["deck"] == []
    assert response.json()["total_matches"] == 0


def test_shelfswipe_chat_resolves_multiple_products_in_one_prompt(client):
    """Without an AI key configured, the deterministic fallback should still resolve 2+ products."""
    response = client.post(
        "/api/v1/shelfswipe/chat",
        json={
            "buyer_ref": "chat-buyer-1",
            "message": "I want the lavender candle and the honey dipper set",
        },
    )
    assert response.status_code == 200
    data = response.json()
    cart_names = {item["name"] for item in data["cart"]}
    assert "Handmade Organic Lavender Candle" in cart_names
    assert "Raw Wildflower Honey & Dipper Set" in cart_names
    assert data["cart_total"] > 0


def test_shelfswipe_chat_cart_persists_and_can_be_viewed(client):
    client.post(
        "/api/v1/shelfswipe/chat",
        json={"buyer_ref": "chat-buyer-2", "message": "add the leather journal"},
    )
    cart = client.get("/api/v1/shelfswipe/cart", params={"buyer_ref": "chat-buyer-2"})
    assert cart.status_code == 200
    items = cart.json()["items"]
    assert len(items) == 1
    assert items[0]["name"] == "Hand-stitched Leather Journal"


def test_shelfswipe_chat_checkout_totals_multiple_items_and_clears_cart(client):
    client.post(
        "/api/v1/shelfswipe/chat",
        json={"buyer_ref": "chat-buyer-3", "message": "lavender candle and ceramic matcha bowl"},
    )
    pre_checkout_cart = client.get("/api/v1/shelfswipe/cart", params={"buyer_ref": "chat-buyer-3"}).json()
    expected_total = pre_checkout_cart["total"]
    assert len(pre_checkout_cart["items"]) == 2

    checkout = client.post(
        "/api/v1/shelfswipe/chat",
        json={"buyer_ref": "chat-buyer-3", "message": "checkout"},
    )
    assert checkout.status_code == 200
    data = checkout.json()
    assert data["checkout"] is not None
    assert data["checkout"]["amount"] == expected_total
    assert data["cart"] == []

    post_checkout_cart = client.get("/api/v1/shelfswipe/cart", params={"buyer_ref": "chat-buyer-3"}).json()
    assert post_checkout_cart["items"] == []


def test_shelfswipe_cart_checkout_rejects_insufficient_stock(client):
    client.post(
        "/api/v1/shelfswipe/chat",
        json={"buyer_ref": "chat-buyer-4", "message": "ceramic matcha bowl"},
    )
    cart = client.get("/api/v1/shelfswipe/cart", params={"buyer_ref": "chat-buyer-4"}).json()
    product_id = cart["items"][0]["product_id"]

    # Force the cart quantity above available stock directly via the record-swipe product lookup.
    deck = client.get("/api/v1/shelfswipe/deck", params={"query": "matcha bowl"}).json()["deck"]
    stock = next(p["stock"] for p in deck if p["id"] == product_id)

    for _ in range(stock + 2):
        client.post(
            "/api/v1/shelfswipe/chat",
            json={"buyer_ref": "chat-buyer-4", "message": "1 ceramic matcha bowl"},
        )

    response = client.post(
        "/api/v1/shelfswipe/checkout/cart",
        json={"buyer_ref": "chat-buyer-4"},
    )
    assert response.status_code == 400


def test_seller_management_routes_require_login(client):
    from app.api.dependencies import get_current_user
    from app.main import app
    app.dependency_overrides.pop(get_current_user, None)
    sid = "00000000-0000-0000-0000-000000000000"
    assert client.post("/api/v1/shelfswipe/sellers/onboard", json={"shop_url": "https://x.example"}).status_code == 401
    assert client.get(f"/api/v1/shelfswipe/sellers/{sid}/draft").status_code == 401
    assert client.post(f"/api/v1/shelfswipe/sellers/{sid}/products", json={}).status_code == 401
    assert client.patch(f"/api/v1/shelfswipe/sellers/{sid}/products/p", json={}).status_code == 401
    assert client.patch(f"/api/v1/shelfswipe/sellers/{sid}/shop", json={}).status_code == 401
    assert client.post(f"/api/v1/shelfswipe/sellers/{sid}/approve", json={}).status_code == 401


def test_checkout_rejects_non_positive_or_huge_quantity(client):
    for qty in (0, -5, 101, 10**9):
        r = client.post("/api/v1/shelfswipe/checkout", json={"buyer_ref": "b", "product_id": "p", "quantity": qty})
        assert r.status_code == 422, (qty, r.status_code)


def test_swipe_direction_is_validated(client):
    for direction in ("; DROP", "up", ""):
        r = client.post("/api/v1/shelfswipe/swipe", json={"buyer_ref": "b", "product_id": "p", "direction": direction})
        assert r.status_code == 422


def test_product_edit_limits(client):
    from pydantic import ValidationError
    from app.schemas.shelfswipe import ProductPatchRequest, ProductCreateRequest
    for bad in ({"name": ""}, {"name": "x" * 300}, {"price": "1e400"}, {"price": -1}, {"price": "1.234"},
                {"tags": ["a"] * 31}, {"stock": 10**9}, {"category": "c" * 65}):
        try:
            ProductPatchRequest(**bad)
        except ValidationError:
            continue
        raise AssertionError(f"accepted {bad}")
    ProductCreateRequest(name="ok", price="19.99", stock=3, tags=["a", "b"])

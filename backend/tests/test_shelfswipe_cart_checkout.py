import uuid

from app.db.models.shelfswipe import SSProduct
from tests.test_shelfswipe_history_and_buyer import _make_product, _make_shop


def _cart_fixture(db_session):
    _, shop = _make_shop(db_session, "CartShop", "https://cart-test.com")
    a = _make_product(db_session, shop, "Cart Item A", status="live", price="10.00", stock=5)
    b = _make_product(db_session, shop, "Cart Item B", status="live", price="4.50", stock=3)
    out = _make_product(db_session, shop, "Cart Item Out", status="live", price="1.00", stock=0)
    db_session.commit()
    return a, b, out


def test_multi_item_cart_checkout_totals_and_decrements_stock_on_capture(client, db_session):
    a, b, _ = _cart_fixture(db_session)
    a_id, b_id = a.id, b.id

    res = client.post(
        "/api/v1/shelfswipe/checkout",
        json={
            "product_id": a_id,
            "buyer_ref": "cart-buyer",
            "items": [
                {"product_id": a_id, "quantity": 2},
                {"product_id": b_id, "quantity": 1},
            ],
            "return_path": "/shelfswipe/buyer-onboarding",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["amount"] == 24.5  # 2 * 10.00 + 4.50
    assert "Cart Item A + 1 more" == body["product_name"]
    assert "return_to=buyer-onboarding" in body["approval_url"]

    client.post(
        "/api/webhooks/paypal",
        json={
            "id": f"WH-CART-{uuid.uuid4().hex[:8]}",
            "event_type": "PAYMENT.CAPTURE.COMPLETED",
            "resource_type": "capture",
            "summary": "Payment capture completed",
            "resource": {
                "id": f"CAP-CART-{uuid.uuid4().hex[:6]}",
                "custom_id": body["payment_id"],
                "status": "COMPLETED",
                "amount": {"value": "24.50", "currency_code": "USD"},
                "supplementary_data": {"related_ids": {"order_id": body["paypal_order_id"]}},
            },
        },
        headers={"x-mock-webhook": "true"},
    )

    db_session.expire_all()
    assert db_session.get(SSProduct, a_id).stock == 3
    assert db_session.get(SSProduct, b_id).stock == 2


def test_cart_checkout_rejects_out_of_stock_and_unknown_items(client, db_session):
    a, _, out = _cart_fixture(db_session)

    res = client.post(
        "/api/v1/shelfswipe/checkout",
        json={"product_id": a.id, "buyer_ref": "b", "items": [{"product_id": out.id, "quantity": 1}]},
    )
    assert res.status_code == 400
    assert "Insufficient stock" in res.json()["detail"]

    res = client.post(
        "/api/v1/shelfswipe/checkout",
        json={"product_id": a.id, "buyer_ref": "b", "items": [{"product_id": str(uuid.uuid4()), "quantity": 1}]},
    )
    assert res.status_code == 404


def test_cart_checkout_ignores_non_whitelisted_return_path(client, db_session):
    a, _, _ = _cart_fixture(db_session)
    res = client.post(
        "/api/v1/shelfswipe/checkout",
        json={"product_id": a.id, "buyer_ref": "b", "items": [{"product_id": a.id, "quantity": 1}], "return_path": "https://evil.example/x"},
    )
    assert res.status_code == 200
    assert "evil" not in res.json()["approval_url"]
    assert "return_to=shelfswipe" in res.json()["approval_url"]


def test_capture_decrements_every_cart_line_once_even_if_webhook_follows(client, db_session):
    a, b, _ = _cart_fixture(db_session)
    a_id, b_id = a.id, b.id
    body = client.post(
        "/api/v1/shelfswipe/checkout",
        json={
            "product_id": a_id,
            "buyer_ref": "cart-buyer",
            "items": [{"product_id": a_id, "quantity": 2}, {"product_id": b_id, "quantity": 1}],
        },
    ).json()
    headers = {"X-Checkout-Token": body["checkout_token"]}
    oid = body["paypal_order_id"]

    assert client.post(f"/api/v1/paypal/orders/{oid}/approve", headers=headers).status_code == 200
    cap = client.post(f"/api/v1/paypal/orders/{oid}/capture", json={}, headers=headers)
    assert cap.status_code == 200 and cap.json()["status"] == "CAPTURED"

    db_session.expire_all()
    assert db_session.get(SSProduct, a_id).stock == 3
    assert db_session.get(SSProduct, b_id).stock == 2

    # A real PayPal webhook arriving afterwards must not decrement a second time.
    client.post(
        "/api/webhooks/paypal",
        json={
            "id": f"WH-CART-{uuid.uuid4().hex[:8]}",
            "event_type": "PAYMENT.CAPTURE.COMPLETED",
            "resource_type": "capture",
            "summary": "Payment capture completed",
            "resource": {
                "id": f"CAP-CART-{uuid.uuid4().hex[:6]}",
                "custom_id": body["payment_id"],
                "status": "COMPLETED",
                "amount": {"value": "24.50", "currency_code": "USD"},
                "supplementary_data": {"related_ids": {"order_id": oid}},
            },
        },
        headers={"x-mock-webhook": "true"},
    )
    db_session.expire_all()
    assert db_session.get(SSProduct, a_id).stock == 3
    assert db_session.get(SSProduct, b_id).stock == 2

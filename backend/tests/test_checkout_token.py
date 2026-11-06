from app.api.dependencies import get_current_user, require_order_access
from app.main import app


def _real_access(client):
    app.dependency_overrides.pop(require_order_access, None)
    app.dependency_overrides.pop(get_current_user, None)


def _create_order(client):
    r = client.post("/api/v1/paypal/orders", json={"amount": "10.00", "currency": "USD"})
    assert r.status_code == 200, r.text
    return r.json()


def test_order_creation_returns_checkout_token(client):
    body = _create_order(client)
    assert body["checkout_token"]


def test_order_routes_reject_missing_or_wrong_token(client):
    order = _create_order(client)
    _real_access(client)
    oid = order["paypal_order_id"]
    assert client.get(f"/api/v1/paypal/orders/{oid}").status_code == 403
    assert client.post(f"/api/v1/paypal/orders/{oid}/approve").status_code == 403
    assert client.post(f"/api/v1/paypal/orders/{oid}/capture", json={}).status_code == 403
    bad = {"X-Checkout-Token": "0" * 64}
    assert client.post(f"/api/v1/paypal/orders/{oid}/capture", json={}, headers=bad).status_code == 403


def test_token_is_bound_to_its_own_order(client):
    a, b = _create_order(client), _create_order(client)
    _real_access(client)
    headers = {"X-Checkout-Token": a["checkout_token"]}
    assert client.post(f"/api/v1/paypal/orders/{b['paypal_order_id']}/approve", headers=headers).status_code == 403
    assert client.post(f"/api/v1/paypal/orders/{a['paypal_order_id']}/approve", headers=headers).status_code == 200

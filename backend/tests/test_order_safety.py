import logging

from app.api.dependencies import get_current_user
from app.main import app


def _body(amount="25.00"):
    return {"amount": amount, "currency": "USD", "customer_ref": "buyer@example.com"}


def test_same_idempotency_key_returns_original_order(client):
    h = {"Idempotency-Key": "attempt-0001-abcd"}
    a = client.post("/api/v1/paypal/orders", json=_body(), headers=h)
    b = client.post("/api/v1/paypal/orders", json=_body(), headers=h)
    assert a.status_code == b.status_code == 200
    assert a.json() == b.json()
    c = client.post("/api/v1/paypal/orders", json=_body(), headers={"Idempotency-Key": "attempt-0002-abcd"})
    assert c.json()["payment_id"] != a.json()["payment_id"]


def test_reusing_key_with_different_body_is_rejected(client):
    h = {"Idempotency-Key": "attempt-0003-abcd"}
    assert client.post("/api/v1/paypal/orders", json=_body("10.00"), headers=h).status_code == 200
    assert client.post("/api/v1/paypal/orders", json=_body("11.00"), headers=h).status_code == 422


def test_without_key_each_call_creates_an_order(client):
    a = client.post("/api/v1/paypal/orders", json=_body()).json()
    b = client.post("/api/v1/paypal/orders", json=_body()).json()
    assert a["payment_id"] != b["payment_id"]


def test_malformed_key_rejected(client):
    assert client.post("/api/v1/paypal/orders", json=_body(), headers={"Idempotency-Key": "x"}).status_code == 422


def test_order_amount_cap(client):
    assert client.post("/api/v1/paypal/orders", json=_body("10000.01")).status_code == 422
    assert client.post("/api/v1/paypal/orders", json=_body("10000.00")).status_code == 200


def test_security_events_are_logged(client, caplog):
    app.dependency_overrides.pop(get_current_user, None)
    with caplog.at_level(logging.INFO, logger="paytrace.security"):
        client.post("/api/v1/auth/login", json={"email": "ghost@example.com", "password": "nope-nope"})
    text = caplog.text
    assert "event=login_failed" in text and "g***@example.com" in text
    assert "nope-nope" not in text and "ghost@example.com" not in text

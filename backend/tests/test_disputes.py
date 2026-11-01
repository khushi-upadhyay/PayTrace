def _create_captured_payment(client, amount=99.50, customer_ref="dispute_shopper"):
    create_res = client.post(
        "/api/v1/paypal/orders",
        json={"amount": amount, "currency": "USD", "customer_ref": customer_ref},
    )
    p_id = create_res.json()["payment_id"]
    order_id = create_res.json()["paypal_order_id"]
    client.post(f"/api/v1/paypal/orders/{order_id}/approve")
    cap_res = client.post(f"/api/v1/paypal/orders/{order_id}/capture")
    assert cap_res.status_code == 200
    assert cap_res.json()["status"] == "CAPTURED"
    return p_id


def test_dispute_lifecycle_open_respond_resolve(client):
    p_id = _create_captured_payment(client)

    # Cannot dispute a payment that doesn't exist.
    bad_res = client.post(
        "/api/v1/disputes/simulate",
        json={"payment_id": "does-not-exist", "reason": "UNAUTHORIZED"},
    )
    assert bad_res.status_code == 404

    # Open a dispute against the captured payment.
    open_res = client.post(
        "/api/v1/disputes/simulate",
        json={
            "payment_id": p_id,
            "reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
            "buyer_statement": "Package never arrived.",
        },
    )
    assert open_res.status_code == 200
    dispute = open_res.json()
    assert dispute["status"] == "OPEN"
    assert dispute["payment_id"] == p_id
    assert dispute["is_simulated"] is True
    assert dispute["response_due_by"] is not None

    # A second open dispute on the same payment is rejected.
    dup_res = client.post(
        "/api/v1/disputes/simulate",
        json={"payment_id": p_id, "reason": "OTHER"},
    )
    assert dup_res.status_code == 400

    # Listing shows it, filterable by status.
    list_res = client.get("/api/v1/disputes", params={"status": "OPEN"})
    assert list_res.status_code == 200
    assert any(d["id"] == dispute["id"] for d in list_res.json()["items"])

    # Payment-scoped lookup works too (used by the payment detail page).
    by_payment_res = client.get(f"/api/v1/disputes/by-payment/{p_id}")
    assert by_payment_res.status_code == 200
    assert by_payment_res.json()["total"] == 1

    # Operator submits evidence without accepting liability -> goes UNDER_REVIEW, not resolved.
    respond_res = client.post(
        f"/api/v1/disputes/{dispute['id']}/respond",
        json={"seller_response": "Tracking shows delivered.", "accept_liability": False},
    )
    assert respond_res.status_code == 200
    assert respond_res.json()["status"] == "UNDER_REVIEW"
    assert respond_res.json()["resolved_at"] is None

    # Responding again (already in UNDER_REVIEW, not terminal) still works and can resolve it.
    resolve_res = client.post(
        f"/api/v1/disputes/{dispute['id']}/respond",
        json={"seller_response": "Issuing refund as goodwill.", "accept_liability": True},
    )
    assert resolve_res.status_code == 200
    assert resolve_res.json()["status"] == "RESOLVED_BUYER_FAVOUR"
    assert resolve_res.json()["resolved_at"] is not None

    # A terminal dispute can no longer be responded to.
    terminal_res = client.post(
        f"/api/v1/disputes/{dispute['id']}/respond",
        json={"seller_response": "too late", "accept_liability": False},
    )
    assert terminal_res.status_code == 400


def test_dispute_simulate_on_uncaptured_payment_returns_400(client):
    create_res = client.post(
        "/api/v1/paypal/orders",
        json={"amount": 10.00, "currency": "USD", "customer_ref": "never_captured"},
    )
    p_id = create_res.json()["payment_id"]  # created but never approved/captured

    res = client.post(
        "/api/v1/disputes/simulate",
        json={"payment_id": p_id, "reason": "OTHER"},
    )
    assert res.status_code == 400
    assert "CAPTURED" in res.json()["detail"] or "captured" in res.json()["detail"].lower()


def test_dispute_respond_unknown_id_returns_404(client):
    res = client.post(
        "/api/v1/disputes/00000000-0000-0000-0000-000000000000/respond",
        json={"seller_response": "n/a", "accept_liability": False},
    )
    assert res.status_code == 404


def test_dispute_simulate_redacts_card_like_numbers_in_statement(client):
    p_id = _create_captured_payment(client, customer_ref="redaction_shopper")
    res = client.post(
        "/api/v1/disputes/simulate",
        json={
            "payment_id": p_id,
            "reason": "UNAUTHORIZED",
            "buyer_statement": "My card 4111111111111111 was used without permission.",
        },
    )
    assert res.status_code == 200
    assert "4111111111111111" not in res.json()["buyer_statement"]
    assert "[REDACTED_CARD]" in res.json()["buyer_statement"]


def test_dispute_endpoints_require_auth(db_session):
    # Deliberately do NOT use the `client` fixture here: it overrides get_current_user
    # to always succeed. This test exists to confirm the disputes router is actually
    # wired into main.py's operator-only gate, not just "happens to require auth in
    # these tests because the fixture says so."
    from fastapi.testclient import TestClient
    from app.main import app as raw_app
    from app.db.session import get_db

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    raw_app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(raw_app) as unauth_client:
            res = unauth_client.get("/api/v1/disputes")
            assert res.status_code == 401
    finally:
        raw_app.dependency_overrides.clear()

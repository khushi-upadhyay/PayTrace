def test_human_approval_workflow(client):
    # 1. Create a payment
    create_res = client.post(
        "/api/v1/paypal/orders",
        json={"amount": 80.00, "customer_ref": "approval_test_user"}
    )
    p_id = create_res.json()["payment_id"]
    order_id = create_res.json()["paypal_order_id"]
    client.post(f"/api/v1/paypal/orders/{order_id}/approve")
    assert client.post(f"/api/v1/paypal/orders/{order_id}/capture", json={}).json()["status"] == "CAPTURED"

    # 2. Propose refund via policy check
    refund_res = client.post(
        f"/api/v1/paypal/payments/{p_id}/refund",
        json={"reason": "Customer cancellation request"}
    )
    assert refund_res.status_code == 200
    ticket_id = refund_res.json()["ticket_id"]
    assert ticket_id

    # 3. Check approvals list
    list_res = client.get("/api/v1/approvals")
    assert list_res.status_code == 200
    tickets = list_res.json()
    assert any(t["id"] == ticket_id and t["status"] == "PENDING" for t in tickets)

    # 4. Human Operator approves action
    decide_res = client.post(
        f"/api/v1/approvals/{ticket_id}/decision",
        json={"decision": "APPROVED", "notes": "Approved by senior operator"}
    )
    assert decide_res.status_code == 200
    assert decide_res.json()["decision"] == "APPROVED"
    assert decide_res.json()["status"] in ("APPROVED", "EXECUTED")

    # 5. Verify payment status updated to REFUNDED
    p_res = client.get(f"/api/v1/payments/{p_id}")
    assert p_res.json()["status"] == "REFUNDED"


def _captured_payment(client, amount="40.00"):
    created = client.post("/api/v1/paypal/orders", json={"amount": amount}).json()
    client.post(f"/api/v1/paypal/orders/{created['paypal_order_id']}/approve")
    client.post(f"/api/v1/paypal/orders/{created['paypal_order_id']}/capture", json={})
    return created["payment_id"]


def test_refund_amount_validation(client):
    pid = _captured_payment(client)
    for bad in (-5, 0, 40.01, 1000, "1e999", 1.234):
        r = client.post(f"/api/v1/paypal/payments/{pid}/refund", json={"amount": bad, "reason": "x"})
        assert r.status_code in (400, 422), (bad, r.status_code, r.text)
    assert client.post(f"/api/v1/paypal/payments/{pid}/refund", json={"amount": 10, "reason": "x" * 600}).status_code == 422


def test_unpaid_payment_cannot_be_refunded(client):
    created = client.post("/api/v1/paypal/orders", json={"amount": "40.00"}).json()
    r = client.post(f"/api/v1/paypal/payments/{created['payment_id']}/refund", json={"reason": "x"})
    assert r.status_code == 400 and "captured" in r.json()["detail"].lower()


def test_refunds_cannot_exceed_captured_amount(client):
    pid = _captured_payment(client, "40.00")
    first = client.post(f"/api/v1/paypal/payments/{pid}/refund", json={"amount": 30, "reason": "x"})
    assert first.status_code == 200
    # 30 is reserved by the pending ticket, so a second 30 must be refused even before any approval
    assert client.post(f"/api/v1/paypal/payments/{pid}/refund", json={"amount": 30, "reason": "y"}).status_code == 400
    second = client.post(f"/api/v1/paypal/payments/{pid}/refund", json={"amount": 10, "reason": "z"})
    assert second.status_code == 200
    for ticket in (first.json()["ticket_id"], second.json()["ticket_id"]):
        assert client.post(f"/api/v1/approvals/{ticket}/decision", json={"decision": "APPROVED"}).status_code == 200
    assert client.post(f"/api/v1/paypal/payments/{pid}/refund", json={"reason": "all gone"}).status_code == 400

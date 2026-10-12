def test_human_approval_workflow(client):
    # 1. Create a payment
    create_res = client.post(
        "/api/v1/paypal/orders",
        json={"amount": 80.00, "customer_ref": "approval_test_user"}
    )
    p_id = create_res.json()["payment_id"]

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

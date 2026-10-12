import uuid

def test_webhook_idempotency_and_correlation(client):
    # 1. Create a payment first
    create_res = client.post(
        "/api/v1/paypal/orders",
        json={"amount": 25.00, "currency": "USD", "customer_ref": "webhook_tester"}
    )
    p_id = create_res.json()["payment_id"]
    order_id = create_res.json()["paypal_order_id"]

    event_id = f"WH-TEST-{uuid.uuid4().hex[:8]}"
    webhook_payload = {
        "id": event_id,
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource_type": "capture",
        "summary": "Payment capture completed",
        "resource": {
            "id": f"CAP-TEST-{uuid.uuid4().hex[:6]}",
            "custom_id": p_id,
            "status": "COMPLETED",
            "amount": {"value": "25.00", "currency_code": "USD"},
            "supplementary_data": {"related_ids": {"order_id": order_id}}
        }
    }

    # First delivery
    res1 = client.post(
        "/api/webhooks/paypal",
        json=webhook_payload,
        headers={"x-mock-webhook": "true"}
    )
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["status"] == "PROCESSED"
    assert data1["payment_id"] == p_id

    # Verify payment status transitioned to CAPTURED
    p_res = client.get(f"/api/v1/payments/{p_id}")
    assert p_res.json()["status"] == "CAPTURED"

    # Second delivery (Duplicate Replay)
    res2 = client.post(
        "/api/webhooks/paypal",
        json=webhook_payload,
        headers={"x-mock-webhook": "true"}
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["status"] == "IGNORED_DUPLICATE"
    assert "idempotent" in data2["message"].lower()

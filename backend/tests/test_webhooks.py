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

def test_webhook_unmatched_stored_for_reconciliation(client):
    event_id = f"WH-UNMATCHED-{uuid.uuid4().hex[:8]}"
    webhook_payload = {
        "id": event_id,
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource_type": "capture",
        "summary": "Capture for unknown payment",
        "resource": {
            "id": "CAP-UNKNOWN-999",
            "status": "COMPLETED",
            "amount": {"value": "100.00", "currency_code": "USD"},
            "supplementary_data": {"related_ids": {"order_id": "ORDER-NONEXISTENT"}}
        }
    }

    res = client.post(
        "/api/v1/webhooks/paypal",
        json=webhook_payload,
        headers={"x-mock-webhook": "true"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "UNMATCHED"
    assert data["payment_id"] is None

def test_webhook_unverified_signature_rejected(client):
    from unittest.mock import patch, AsyncMock
    event_id = f"WH-UNVERIFIED-{uuid.uuid4().hex[:8]}"
    webhook_payload = {
        "id": event_id,
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource_type": "capture",
        "summary": "Untrusted capture",
        "resource": {"id": "CAP-UNVERIFIED-1"}
    }

    with patch("app.core.config.settings.PAYPAL_CLIENT_ID", "live_cid"), \
         patch("app.core.config.settings.PAYPAL_CLIENT_SECRET", "live_secret"), \
         patch("app.core.config.settings.PAYPAL_WEBHOOK_ID", "WH-CONFIGURED-ID"), \
         patch("app.services.paypal.client.paypal_client.verify_webhook_signature", new_callable=AsyncMock, return_value=False):
        res = client.post(
            "/api/v1/webhooks/paypal",
            json=webhook_payload,
            headers={
                "paypal-transmission-id": "fake-trans-id",
                "paypal-transmission-sig": "fake-sig",
            }
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "VERIFICATION_FAILED"

def test_webhook_capture_denied_and_pending(client):
    # 1. Test Capture Denied
    create_res1 = client.post(
        "/api/v1/paypal/orders",
        json={"amount": 30.00, "currency": "USD", "customer_ref": "denied_buyer"}
    )
    p_id1 = create_res1.json()["payment_id"]
    order_id1 = create_res1.json()["paypal_order_id"]

    denied_wh = {
        "id": f"WH-DENIED-{uuid.uuid4().hex[:8]}",
        "event_type": "PAYMENT.CAPTURE.DENIED",
        "resource_type": "capture",
        "summary": "Capture denied",
        "resource": {
            "id": f"CAP-DENIED-{uuid.uuid4().hex[:6]}",
            "status": "DENIED",
            "status_details": {"reason": "CARD_DECLINED"},
            "supplementary_data": {"related_ids": {"order_id": order_id1}}
        }
    }
    client.post("/api/v1/webhooks/paypal", json=denied_wh, headers={"x-mock-webhook": "true"})
    p1 = client.get(f"/api/v1/payments/{p_id1}").json()
    assert p1["status"] == "DENIED"

    # 2. Test Capture Pending
    create_res2 = client.post(
        "/api/v1/paypal/orders",
        json={"amount": 40.00, "currency": "USD", "customer_ref": "pending_buyer"}
    )
    p_id2 = create_res2.json()["payment_id"]
    order_id2 = create_res2.json()["paypal_order_id"]

    pending_wh = {
        "id": f"WH-PENDING-{uuid.uuid4().hex[:8]}",
        "event_type": "PAYMENT.CAPTURE.PENDING",
        "resource_type": "capture",
        "summary": "Capture pending",
        "resource": {
            "id": f"CAP-PENDING-{uuid.uuid4().hex[:6]}",
            "status": "PENDING",
            "status_details": {"reason": "PENDING_REVIEW"},
            "supplementary_data": {"related_ids": {"order_id": order_id2}}
        }
    }
    client.post("/api/v1/webhooks/paypal", json=pending_wh, headers={"x-mock-webhook": "true"})
    p2 = client.get(f"/api/v1/payments/{p_id2}").json()
    assert p2["status"] == "PENDING"


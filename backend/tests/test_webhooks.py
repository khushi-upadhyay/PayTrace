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


def test_mock_webhook_header_is_not_trusted_outside_test_mode(client):
    from unittest.mock import patch

    create_res = client.post("/api/v1/paypal/orders", json={"amount": 25.00})
    assert create_res.status_code == 200
    payment_id = create_res.json()["payment_id"]
    order_id = create_res.json()["paypal_order_id"]
    event = {
        "id": f"WH-SPOOF-{uuid.uuid4().hex[:8]}",
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource_type": "capture",
        "resource": {
            "id": "CAP-SPOOF-1",
            "custom_id": payment_id,
            "supplementary_data": {"related_ids": {"order_id": order_id}},
        },
    }
    with patch("app.core.config.settings.APP_ENV", "development"):
        response = client.post(
            "/api/v1/webhooks/paypal",
            json=event,
            headers={"x-mock-webhook": "true"},
        )
    assert response.status_code == 200
    assert response.json()["status"] == "VERIFICATION_FAILED"
    assert client.get(f"/api/v1/payments/{payment_id}").json()["status"] == "CREATED"


def test_webhook_rejects_malformed_json(client):
    response = client.post("/api/webhooks/paypal", content=b"not json")
    assert response.status_code == 400

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



def test_order_approved_webhook_does_not_mark_payment_captured(client):
    created = client.post("/api/v1/paypal/orders", json={"amount": 25.00, "currency": "USD"})
    payment_id = created.json()["payment_id"]
    order_id = created.json()["paypal_order_id"]
    payload = {
        "id": f"WH-APPROVED-{uuid.uuid4().hex[:8]}",
        "event_type": "CHECKOUT.ORDER.APPROVED",
        "resource_type": "checkout-order",
        "resource": {"id": order_id, "status": "APPROVED"},
    }
    response = client.post("/api/v1/webhooks/paypal", json=payload, headers={"x-mock-webhook": "true"})
    assert response.json()["status"] == "PROCESSED"
    payment = client.get(f"/api/v1/payments/{payment_id}").json()
    assert payment["status"] == "APPROVED"
    assert payment["paypal_capture_id"] is None


def test_capture_completed_webhook_rejects_amount_mismatch(client):
    created = client.post("/api/v1/paypal/orders", json={"amount": 25.00, "currency": "USD"})
    payment_id = created.json()["payment_id"]
    order_id = created.json()["paypal_order_id"]
    payload = {
        "id": f"WH-MISMATCH-{uuid.uuid4().hex[:8]}",
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource_type": "capture",
        "resource": {
            "id": "CAP-MISMATCH", "custom_id": payment_id, "status": "COMPLETED",
            "amount": {"value": "24.00", "currency_code": "USD"},
            "supplementary_data": {"related_ids": {"order_id": order_id}},
        },
    }
    response = client.post("/api/v1/webhooks/paypal", json=payload, headers={"x-mock-webhook": "true"})
    assert response.json()["status"] == "INVALID_CAPTURE"
    payment = client.get(f"/api/v1/payments/{payment_id}").json()
    assert payment["status"] == "CREATED"
    assert payment["paypal_capture_id"] is None

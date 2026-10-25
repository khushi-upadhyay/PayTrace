def test_investigation_timeout_scenario(client):
    """
    Tests PayTrace investigation of the critical scenario:
    Merchant backend timed out waiting for capture response.
    PayTrace must identify uncertain state, high risk, and explicitly advise
    reconciliation over retry to prevent duplicate charges.
    """
    # 1. Trigger the timeout scenario
    scen_res = client.post(
        "/api/v1/demo/scenarios",
        json={"scenario": "timeout_before_response"}
    )
    assert scen_res.status_code == 200
    p_id = scen_res.json()["payment_id"]

    # 2. Verify payment is marked CAPTURE_UNCERTAIN
    p_res = client.get(f"/api/v1/payments/{p_id}")
    assert p_res.json()["status"] == "CAPTURE_UNCERTAIN"
    assert p_res.json()["failure_code"] == "TIMEOUT_BEFORE_RESPONSE"

    # 3. Run AI Investigator
    inv_res = client.post(
        "/api/v1/ai/investigate",
        json={"payment_id": p_id, "question": "Why did this payment stop?"}
    )
    assert inv_res.status_code == 200
    inv = inv_res.json()

    assert inv["severity"] == "HIGH"
    assert ("timed out" in inv["root_cause"].lower()) or ("timeout" in inv["root_cause"].lower())
    assert len(inv["facts"]) >= 3

    assert len(inv["inferences"]) >= 1

    # Crucial PRD requirement assertions:
    # Must advise against blind retries to prevent duplicate charges!
    recommendation = inv["recommendation"].lower()
    inferences_str = " ".join(inv["inferences"]).lower()
    facts_str = " ".join(inv["facts"]).lower()

    assert "duplicate" in (inferences_str + recommendation + facts_str)
    assert ("reconcil" in recommendation) or ("check" in recommendation)

    # 4. Test chat endpoint advice regarding retry
    chat_res = client.post(
        "/api/v1/ai/chat",
        json={
            "payment_id": p_id,
            "messages": [{"role": "user", "content": "Can I immediately retry this capture?"}]
        }
    )
    assert chat_res.status_code == 200
    chat_data = chat_res.json()
    assert "not" in chat_data["response"].lower() or "warning" in chat_data["response"].lower()

def test_investigation_denied_scenario(client):
    scen_res = client.post("/api/v1/demo/scenarios", json={"scenario": "capture_denied"})
    assert scen_res.status_code == 200
    p_id = scen_res.json()["payment_id"]

    inv_res = client.post("/api/v1/ai/investigate", json={"payment_id": p_id})
    assert inv_res.status_code == 200
    inv = inv_res.json()
    assert inv["severity"] == "MEDIUM"
    assert "declined" in inv["root_cause"].lower() or "denied" in inv["root_cause"].lower()
    assert len(inv["facts"]) >= 2
    assert "instrument" in inv["recommendation"].lower() or "alternative" in inv["recommendation"].lower()

def test_investigation_capture_pending_scenario(client):
    # Create order and force PENDING via webhook
    create_res = client.post("/api/v1/paypal/orders", json={"amount": 80.00, "customer_ref": "pending_shopper"})
    p_id = create_res.json()["payment_id"]
    order_id = create_res.json()["paypal_order_id"]

    pending_wh = {
        "id": f"WH-PENDING-{p_id[:8]}",
        "event_type": "PAYMENT.CAPTURE.PENDING",
        "resource_type": "capture",
        "resource": {
            "id": f"CAP-PENDING-{p_id[:6]}",
            "status": "PENDING",
            "status_details": {"reason": "PENDING_REVIEW"},
            "supplementary_data": {"related_ids": {"order_id": order_id}}
        }
    }
    client.post("/api/v1/webhooks/paypal", json=pending_wh, headers={"x-mock-webhook": "true"})

    inv_res = client.post("/api/v1/ai/investigate", json={"payment_id": p_id})
    assert inv_res.status_code == 200
    inv = inv_res.json()
    assert "pending" in inv["root_cause"].lower()
    assert inv["severity"] == "MEDIUM"

def test_investigation_delayed_webhook_scenario(client):
    # Create and capture order without receiving any webhook
    create_res = client.post("/api/v1/paypal/orders", json={"amount": 49.99, "customer_ref": "fast_shopper"})
    p_id = create_res.json()["payment_id"]
    order_id = create_res.json()["paypal_order_id"]
    client.post(f"/api/v1/paypal/orders/{order_id}/capture")

    inv_res = client.post("/api/v1/ai/investigate", json={"payment_id": p_id})
    assert inv_res.status_code == 200
    inv = inv_res.json()
    assert "webhook" in inv["root_cause"].lower() or "delayed" in inv["root_cause"].lower()


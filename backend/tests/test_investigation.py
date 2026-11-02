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
    client.post(f"/api/v1/paypal/orders/{order_id}/approve")
    client.post(f"/api/v1/paypal/orders/{order_id}/capture")

    inv_res = client.post("/api/v1/ai/investigate", json={"payment_id": p_id})
    assert inv_res.status_code == 200
    inv = inv_res.json()
    assert "webhook" in inv["root_cause"].lower() or "delayed" in inv["root_cause"].lower()
    assert any("does not prove" in fact.lower() for fact in inv["facts"])


def test_captured_payment_without_webhook_does_not_claim_provider_delivery_failure(client):
    create_res = client.post("/api/v1/paypal/orders", json={"amount": 18.25, "customer_ref": "no-webhook-evidence"})
    payment_id = create_res.json()["payment_id"]
    order_id = create_res.json()["paypal_order_id"]
    client.post(f"/api/v1/paypal/orders/{order_id}/approve")
    client.post(f"/api/v1/paypal/orders/{order_id}/capture")

    response = client.post("/api/v1/ai/investigate", json={"payment_id": payment_id})
    assert response.status_code == 200
    result = response.json()
    claims = " ".join([result["root_cause"], *result["facts"], *result["inferences"]]).lower()
    assert "no linked webhook records were found" in claims
    assert "does not prove" in claims
    assert "delayed" not in result["root_cause"].lower()


def test_followup_webhook_question_reports_only_stored_evidence(client):
    create_res = client.post("/api/v1/paypal/orders", json={"amount": 18.25, "customer_ref": "chat-webhook-evidence"})
    payment_id = create_res.json()["payment_id"]

    response = client.post("/api/v1/ai/chat", json={
        "payment_id": payment_id,
        "messages": [
            {"role": "user", "content": "Explain this payment"},
            {"role": "assistant", "content": "The payment is pending."},
            {"role": "user", "content": "Were any webhook events recorded?"},
        ],
        "question": "Were any webhook events recorded?",
    })
    assert response.status_code == 200
    assert "no webhook events were found" in response.json()["response"].lower()
    assert "does not prove" in response.json()["response"].lower()


def test_followup_investigation_uses_linked_session_network_evidence(client):
    session_response = client.post("/api/v1/sessions", json={"visitor_ref": "ai-evidence-test"})
    assert session_response.status_code == 200
    session_id = session_response.json()["id"]
    payment_response = client.post("/api/v1/paypal/orders", json={"amount": 18.25, "customer_ref": "session-evidence", "session_id": session_id})
    payment_id = payment_response.json()["payment_id"]
    event_response = client.post(f"/api/v1/sessions/{session_id}/events", json={"events": [{
        "id": "a5a98f9c-2ccd-4c20-a57d-4e43fbdb0e97",
        "event_type": "network",
        "category": "network",
        "severity": "error",
        "payment_id": payment_id,
        "route": "/checkout",
        "payload": {"method": "POST", "url": "http://localhost:8000/api/v1/paypal/orders/capture", "status": 502, "duration_ms": 2100, "outcome": "http_error"},
    }]})
    assert event_response.status_code == 200

    response = client.post("/api/v1/ai/chat", json={
        "payment_id": payment_id,
        "messages": [{"role": "user", "content": "Which network request failed?"}],
        "question": "Which network request failed?",
    })
    assert response.status_code == 200
    assert "network" in response.json()["response"].lower()
    assert "502" in response.json()["response"]


def test_incident_investigation_uses_stored_incident_and_payment_evidence(client, db_session):
    from datetime import datetime
    from decimal import Decimal
    from app.db.models.incident import Incident
    from app.db.models.payment import Payment

    payment_id = "incident-payment-1"
    incident_id = "incident-context-1"
    db_session.add(Payment(id=payment_id, paypal_order_id="ORDER-INCIDENT-1", customer_ref="buyer-incident", amount=Decimal("45.00"), currency="USD", status="CAPTURE_UNCERTAIN", failure_code="TIMEOUT_BEFORE_RESPONSE", source_mode="SIMULATED", actor="demo", created_at=datetime.utcnow(), updated_at=datetime.utcnow()))
    db_session.add(Incident(id=incident_id, title="Stored timeout incident", severity="HIGH", status="OPEN", started_at=datetime.utcnow(), affected_payment_count=1, revenue_at_risk=Decimal("45.00"), currency="USD", detection_rule="CAPTURE_TIMEOUT_SPIKE", root_cause=None, created_at=datetime.utcnow(), updated_at=datetime.utcnow()))
    db_session.flush()

    response = client.post("/api/v1/ai/investigate", json={"incident_id": incident_id})
    assert response.status_code == 200
    result = response.json()
    assert result["incident_id"] == incident_id
    assert result["severity"] == "HIGH"
    assert any(payment_id in fact for fact in result["facts"])
    assert any("no stored root-cause assessment" in fact.lower() for fact in result["facts"])

    chat = client.post("/api/v1/ai/chat", json={"incident_id": incident_id, "messages": [{"role": "user", "content": "Which payments are affected?"}]})
    assert chat.status_code == 200
    assert payment_id in chat.json()["response"]


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

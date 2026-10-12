def test_demo_scenarios_and_reset(client):
    """
    Tests listing demo scenarios, triggering scenarios, and resetting demo data.
    """
    # 1. List scenarios
    list_res = client.get("/api/v1/demo/scenarios")
    assert list_res.status_code == 200
    scenarios = list_res.json()
    assert len(scenarios) >= 3

    scenario_ids = [s["id"] for s in scenarios]
    assert "timeout_before_response" in scenario_ids
    assert "capture_denied" in scenario_ids

    # 2. Trigger capture_denied scenario
    denied_res = client.post(
        "/api/v1/demo/scenarios",
        json={"scenario": "capture_denied"}
    )
    assert denied_res.status_code == 200
    p_id = denied_res.json()["payment_id"]

    # Verify denied status
    p = client.get(f"/api/v1/payments/{p_id}").json()
    assert p["status"] == "DENIED"
    assert p["source_mode"] == "SIMULATED"

    # 3. Trigger duplicate webhook scenario
    dup_res = client.post(
        "/api/v1/demo/scenarios",
        json={"scenario": "duplicate_webhook_replay"}
    )
    assert dup_res.status_code == 200

    # 4. Reset demo data
    reset_res = client.post("/api/v1/demo/reset")
    assert reset_res.status_code == 200
    reset_data = reset_res.json()
    assert reset_data["success"] is True
    assert reset_data["payments_seeded"] >= 5

def test_incident_detection_and_reporting(client):
    # Trigger timeout scenario which generates an incident
    client.post(
        "/api/v1/demo/scenarios",
        json={"scenario": "timeout_before_response"}
    )

    # Fetch incidents
    inc_res = client.get("/api/v1/incidents")
    assert inc_res.status_code == 200
    inc_list = inc_res.json()["items"]
    assert len(inc_list) >= 1

    timeout_inc = next((i for i in inc_list if "timeout" in i["title"].lower()), None)
    assert timeout_inc is not None
    assert timeout_inc["severity"] == "HIGH"
    assert timeout_inc["affected_payment_count"] >= 1
    assert float(timeout_inc["revenue_at_risk"]) > 0

    # Incident Details
    detail_res = client.get(f"/api/v1/incidents/{timeout_inc['id']}")
    assert detail_res.status_code == 200
    details = detail_res.json()
    assert len(details["affected_payments"]) >= 1

    # Generate Report
    report_res = client.post(f"/api/v1/incidents/{timeout_inc['id']}/report")
    assert report_res.status_code == 200
    report = report_res.json()
    assert report["incident_id"] == timeout_inc["id"]
    assert len(report["detailed_findings"]) >= 2
    assert len(report["recommended_mitigations"]) >= 1

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

    # A single day's worth of payments is not yet a "recurring pattern".
    assert timeout_inc["recurrence"]["distinct_days_seen"] == 1
    assert timeout_inc["recurrence"]["pattern_label"] is None

    # Generate Report
    report_res = client.post(f"/api/v1/incidents/{timeout_inc['id']}/report")
    assert report_res.status_code == 200
    report = report_res.json()
    assert report["incident_id"] == timeout_inc["id"]
    assert len(report["detailed_findings"]) >= 2
    assert len(report["recommended_mitigations"]) >= 1


def test_incident_recurrence_is_grounded_in_distinct_days(db_session):
    """
    Unit-level check of the pattern-tracking math itself: it must count distinct
    calendar days with a matching failure, not just raw row count, and must not
    claim a pattern exists from a single day's events.
    """
    import uuid
    from datetime import timedelta
    from decimal import Decimal
    from app.core.time import utc_now
    from app.db.models.payment import Payment
    from app.db.models.incident import Incident
    from app.services.incidents.detector import incident_detector

    now = utc_now()

    def make_payment(days_ago: int):
        db_session.add(Payment(
            id=str(uuid.uuid4()),
            customer_ref="pattern_test",
            amount=Decimal("50.00"),
            currency="USD",
            status="CAPTURE_UNCERTAIN",
            failure_code="TIMEOUT_BEFORE_RESPONSE",
            source_mode="SIMULATED",
            created_at=now - timedelta(days=days_ago),
        ))

    # Three distinct days within the window, plus two same-day duplicates that
    # must NOT inflate the distinct-day count.
    make_payment(days_ago=0)
    make_payment(days_ago=0)
    make_payment(days_ago=2)
    make_payment(days_ago=5)
    # Outside the 7-day window entirely; must not be counted.
    make_payment(days_ago=9)
    db_session.flush()

    incident = Incident(
        id=str(uuid.uuid4()),
        title="Capture Timeout & Unresolved Backend State Spike",
        severity="HIGH",
        status="OPEN",
        detection_rule="CAPTURE_TIMEOUT_SPIKE",
    )

    result = incident_detector.compute_recurrence(db_session, incident, window_days=7)
    assert result["distinct_days_seen"] == 3
    assert result["payments_in_window"] == 4
    assert "3" in result["pattern_label"]

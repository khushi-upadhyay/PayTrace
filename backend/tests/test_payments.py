def test_create_and_get_payment(client):
    # Create order
    create_res = client.post(
        "/api/v1/paypal/orders",
        json={"amount": 49.99, "currency": "USD", "customer_ref": "test_user_1"}
    )
    assert create_res.status_code == 200
    create_data = create_res.json()
    payment_id = create_data["payment_id"]
    order_id = create_data["paypal_order_id"]
    assert payment_id
    assert order_id

    # Retrieve payment
    get_res = client.get(f"/api/v1/payments/{payment_id}")
    assert get_res.status_code == 200
    p = get_res.json()
    assert p["id"] == payment_id
    assert p["status"] == "CREATED"
    assert float(p["amount"]) == 49.99

    # List payments
    list_res = client.get("/api/v1/payments")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["total"] >= 1


def test_payment_workspace_uses_persisted_payment_and_event_data(client, db_session):
    from app.db.models.payment import Payment
    from app.db.models.payment_event import PaymentEvent
    from app.db.models.session import Session, SessionEvent

    db_session.add(Session(id="workspace-session-1", visitor_ref="anon-workspace"))

    payment = Payment(
        id="workspace-payment-1",
        customer_ref="buyer-workspace",
        session_id="workspace-session-1",
        amount="42.50",
        currency="USD",
        status="CAPTURE_FAILED",
        source_mode="PAYPAL_SANDBOX",
        failure_code="DECLINED",
    )
    db_session.add(payment)
    db_session.flush()
    db_session.add(PaymentEvent(
        payment_id=payment.id,
        event_type="capture",
        source="PAYPAL_API",
        status="FAILED",
        latency_ms=2450,
        is_simulated=False,
    ))
    db_session.add(SessionEvent(
        id="workspace-network-1",
        session_id="workspace-session-1",
        payment_id=payment.id,
        event_type="fetch",
        category="network",
        route="/checkout",
        payload_redacted={"url": "/api/capture?access_token=must-not-leak", "method": "POST", "status": 500, "duration_ms": 123},
    ))
    db_session.commit()

    response = client.get("/api/v1/payments/workspace")
    assert response.status_code == 200
    data = response.json()
    assert data["total_transactions"] == 1
    assert data["failed_count"] == 1
    assert data["average_event_latency_ms"] == 2450
    assert data["latency_sample_count"] == 1
    assert data["transactions"][0]["id"] == payment.id
    assert data["transactions"][0]["processing_duration_ms"] == 2450
    assert any(finding["kind"] == "high_observed_latency" for finding in data["anomalies"])
    assert data["failures_by_endpoint"] == [{"endpoint": "/api/capture", "count": 1, "payment_ids": [payment.id]}]
    assert data["correlated_network_events"][0]["endpoint"] == "/api/capture"
    assert "must-not-leak" not in response.text


def test_payment_workspace_represents_missing_data_as_missing(client):
    response = client.get("/api/v1/payments/workspace")
    assert response.status_code == 200
    data = response.json()
    assert data["total_transactions"] == 0
    assert data["average_event_latency_ms"] is None
    assert data["latency_sample_count"] == 0
    assert data["processed_amounts"] == []
    assert data["transactions"] == []


def test_payment_list_filters_and_sorts_in_the_database(client, db_session):
    from app.db.models.payment import Payment

    db_session.add_all([
        Payment(id="sort-payment-a", customer_ref="sort-buyer", amount="30.00", currency="USD", status="CAPTURE_FAILED", source_mode="PAYPAL_SANDBOX"),
        Payment(id="sort-payment-b", customer_ref="sort-buyer", amount="10.00", currency="USD", status="CAPTURE_FAILED", source_mode="PAYPAL_SANDBOX"),
        Payment(id="sort-payment-c", customer_ref="sort-buyer", amount="5.00", currency="USD", status="CAPTURED", source_mode="PAYPAL_SANDBOX"),
    ])
    db_session.commit()

    response = client.get("/api/v1/payments", params={
        "status": "CAPTURE_FAILED", "sort_by": "amount", "sort_order": "asc", "page_size": 100,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert [item["id"] for item in data["items"]] == ["sort-payment-b", "sort-payment-a"]

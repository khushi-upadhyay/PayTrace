def test_analytics_metrics(client):
    """
    Tests the analytics engine for metrics, success rate, latency breakdown,
    uncertain payments, and revenue-at-risk aggregation.
    """
    # Create payments: 1 captured, 1 timeout uncertain
    p1 = client.post(
        "/api/v1/paypal/orders",
        json={"amount": 100.0, "currency": "USD", "customer_ref": "analytics_user_1"}
    ).json()
    client.post(f"/api/v1/paypal/orders/{p1['paypal_order_id']}/approve")
    client.post(
        f"/api/v1/paypal/orders/{p1['paypal_order_id']}/capture",
        json={"simulate_timeout": False}
    )

    p2 = client.post(
        "/api/v1/paypal/orders",
        json={"amount": 250.0, "currency": "USD", "customer_ref": "analytics_user_2"}
    ).json()
    client.post(f"/api/v1/paypal/orders/{p2['paypal_order_id']}/approve")
    client.post(
        f"/api/v1/paypal/orders/{p2['paypal_order_id']}/capture",
        json={"simulate_timeout": True}
    )

    # Query analytics endpoint
    res = client.get("/api/v1/analytics")
    assert res.status_code == 200
    data = res.json()

    assert data["total_payments"] >= 2
    assert data["uncertain_payments"] >= 1
    assert float(data["potential_revenue_at_risk"]) >= 250.0
    assert 0.0 <= data["success_rate_percent"] <= 100.0
    assert "status_breakdown" in data
    assert "volume_over_time" in data
    assert "failure_categories" in data
    assert data["average_webhook_delay_seconds"] is None


def test_analytics_keeps_revenue_at_risk_separate_by_currency(client, db_session):
    from app.db.models.payment import Payment

    db_session.add_all([
        Payment(id="risk-usd", customer_ref="risk-usd", amount="25.00", currency="USD", status="DENIED"),
        Payment(id="risk-eur", customer_ref="risk-eur", amount="30.00", currency="EUR", status="CAPTURE_UNCERTAIN"),
    ])
    db_session.commit()

    response = client.get("/api/v1/analytics")
    assert response.status_code == 200
    data = response.json()
    assert data["potential_revenue_at_risk"] is None
    assert data["currency"] == "MULTI"
    assert data["revenue_at_risk_by_currency"] == [
        {"currency": "EUR", "amount": "30.00"},
        {"currency": "USD", "amount": "25.00"},
    ]

def test_payment_timeline_flow(client):
    # 1. Create Order
    create_res = client.post(
        "/api/v1/paypal/orders",
        json={"amount": 99.50, "currency": "USD", "customer_ref": "timeline_shopper"}
    )
    p_id = create_res.json()["payment_id"]
    order_id = create_res.json()["paypal_order_id"]

    # 2. Capture Order
    cap_res = client.post(f"/api/v1/paypal/orders/{order_id}/capture")
    assert cap_res.status_code == 200

    # 3. Fetch Timeline
    tl_res = client.get(f"/api/v1/payments/{p_id}/timeline")
    assert tl_res.status_code == 200
    tl_data = tl_res.json()
    assert tl_data["payment_id"] == p_id
    assert tl_data["current_status"] == "CAPTURED"
    assert tl_data["total_events"] >= 3

    event_types = [e["event_type"] for e in tl_data["events"]]
    assert "CHECKOUT_ORDER_CREATED" in event_types
    assert "CHECKOUT_ORDER_APPROVED" in event_types
    assert "CAPTURE_COMPLETED" in event_types

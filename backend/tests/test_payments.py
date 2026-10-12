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

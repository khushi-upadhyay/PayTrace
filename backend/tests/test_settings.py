def test_settings_exposure_safety(client):
    """
    Tests settings status endpoint:
    Must disclose integration status and public IDs without leaking secrets.
    """
    res = client.get("/api/v1/settings")
    assert res.status_code == 200
    data = res.json()

    assert "paypal" in data
    assert "ai" in data
    assert "database" in data
    assert "is_configured" in data["paypal"]
    assert "is_configured" in data["ai"]
    assert "environment" in data["paypal"]
    assert "provider" in data["ai"]

    # Verify no secret credentials exist anywhere in the payload
    serialized = str(data).lower()
    assert "client_secret" not in serialized
    assert "paypal_client_secret" not in serialized
    assert "password" not in serialized

def test_health_check(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("healthy", "degraded")
    assert data["paypal_environment"] == "sandbox"
    assert data["paypal_configured"] is False
    assert "ai_investigator" in data

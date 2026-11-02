from datetime import datetime
from decimal import Decimal

from app.db.models.incident import Incident
from app.db.models.payment import Payment
from app.db.models.session import Session as BrowserSession


def test_workspace_search_returns_persisted_categories_and_detail_links(client, db_session):
    now = datetime.utcnow()
    db_session.add(Payment(id="search-payment-1", paypal_order_id="ORDER-SEARCH-1", customer_ref="customer-search-1", amount=Decimal("20.00"), currency="USD", status="CAPTURE_FAILED", failure_code="SEARCH_FAILURE_CODE", source_mode="SIMULATED", actor="demo", created_at=now, updated_at=now))
    db_session.add(BrowserSession(id="search-session-1", visitor_ref="visitor-search-1", started_at=now, last_activity_at=now, metadata_redacted={}, recording_enabled=True))
    db_session.add(Incident(id="search-incident-1", title="Searchable incident", severity="MEDIUM", status="OPEN", started_at=now, affected_payment_count=1, revenue_at_risk=Decimal("20.00"), currency="USD", detection_rule="SEARCH_RULE", created_at=now, updated_at=now))
    db_session.flush()

    for query, category, href in [
        ("ORDER-SEARCH-1", "PayPal order", "/payments/search-payment-1"),
        ("customer-search-1", "Customer", "/payments/search-payment-1"),
        ("SEARCH_FAILURE_CODE", "Failure code", "/payments/search-payment-1"),
        ("search-session-1", "Session", "/sessions/search-session-1"),
        ("search-incident-1", "Incident", "/incidents/search-incident-1"),
    ]:
        response = client.get("/api/v1/search", params={"q": query})
        assert response.status_code == 200
        assert any(item["category"] == category and item["href"] == href for item in response.json()["items"])

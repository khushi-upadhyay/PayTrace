import uuid
import pytest
from unittest.mock import patch, AsyncMock
from decimal import Decimal
import httpx
from app.services.paypal.client import PayPalClient
from app.core.config import settings

@pytest.mark.asyncio
async def test_paypal_client_oauth_token_acquisition():
    client = PayPalClient()
    mock_response = httpx.Response(
        200,
        json={"access_token": "FAKE_ACCESS_TOKEN_123", "expires_in": 3600},
        request=httpx.Request("POST", "https://api-m.sandbox.paypal.com/v1/oauth2/token"),
    )

    with patch("app.core.config.settings.PAYPAL_CLIENT_ID", "test-client-id"), \
         patch("app.core.config.settings.PAYPAL_CLIENT_SECRET", "test-client-secret"), \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        token = await client.get_access_token()
        assert token == "FAKE_ACCESS_TOKEN_123"
        # Verify caching returns same token without re-fetching
        cached = await client.get_access_token()
        assert cached == "FAKE_ACCESS_TOKEN_123"

@pytest.mark.asyncio
async def test_paypal_client_missing_credentials_raises_error():
    client = PayPalClient()
    with patch("app.core.config.settings.PAYPAL_CLIENT_ID", ""), \
         patch("app.core.config.settings.PAYPAL_CLIENT_SECRET", ""):
        with pytest.raises(ValueError, match="PayPal Client ID and Secret are not configured"):
            await client.get_access_token()

@pytest.mark.asyncio
async def test_paypal_client_create_order():
    client = PayPalClient()
    client._token = "VALID_CACHED_TOKEN"
    import datetime
    client._token_expires_at = datetime.datetime.utcnow() + datetime.timedelta(hours=1)

    mock_res = httpx.Response(
        201,
        json={"id": "ORDER-LIVE-999", "status": "CREATED", "links": [{"rel": "approve", "href": "https://sandbox.paypal.com/checkoutnow?token=ORDER-LIVE-999"}]},
        request=httpx.Request("POST", "https://api-m.sandbox.paypal.com/v2/checkout/orders"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_res):
        res = await client.create_order(amount=Decimal("49.99"), currency="USD", custom_id="pay-123")
        assert res["id"] == "ORDER-LIVE-999"

@pytest.mark.asyncio
async def test_paypal_client_capture_order():
    client = PayPalClient()
    client._token = "VALID_CACHED_TOKEN"
    import datetime
    client._token_expires_at = datetime.datetime.utcnow() + datetime.timedelta(hours=1)

    mock_res = httpx.Response(
        201,
        json={
            "id": "ORDER-LIVE-999",
            "status": "COMPLETED",
            "purchase_units": [{"payments": {"captures": [{"id": "CAP-LIVE-999", "status": "COMPLETED"}]}}],
        },
        request=httpx.Request("POST", "https://api-m.sandbox.paypal.com/v2/checkout/orders/ORDER-LIVE-999/capture"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_res):
        res = await client.capture_order("ORDER-LIVE-999")
        assert res["status"] == "COMPLETED"

@pytest.mark.asyncio
async def test_paypal_client_verify_webhook_signature():
    client = PayPalClient()
    client._token = "VALID_CACHED_TOKEN"
    import datetime
    client._token_expires_at = datetime.datetime.utcnow() + datetime.timedelta(hours=1)

    mock_res = httpx.Response(
        200,
        json={"verification_status": "SUCCESS"},
        request=httpx.Request("POST", "https://api-m.sandbox.paypal.com/v1/notifications/verify-webhook-signature"),
    )

    with patch("app.core.config.settings.PAYPAL_WEBHOOK_ID", "WH-ID-12345"), \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_res):
        headers = {
            "paypal-auth-algo": "SHA256withRSA",
            "paypal-cert-url": "https://api.sandbox.paypal.com/cert",
            "paypal-transmission-id": "trans-1",
            "paypal-transmission-sig": "sig-1",
            "paypal-transmission-time": "2026-10-24T12:00:00Z",
        }
        raw_body = b'{"id":"WH-EVT-1","event_type":"PAYMENT.CAPTURE.COMPLETED"}'
        verified = await client.verify_webhook_signature(headers, raw_body)
        assert verified is True

@pytest.mark.asyncio
async def test_paypal_client_verify_webhook_signature_rejected():
    client = PayPalClient()
    client._token = "VALID_CACHED_TOKEN"
    import datetime
    client._token_expires_at = datetime.datetime.utcnow() + datetime.timedelta(hours=1)

    mock_res = httpx.Response(
        200,
        json={"verification_status": "FAILURE"},
        request=httpx.Request("POST", "https://api-m.sandbox.paypal.com/v1/notifications/verify-webhook-signature"),
    )

    with patch("app.core.config.settings.PAYPAL_WEBHOOK_ID", "WH-ID-12345"), \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_res):
        headers = {
            "paypal-auth-algo": "SHA256withRSA",
            "paypal-cert-url": "https://api.sandbox.paypal.com/cert",
            "paypal-transmission-id": "trans-1",
            "paypal-transmission-sig": "sig-1",
            "paypal-transmission-time": "2026-10-24T12:00:00Z",
        }
        raw_body = b'{"id":"WH-EVT-1","event_type":"PAYMENT.CAPTURE.COMPLETED"}'
        verified = await client.verify_webhook_signature(headers, raw_body)
        assert verified is False

@pytest.mark.asyncio
async def test_paypal_client_capture_order_preserves_error():
    client = PayPalClient()
    client._token = "VALID_CACHED_TOKEN"
    import datetime
    client._token_expires_at = datetime.datetime.utcnow() + datetime.timedelta(hours=1)

    error_payload = {
        "name": "UNPROCESSABLE_ENTITY",
        "details": [{"issue": "ORDER_NOT_APPROVED", "description": "Payer has not yet approved the Order for payment."}],
        "message": "The requested action could not be performed, semantically incorrect, or failed business validation.",
    }
    mock_error_res = httpx.Response(
        422,
        json=error_payload,
        request=httpx.Request("POST", "https://api-m.sandbox.paypal.com/v2/checkout/orders/ORD-UNAPPROVED/capture"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_error_res):
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await client.capture_order("ORD-UNAPPROVED")
        assert exc_info.value.response.status_code == 422
        assert "UNPROCESSABLE_ENTITY" in exc_info.value.response.text

def test_capture_before_approval_rejected_in_route(client):
    """Verifies that attempting to capture an unapproved order in live mode raises 422."""
    from unittest.mock import patch, AsyncMock

    mock_unapproved_order = {
        "id": "ORD-LIVE-UNAPPROVED",
        "status": "CREATED", # Not yet APPROVED
        "links": [{"rel": "approve", "href": "https://sandbox.paypal.com/checkoutnow?token=ORD-LIVE-UNAPPROVED"}],
    }

    with patch("app.core.config.settings.PAYPAL_CLIENT_ID", "live_cid"), \
         patch("app.core.config.settings.PAYPAL_CLIENT_SECRET", "live_secret"), \
         patch("app.services.paypal.client.paypal_client.create_order", new_callable=AsyncMock, return_value=mock_unapproved_order), \
         patch("app.services.paypal.client.paypal_client.get_order", new_callable=AsyncMock, return_value=mock_unapproved_order):

        # 1. Create live order
        create_res = client.post("/api/v1/paypal/orders", json={"amount": 49.99, "customer_ref": "buyer@test.com"})
        assert create_res.status_code == 200
        order_id = create_res.json()["paypal_order_id"]

        # 2. Attempt capture before buyer approval
        cap_res = client.post(f"/api/v1/paypal/orders/{order_id}/capture")
        assert cap_res.status_code == 422
        assert "cannot be captured because buyer has not approved it" in cap_res.json()["detail"]

def test_capture_after_approval_succeeds_in_route(client):
    """Verifies that capturing an APPROVED order in live mode succeeds and prevents duplicate captures."""
    from unittest.mock import patch, AsyncMock

    mock_created_order = {
        "id": "ORD-LIVE-APPROVED",
        "status": "CREATED",
        "links": [{"rel": "approve", "href": "https://sandbox.paypal.com/checkoutnow?token=ORD-LIVE-APPROVED"}],
    }
    mock_approved_order = {
        "id": "ORD-LIVE-APPROVED",
        "status": "APPROVED",
    }
    mock_capture_success = {
        "id": "ORD-LIVE-APPROVED",
        "status": "COMPLETED",
        "purchase_units": [{"payments": {"captures": [{"id": "CAP-LIVE-100", "status": "COMPLETED"}]}}],
    }

    with patch("app.core.config.settings.PAYPAL_CLIENT_ID", "live_cid"), \
         patch("app.core.config.settings.PAYPAL_CLIENT_SECRET", "live_secret"), \
         patch("app.services.paypal.client.paypal_client.create_order", new_callable=AsyncMock, return_value=mock_created_order), \
         patch("app.services.paypal.client.paypal_client.get_order", new_callable=AsyncMock, return_value=mock_approved_order), \
         patch("app.services.paypal.client.paypal_client.capture_order", new_callable=AsyncMock, return_value=mock_capture_success):

        # 1. Create live order
        create_res = client.post("/api/v1/paypal/orders", json={"amount": 49.99, "customer_ref": "buyer@test.com"})
        assert create_res.status_code == 200
        order_id = create_res.json()["paypal_order_id"]

        # 2. Capture approved order
        cap_res = client.post(f"/api/v1/paypal/orders/{order_id}/capture")
        assert cap_res.status_code == 200
        cap_data = cap_res.json()
        assert cap_data["status"] == "CAPTURED"
        assert cap_data["paypal_capture_id"] == "CAP-LIVE-100"

        # 3. Duplicate capture attempt returns existing state safely
        dup_res = client.post(f"/api/v1/paypal/orders/{order_id}/capture")
        assert dup_res.status_code == 200
        assert dup_res.json()["status"] == "CAPTURED"
        assert "duplicate capture prevented" in dup_res.json()["details"]["message"].lower()

def test_create_order_does_not_invoke_capture(client):
    """Verifies that creating an order returns CREATED status and approval URL without capturing."""
    from unittest.mock import patch, AsyncMock

    mock_created_order = {
        "id": "ORD-LIVE-NEW",
        "status": "CREATED",
        "links": [
            {"rel": "approve", "href": "https://sandbox.paypal.com/checkoutnow?token=ORD-LIVE-NEW"}
        ],
    }

    with patch("app.core.config.settings.PAYPAL_CLIENT_ID", "live_cid"), \
         patch("app.core.config.settings.PAYPAL_CLIENT_SECRET", "live_secret"), \
         patch("app.services.paypal.client.paypal_client.create_order", new_callable=AsyncMock, return_value=mock_created_order):

        res = client.post("/api/v1/paypal/orders", json={"amount": 99.00, "customer_ref": "buyer@test.com"})
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "CREATED"
        assert data["paypal_order_id"] == "ORD-LIVE-NEW"
        assert data["approval_url"] == "https://sandbox.paypal.com/checkoutnow?token=ORD-LIVE-NEW"

        # Verify payment is stored as CREATED and NOT CAPTURED
        p_res = client.get(f"/api/v1/payments/{data['payment_id']}")
        assert p_res.status_code == 200
        assert p_res.json()["status"] == "CREATED"
        assert p_res.json()["paypal_capture_id"] is None



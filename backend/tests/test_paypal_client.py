import uuid
import pytest
from unittest.mock import patch, AsyncMock
from decimal import Decimal
import httpx
from app.services.paypal.client import PayPalClient, validate_created_order_amount
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
        json={
            "id": "ORDER-LIVE-999",
            "status": "CREATED",
            "purchase_units": [{
                "reference_id": "default",
                "amount": {"currency_code": "USD", "value": "49.99"},
                "payee": {"merchant_id": "SANDBOX-MERCHANT-1", "email_address": "seller@example.test"},
            }],
            "links": [{"rel": "approve", "href": "https://sandbox.paypal.com/checkoutnow?token=ORDER-LIVE-999"}],
        },
        request=httpx.Request("POST", "https://api-m.sandbox.paypal.com/v2/checkout/orders"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_res) as post:
        res = await client.create_order(amount=Decimal("49.99"), currency="USD", custom_id="pay-123")
        assert res["id"] == "ORDER-LIVE-999"
        assert res["purchase_units"][0]["payee"]["merchant_id"] == "SANDBOX-MERCHANT-1"
        sent_body = post.await_args.kwargs["json"]
        assert sent_body["purchase_units"][0]["amount"] == {
            "currency_code": "USD",
            "value": "49.99",
        }
        assert post.await_args.kwargs["headers"]["Prefer"] == "return=representation"

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

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_res) as post:
        res = await client.capture_order("ORDER-LIVE-999", idempotency_key="payment-1")
        assert res["status"] == "COMPLETED"
        assert post.await_args.kwargs["headers"]["Prefer"] == "return=representation"
        assert post.await_args.kwargs["headers"]["PayPal-Request-Id"] == "payment-1"

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


def test_safe_paypal_error_diagnostics_excludes_message_and_sensitive_fields():
    from app.services.paypal.client import safe_paypal_error_diagnostics

    response = httpx.Response(
        422,
        json={
            "name": "UNPROCESSABLE_ENTITY",
            "debug_id": "DEBUG-123",
            "message": "Sensitive response text with buyer email and access token",
            "details": [{
                "issue": "UNSUPPORTED_PAYEE_CURRENCY",
                "description": "Do not include this full detail in logs",
                "checkout_url": "https://www.sandbox.paypal.com/checkoutnow?token=secret",
            }],
        },
        request=httpx.Request("POST", "https://api-m.sandbox.paypal.com/v2/checkout/orders"),
    )
    response.raise_for_status = lambda: None
    error = httpx.HTTPStatusError("provider error", request=response.request, response=response)

    diagnostics = safe_paypal_error_diagnostics(error)
    assert diagnostics == {
        "http_status": 422,
        "error_name": "UNPROCESSABLE_ENTITY",
        "debug_id": "DEBUG-123",
        "issues": ["UNSUPPORTED_PAYEE_CURRENCY"],
    }
    assert "Sensitive response text" not in repr(diagnostics)
    assert "checkout_url" not in repr(diagnostics)

def test_capture_before_approval_rejected_in_route(client):
    """Verifies that attempting to capture an unapproved order in live mode raises 422."""
    from unittest.mock import patch, AsyncMock

    mock_unapproved_order = {
        "id": "ORD-LIVE-UNAPPROVED",
        "status": "CREATED", # Not yet APPROVED
        "purchase_units": [{"amount": {"currency_code": "USD", "value": "49.99"}}],
        "links": [{"rel": "approve", "href": "https://sandbox.paypal.com/checkoutnow?token=ORD-LIVE-UNAPPROVED"}],
    }

    with patch("app.core.config.settings.PAYPAL_CLIENT_ID", "sandbox_cid"), \
         patch("app.core.config.settings.PAYPAL_CLIENT_SECRET", "sandbox_secret"), \
         patch("app.services.paypal.client.paypal_client.create_order", new_callable=AsyncMock, return_value=mock_unapproved_order), \
         patch("app.services.paypal.client.paypal_client.get_order", new_callable=AsyncMock, return_value=mock_unapproved_order), \
         patch("app.services.paypal.client.paypal_client.capture_order", new_callable=AsyncMock) as capture:

        # 1. Create live order
        create_res = client.post("/api/v1/paypal/orders", json={"amount": 49.99, "customer_ref": "buyer@test.com"})
        assert create_res.status_code == 200
        order_id = create_res.json()["paypal_order_id"]

        # 2. Attempt capture before buyer approval
        cap_res = client.post(f"/api/v1/paypal/orders/{order_id}/capture")
        assert cap_res.status_code == 422
        assert "cannot be captured because buyer has not approved it" in cap_res.json()["detail"]
        capture.assert_not_awaited()

def test_capture_after_approval_succeeds_in_route(client):
    """Verifies that capturing an APPROVED order in live mode succeeds and prevents duplicate captures."""
    from unittest.mock import patch, AsyncMock

    mock_created_order = {
        "id": "ORD-LIVE-APPROVED",
        "status": "CREATED",
        "purchase_units": [{"amount": {"currency_code": "USD", "value": "49.99"}}],
        "links": [{"rel": "approve", "href": "https://sandbox.paypal.com/checkoutnow?token=ORD-LIVE-APPROVED"}],
    }
    mock_approved_order = {
        "id": "ORD-LIVE-APPROVED",
        "status": "APPROVED",
    }
    mock_capture_success = {
        "id": "ORD-LIVE-APPROVED",
        "status": "COMPLETED",
        "purchase_units": [{"payments": {"captures": [{"id": "CAP-LIVE-100", "status": "COMPLETED", "amount": {"currency_code": "USD", "value": "49.99"}, "final_capture": True}]}}],
    }

    with patch("app.core.config.settings.PAYPAL_CLIENT_ID", "sandbox_cid"), \
         patch("app.core.config.settings.PAYPAL_CLIENT_SECRET", "sandbox_secret"), \
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
        timeline = client.get(f"/api/v1/payments/{cap_data['payment_id']}/timeline").json()
        completed_event = next(event for event in timeline["events"] if event["event_type"] == "CAPTURE_COMPLETED")
        assert completed_event["metadata_redacted"]["capture_status"] == "COMPLETED"
        assert completed_event["metadata_redacted"]["capture_amount"] == "49.99"
        assert completed_event["metadata_redacted"]["capture_currency"] == "USD"

        # 3. Duplicate capture attempt returns existing state safely
        dup_res = client.post(f"/api/v1/paypal/orders/{order_id}/capture")
        assert dup_res.status_code == 200
        assert dup_res.json()["status"] == "CAPTURED"
        assert "duplicate capture prevented" in dup_res.json()["details"]["message"].lower()


def test_simulated_order_requires_approval_before_capture(client):
    create_res = client.post("/api/v1/paypal/orders", json={"amount": 19.99})
    assert create_res.status_code == 200
    order_id = create_res.json()["paypal_order_id"]
    assert create_res.json()["is_mock"] is True

    denied = client.post(f"/api/v1/paypal/orders/{order_id}/capture")
    assert denied.status_code == 422

    approved = client.post(f"/api/v1/paypal/orders/{order_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"

    captured = client.post(f"/api/v1/paypal/orders/{order_id}/capture")
    assert captured.status_code == 200
    assert captured.json()["status"] == "CAPTURED"

    duplicate = client.post(f"/api/v1/paypal/orders/{order_id}/capture")
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "CAPTURED"


def test_completed_provider_order_is_reconciled_without_recapture(client):
    from unittest.mock import patch, AsyncMock

    order_id = "ORD-ALREADY-COMPLETED"
    completed_order = {
        "id": order_id,
        "status": "COMPLETED",
        "purchase_units": [{"payments": {"captures": [{"id": "CAP-ALREADY-DONE", "status": "COMPLETED", "amount": {"currency_code": "USD", "value": "15.00"}, "final_capture": True}]}}],
    }
    with patch("app.core.config.settings.PAYPAL_CLIENT_ID", "sandbox-client"), \
         patch("app.core.config.settings.PAYPAL_CLIENT_SECRET", "sandbox-secret"), \
         patch("app.services.paypal.client.paypal_client.create_order", new_callable=AsyncMock, return_value={"id": order_id, "status": "CREATED", "purchase_units": [{"amount": {"currency_code": "USD", "value": "15.00"}}], "links": []}), \
         patch("app.services.paypal.client.paypal_client.get_order", new_callable=AsyncMock, return_value=completed_order), \
         patch("app.services.paypal.client.paypal_client.capture_order", new_callable=AsyncMock) as capture:
        created = client.post("/api/v1/paypal/orders", json={"amount": 15.00})
        assert created.status_code == 200
        response = client.post(f"/api/v1/paypal/orders/{order_id}/capture")

    assert response.status_code == 200
    assert response.json()["status"] == "CAPTURED"
    assert response.json()["paypal_capture_id"] == "CAP-ALREADY-DONE"
    timeline = client.get(f"/api/v1/payments/{created.json()['payment_id']}/timeline").json()
    reconciled_event = next(event for event in timeline["events"] if event["event_type"] == "CAPTURE_RECONCILED")
    assert reconciled_event["metadata_redacted"]["capture_amount"] == "15.00"
    assert reconciled_event["metadata_redacted"]["capture_currency"] == "USD"
    capture.assert_not_awaited()

def test_create_order_does_not_invoke_capture(client):
    """Verifies that creating an order returns CREATED status and approval URL without capturing."""
    from unittest.mock import patch, AsyncMock

    mock_created_order = {
        "id": "ORD-LIVE-NEW",
        "status": "CREATED",
        "purchase_units": [{"amount": {"currency_code": "USD", "value": "99.00"}}],
        "links": [
            {"rel": "approve", "href": "https://sandbox.paypal.com/checkoutnow?token=ORD-LIVE-NEW"}
        ],
    }

    with patch("app.core.config.settings.PAYPAL_CLIENT_ID", "sandbox_cid"), \
         patch("app.core.config.settings.PAYPAL_CLIENT_SECRET", "sandbox_secret"), \
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


def test_order_creation_rejects_currency_other_than_usd(client):
    response = client.post(
        "/api/v1/paypal/orders",
        json={"amount": 49.99, "currency": "EUR"},
    )
    assert response.status_code == 422


def test_order_currency_must_match_provider_order(client):
    from unittest.mock import patch, AsyncMock

    mismatched_provider_order = {
        "id": "ORD-CURRENCY-MISMATCH",
        "status": "CREATED",
        "purchase_units": [{"amount": {"currency_code": "EUR", "value": "49.99"}}],
        "links": [],
    }
    with patch("app.core.config.settings.PAYPAL_CLIENT_ID", "sandbox-client"), \
         patch("app.core.config.settings.PAYPAL_CLIENT_SECRET", "sandbox-secret"), \
         patch("app.services.paypal.client.paypal_client.create_order", new_callable=AsyncMock, return_value=mismatched_provider_order) as create:
        response = client.post("/api/v1/paypal/orders", json={"amount": 49.99, "currency": "USD"})

    assert response.status_code == 502
    assert "currency_mismatch" in response.json()["detail"]
    create.assert_awaited_once()


@pytest.mark.parametrize(
    "response,reason",
    [
        ({"purchase_units": [{"amount": {"currency_code": "EUR", "value": "49.99"}}]}, "currency_mismatch"),
        ({"purchase_units": [{"amount": {"currency_code": "USD", "value": "50.00"}}]}, "amount_mismatch"),
        ({"purchase_units": []}, "expected_one_purchase_unit"),
        ({"id": "ORDER-MINIMAL"}, "expected_one_purchase_unit"),
        ({"purchase_units": "invalid"}, "expected_one_purchase_unit"),
        ({"purchase_units": [{"amount": None}]}, "amount_not_object"),
        ({"purchase_units": ["invalid"]}, "purchase_unit_not_object"),
        ({"purchase_units": [{"amount": {"currency_code": "USD", "value": "not-a-decimal"}}]}, "amount_not_decimal"),
        (None, "response_not_object"),
    ],
)
def test_created_order_validation_rejects_bad_provider_response(response, reason):
    with pytest.raises(ValueError, match=reason):
        validate_created_order_amount(response, Decimal("49.99"), "USD")


def test_created_order_validation_accepts_decimal_equivalent_amount():
    response = {
        "purchase_units": [
            {"amount": {"currency_code": "USD", "value": "49.990"}}
        ]
    }
    validate_created_order_amount(response, Decimal("49.99"), "USD")




def test_completed_order_with_missing_capture_details_fails_closed(client):
    from unittest.mock import patch, AsyncMock
    order_id = "ORD-COMPLETED-MISSING-CAPTURE"
    completed_order = {"id": order_id, "status": "COMPLETED", "purchase_units": [{"payments": {"captures": []}}]}
    with patch("app.core.config.settings.PAYPAL_CLIENT_ID", "sandbox-client"), \
         patch("app.core.config.settings.PAYPAL_CLIENT_SECRET", "sandbox-secret"), \
         patch("app.services.paypal.client.paypal_client.create_order", new_callable=AsyncMock, return_value={"id": order_id, "status": "CREATED", "purchase_units": [{"amount": {"currency_code": "USD", "value": "15.00"}}], "links": []}), \
         patch("app.services.paypal.client.paypal_client.get_order", new_callable=AsyncMock, return_value=completed_order), \
         patch("app.services.paypal.client.paypal_client.capture_order", new_callable=AsyncMock) as capture:
        created = client.post("/api/v1/paypal/orders", json={"amount": 15.00})
        response = client.post(f"/api/v1/paypal/orders/{order_id}/capture")
    assert created.status_code == 200
    assert response.status_code == 502
    assert client.get(f"/api/v1/payments/{created.json()['payment_id']}").json()["status"] == "CREATED"
    capture.assert_not_awaited()


def test_capture_persistence_failure_retries_by_reconciling_without_recapture(client, db_session):
    from unittest.mock import patch, AsyncMock
    order_id = "ORD-COMMIT-RETRY"
    completed_order = {"id": order_id, "status": "COMPLETED", "purchase_units": [{"payments": {"captures": [{"id": "CAP-COMMIT-RETRY", "status": "COMPLETED", "amount": {"currency_code": "USD", "value": "15.00"}}]}}]}
    with patch("app.core.config.settings.PAYPAL_CLIENT_ID", "sandbox-client"), \
         patch("app.core.config.settings.PAYPAL_CLIENT_SECRET", "sandbox-secret"), \
         patch("app.services.paypal.client.paypal_client.create_order", new_callable=AsyncMock, return_value={"id": order_id, "status": "CREATED", "purchase_units": [{"amount": {"currency_code": "USD", "value": "15.00"}}], "links": []}), \
         patch("app.services.paypal.client.paypal_client.get_order", new_callable=AsyncMock, return_value=completed_order), \
         patch("app.services.paypal.client.paypal_client.capture_order", new_callable=AsyncMock) as capture:
        created = client.post("/api/v1/paypal/orders", json={"amount": 15.00})
        with patch.object(db_session, "commit", side_effect=RuntimeError("simulated persistence failure")):
            failed_save = client.post(f"/api/v1/paypal/orders/{order_id}/capture")
        assert failed_save.status_code == 503
        # SQLite test sessions share one outer transaction; recreate the payment
        # that production had already committed before the capture transaction failed.
        recreated = client.post("/api/v1/paypal/orders", json={"amount": 15.00})
        response = client.post(f"/api/v1/paypal/orders/{order_id}/capture")
    assert recreated.status_code == 200
    assert response.status_code == 200
    assert response.json()["paypal_capture_id"] == "CAP-COMMIT-RETRY"
    assert client.get(f"/api/v1/payments/{recreated.json()['payment_id']}").json()["status"] == "CAPTURED"
    capture.assert_not_awaited()


def test_reconcile_after_response_loss_recovers_capture_without_a_second_capture(client):
    """
    Regression test for a critical bug: the "reconcile" call (same endpoint the
    frontend's "Reconcile with PayPal" button uses, with simulate_timeout omitted)
    used to fall through CAPTURE_UNCERTAIN's safety branch and execute a second real
    capture — the exact blind-retry double-charge this status exists to prevent.
    """
    create_res = client.post(
        "/api/v1/paypal/orders",
        json={"amount": 42.00, "currency": "USD", "customer_ref": "reconcile_test_buyer"},
    )
    assert create_res.status_code == 200
    order_id = create_res.json()["paypal_order_id"]
    payment_id = create_res.json()["payment_id"]

    client.post(f"/api/v1/paypal/orders/{order_id}/approve")

    # The demo performs the mock provider capture, then discards the response.
    timeout_res = client.post(
        f"/api/v1/paypal/orders/{order_id}/capture",
        json={"simulate_timeout": True},
    )
    assert timeout_res.status_code == 200
    timeout_data = timeout_res.json()
    assert timeout_data["status"] == "CAPTURE_UNCERTAIN"
    assert timeout_data["paypal_capture_id"] is None

    # Operator clicks "Reconcile with PayPal" (same endpoint, no simulate_timeout flag).
    reconcile_res = client.post(f"/api/v1/paypal/orders/{order_id}/capture")
    assert reconcile_res.status_code == 200
    reconcile_data = reconcile_res.json()

    # Provider reconciliation must recover the original capture ID rather than issue another capture.
    assert reconcile_data["status"] == "CAPTURED"
    assert reconcile_data["reconciliation_required"] is False
    first_capture_id = reconcile_data["paypal_capture_id"]
    assert first_capture_id

    # Local state is reconciled from provider evidence.
    payment = client.get(f"/api/v1/payments/{payment_id}").json()
    assert payment["status"] == "CAPTURED"

    # Reconciling again (e.g. the operator clicks it twice) must be stably idempotent.
    second_reconcile_res = client.post(f"/api/v1/paypal/orders/{order_id}/capture")
    assert second_reconcile_res.status_code == 200
    assert second_reconcile_res.json()["status"] == "CAPTURED"
    assert second_reconcile_res.json()["paypal_capture_id"] == first_capture_id

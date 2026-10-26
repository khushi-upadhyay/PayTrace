import httpx
import logging
from typing import Optional, Dict, Any, Tuple
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta
from app.core.config import settings
from app.core.security import redact_sensitive_data

logger = logging.getLogger(__name__)


def validate_created_order_amount(
    order_data: Any,
    requested_amount: Decimal,
    requested_currency: str,
) -> None:
    """Validate the sole purchase unit against the exact amount sent to PayPal."""
    requested_value = f"{requested_amount:.2f}"
    returned_currency = None
    returned_value = None
    reason = None

    if not isinstance(order_data, dict):
        reason = "response_not_object"
    else:
        purchase_units = order_data.get("purchase_units")
        if not isinstance(purchase_units, list) or len(purchase_units) != 1:
            reason = "expected_one_purchase_unit"
        elif not isinstance(purchase_units[0], dict):
            reason = "purchase_unit_not_object"
        else:
            returned_amount = purchase_units[0].get("amount")
            if not isinstance(returned_amount, dict):
                reason = "amount_not_object"
            else:
                returned_currency = returned_amount.get("currency_code")
                returned_value = returned_amount.get("value")
                if returned_currency != requested_currency:
                    reason = "currency_mismatch"
                elif not isinstance(returned_value, (str, int, Decimal)) or isinstance(returned_value, bool):
                    reason = "amount_missing_or_invalid"
                else:
                    try:
                        parsed_returned = Decimal(str(returned_value))
                        parsed_requested = Decimal(requested_value)
                        if not parsed_returned.is_finite():
                            reason = "amount_not_finite"
                        elif parsed_returned != parsed_requested:
                            reason = "amount_mismatch"
                    except (InvalidOperation, ValueError):
                        reason = "amount_not_decimal"

    if reason:
        safe_returned_value = (
            returned_value
            if isinstance(returned_value, (str, int, Decimal)) and not isinstance(returned_value, bool)
            else None
        )
        safe_returned_currency = returned_currency if isinstance(returned_currency, str) else None
        logger.warning(
            "PayPal order amount validation failed: requested_amount=%s requested_currency=%s "
            "returned_amount=%s returned_currency=%s reason=%s",
            requested_value,
            requested_currency,
            safe_returned_value,
            safe_returned_currency,
            reason,
        )
        raise ValueError(f"PayPal order amount validation failed ({reason})")


def safe_paypal_error_diagnostics(error: httpx.HTTPStatusError) -> Dict[str, Any]:
    """Extract only PayPal's non-sensitive error identifiers and issue codes."""
    try:
        payload = error.response.json()
    except (ValueError, TypeError):
        payload = None

    if not isinstance(payload, dict):
        payload = {}

    details = payload.get("details")
    issues = []
    if isinstance(details, list):
        issues = [
            item["issue"][:80]
            for item in details
            if isinstance(item, dict) and isinstance(item.get("issue"), str)
        ][:10]

    error_name = payload.get("name")
    debug_id = payload.get("debug_id")
    return {
        "http_status": error.response.status_code,
        "error_name": error_name[:80] if isinstance(error_name, str) else None,
        "debug_id": debug_id[:80] if isinstance(debug_id, str) else None,
        "issues": issues,
    }

class PayPalClient:
    """Client for interacting with real PayPal Sandbox REST API."""

    def __init__(self):
        self._token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

    @property
    def base_url(self) -> str:
        return "https://api-m.sandbox.paypal.com" if settings.paypal_mode == "sandbox" else "https://api-m.paypal.com"

    async def get_access_token(self) -> str:
        """Acquires and caches PayPal OAuth2 token safely."""
        if self._token and self._token_expires_at and datetime.utcnow() < self._token_expires_at:
            return self._token

        if not settings.PAYPAL_CLIENT_ID or not settings.PAYPAL_CLIENT_SECRET:
            raise ValueError("PayPal Client ID and Secret are not configured.")

        auth = (settings.PAYPAL_CLIENT_ID.strip(), settings.PAYPAL_CLIENT_SECRET.strip())
        headers = {"Accept": "application/json", "Accept-Language": "en_US"}
        data = {"grant_type": "client_credentials"}

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/v1/oauth2/token",
                    auth=auth,
                    headers=headers,
                    data=data,
                )
                response.raise_for_status()
                payload = response.json()
                self._token = payload["access_token"]
                expires_in = int(payload.get("expires_in", 3600))
                # Cache token until 60 seconds before expiry
                self._token_expires_at = datetime.utcnow() + timedelta(seconds=max(expires_in - 60, 60))
                return self._token
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error acquiring PayPal access token: {e.response.status_code} - {e.response.text}")
                raise
            except httpx.HTTPError as e:
                logger.error(f"Network error acquiring PayPal access token: {e}")
                raise

    async def create_order(
        self,
        amount: Decimal,
        currency: str = "USD",
        custom_id: str = "",
        return_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Creates a PayPal order via v2/checkout/orders with server-validated amount."""
        token = await self.get_access_token()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            # PayPal defaults to return=minimal, which omits purchase_units and amount.
            "Prefer": "return=representation",
        }
        body = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "custom_id": custom_id,
                    "amount": {
                        "currency_code": currency,
                        "value": f"{amount:.2f}",
                    },
                    "description": "PayTrace Sandbox Transaction",
                }
            ],
            "application_context": {
                "user_action": "PAY_NOW",
                "return_url": return_url or f"{settings.FRONTEND_ORIGIN}/checkout?status=approved",
                "cancel_url": cancel_url or f"{settings.FRONTEND_ORIGIN}/checkout?status=cancelled",
            },
        }

        async with httpx.AsyncClient(timeout=12.0) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/v2/checkout/orders",
                    headers=headers,
                    json=body,
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error("PayPal create_order HTTP error status=%s", e.response.status_code)
                raise
            except httpx.HTTPError as e:
                logger.error("PayPal create_order network error type=%s", type(e).__name__)
                raise

    async def get_order(self, order_id: str) -> Dict[str, Any]:
        """Retrieves provider order details for reconciliation."""
        token = await self.get_access_token()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/v2/checkout/orders/{order_id}",
                    headers=headers,
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(
                    f"PayPal get_order HTTP error {e.response.status_code} for order {order_id}: {e.response.text}"
                )
                raise
            except httpx.HTTPError as e:
                logger.error(f"PayPal get_order network error for order {order_id}: {e}")
                raise

    async def capture_order(
        self, order_id: str, idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """Captures an approved PayPal order with a stable retry key when provided."""
        token = await self.get_access_token()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "Prefer": "return=representation",
        }
        if idempotency_key:
            headers["PayPal-Request-Id"] = idempotency_key
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/v2/checkout/orders/{order_id}/capture",
                    headers=headers,
                    json={},
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(
                    f"PayPal capture_order HTTP error {e.response.status_code} for order {order_id}: {e.response.text}"
                )
                raise
            except httpx.HTTPError as e:
                logger.error(f"PayPal capture_order network error for order {order_id}: {e}")
                raise

    async def refund_capture(self, capture_id: str, amount: Optional[Decimal] = None, currency: str = "USD", note: str = "") -> Dict[str, Any]:
        """Executes refund through server-side policy check."""
        token = await self.get_access_token()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        body: Dict[str, Any] = {"note_to_payer": note or "Refund processed via PayTrace"}
        if amount is not None:
            body["amount"] = {
                "value": f"{amount:.2f}",
                "currency_code": currency,
            }

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/v2/payments/captures/{capture_id}/refund",
                    headers=headers,
                    json=body,
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(
                    f"PayPal refund_capture HTTP error {e.response.status_code} for capture {capture_id}: {e.response.text}"
                )
                raise
            except httpx.HTTPError as e:
                logger.error(f"PayPal refund_capture network error for capture {capture_id}: {e}")
                raise

    async def verify_webhook_signature(
        self,
        headers: Dict[str, str],
        raw_body: bytes,
    ) -> bool:
        """Verifies PayPal webhook signature via official API."""
        if not settings.PAYPAL_WEBHOOK_ID:
            logger.warning("PAYPAL_WEBHOOK_ID is not configured, skipping verification.")
            return False

        token = await self.get_access_token()
        auth_algo = headers.get("paypal-auth-algo", "")
        cert_url = headers.get("paypal-cert-url", "")
        transmission_id = headers.get("paypal-transmission-id", "")
        transmission_sig = headers.get("paypal-transmission-sig", "")
        transmission_time = headers.get("paypal-transmission-time", "")

        try:
            import json
            webhook_event = json.loads(raw_body.decode("utf-8"))
        except Exception as e:
            logger.error(f"Failed to parse webhook JSON body for verification: {e}")
            return False

        verification_body = {
            "auth_algo": auth_algo,
            "cert_url": cert_url,
            "transmission_id": transmission_id,
            "transmission_sig": transmission_sig,
            "transmission_time": transmission_time,
            "webhook_id": settings.PAYPAL_WEBHOOK_ID.strip(),
            "webhook_event": webhook_event,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/v1/notifications/verify-webhook-signature",
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
                    json=verification_body,
                )
                if response.status_code == 200 and response.json().get("verification_status") == "SUCCESS":
                    return True
                logger.warning(f"PayPal webhook verification rejected: status={response.status_code}, response={response.text}")
            except Exception as e:
                logger.error(f"Error during PayPal webhook verification: {e}")
        return False

paypal_client = PayPalClient()

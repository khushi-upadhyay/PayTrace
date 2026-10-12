import httpx
import logging
from typing import Optional, Dict, Any, Tuple
from decimal import Decimal
from datetime import datetime, timedelta
from app.core.config import settings
from app.core.security import redact_sensitive_data

logger = logging.getLogger(__name__)

class PayPalClient:
    """Client for interacting with real PayPal Sandbox REST API."""

    def __init__(self):
        self.base_url = "https://api-m.sandbox.paypal.com" if settings.PAYPAL_ENVIRONMENT == "sandbox" else "https://api-m.paypal.com"
        self._token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

    async def get_access_token(self) -> str:
        """Acquires and caches PayPal OAuth2 token safely."""
        if self._token and self._token_expires_at and datetime.utcnow() < self._token_expires_at:
            return self._token

        if not settings.PAYPAL_CLIENT_ID or not settings.PAYPAL_CLIENT_SECRET:
            raise ValueError("PayPal Client ID and Secret are not configured.")

        auth = (settings.PAYPAL_CLIENT_ID, settings.PAYPAL_CLIENT_SECRET)
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
                self._token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in - 60)
                return self._token
            except httpx.HTTPError as e:
                logger.error(f"Failed to acquire PayPal access token: {e}")
                raise

    async def create_order(self, amount: Decimal, currency: str = "USD", custom_id: str = "") -> Dict[str, Any]:
        """Creates a PayPal order via v2/checkout/orders."""
        token = await self.get_access_token()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
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
                    "description": "PayTrace Demo Transaction",
                }
            ],
            "application_context": {
                "user_action": "PAY_NOW",
                "return_url": f"{settings.FRONTEND_ORIGIN}/checkout?status=success",
                "cancel_url": f"{settings.FRONTEND_ORIGIN}/checkout?status=cancel",
            },
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.base_url}/v2/checkout/orders",
                headers=headers,
                json=body,
            )
            response.raise_for_status()
            return response.json()

    async def get_order(self, order_id: str) -> Dict[str, Any]:
        """Retrieves provider order details for reconciliation."""
        token = await self.get_access_token()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{self.base_url}/v2/checkout/orders/{order_id}",
                headers=headers,
            )
            response.raise_for_status()
            return response.json()

    async def capture_order(self, order_id: str) -> Dict[str, Any]:
        """Captures an approved PayPal order."""
        token = await self.get_access_token()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{self.base_url}/v2/checkout/orders/{order_id}/capture",
                headers=headers,
                json={},
            )
            response.raise_for_status()
            return response.json()

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
            response = await client.post(
                f"{self.base_url}/v2/payments/captures/{capture_id}/refund",
                headers=headers,
                json=body,
            )
            response.raise_for_status()
            return response.json()

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

        verification_body = {
            "auth_algo": auth_algo,
            "cert_url": cert_url,
            "transmission_id": transmission_id,
            "transmission_sig": transmission_sig,
            "transmission_time": transmission_time,
            "webhook_id": settings.PAYPAL_WEBHOOK_ID,
            "webhook_event": httpx.Response(200, content=raw_body).json(),
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
            except Exception as e:
                logger.error(f"Error during PayPal webhook verification: {e}")
        return False

paypal_client = PayPalClient()

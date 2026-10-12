import uuid
from decimal import Decimal
from typing import Dict, Any, Optional
from datetime import datetime

class MockPayPalSandbox:
    """High-fidelity PayPal Sandbox Simulator for credential-less local testing and demo scenarios."""

    def __init__(self):
        # In-memory store for simulated orders and captures
        self.orders: Dict[str, Dict[str, Any]] = {}
        self.captures: Dict[str, Dict[str, Any]] = {}

    def create_order(self, amount: Decimal, currency: str = "USD", custom_id: str = "") -> Dict[str, Any]:
        order_id = f"MOCK-ORD-{uuid.uuid4().hex[:12].upper()}"
        order_data = {
            "id": order_id,
            "status": "CREATED",
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "custom_id": custom_id,
                    "amount": {
                        "currency_code": currency,
                        "value": f"{amount:.2f}",
                    },
                }
            ],
            "create_time": datetime.utcnow().isoformat() + "Z",
            "links": [
                {
                    "href": f"http://localhost:3000/checkout?orderId={order_id}&status=approved",
                    "rel": "approve",
                    "method": "GET"
                }
            ]
        }
        self.orders[order_id] = order_data
        return order_data

    def get_order(self, order_id: str) -> Dict[str, Any]:
        if order_id in self.orders:
            return self.orders[order_id]
        # Return default synthesized order
        return {
            "id": order_id,
            "status": "APPROVED",
            "intent": "CAPTURE",
            "purchase_units": [{"amount": {"currency_code": "USD", "value": "49.99"}}],
        }

    def capture_order(self, order_id: str, simulate_scenario: Optional[str] = None) -> Dict[str, Any]:
        capture_id = f"MOCK-CAP-{uuid.uuid4().hex[:12].upper()}"
        
        if simulate_scenario == "capture_denied":
            return {
                "id": order_id,
                "status": "COMPLETED",
                "payment_source": {"paypal": {}},
                "purchase_units": [
                    {
                        "payments": {
                            "captures": [
                                {
                                    "id": capture_id,
                                    "status": "DECLINED",
                                    "status_details": {
                                        "reason": "INSTRUMENT_DECLINED"
                                    }
                                }
                            ]
                        }
                    }
                ]
            }

        # Successful capture at provider
        capture_payload = {
            "id": order_id,
            "status": "COMPLETED",
            "purchase_units": [
                {
                    "payments": {
                        "captures": [
                            {
                                "id": capture_id,
                                "status": "COMPLETED",
                                "amount": {"currency_code": "USD", "value": "49.99"},
                                "create_time": datetime.utcnow().isoformat() + "Z",
                            }
                        ]
                    }
                }
            ]
        }
        self.captures[capture_id] = capture_payload
        if order_id in self.orders:
            self.orders[order_id]["status"] = "COMPLETED"
        return capture_payload

    def create_mock_webhook(
        self,
        event_type: str,
        order_id: Optional[str] = None,
        capture_id: Optional[str] = None,
        amount: Decimal = Decimal("49.99"),
        currency: str = "USD",
        custom_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generates realistic PayPal webhook structure."""
        event_id = f"WH-{uuid.uuid4().hex[:16].upper()}"
        now_str = datetime.utcnow().isoformat() + "Z"
        
        resource: Dict[str, Any] = {
            "id": capture_id or order_id or f"RES-{uuid.uuid4().hex[:8].upper()}",
            "create_time": now_str,
            "update_time": now_str,
            "amount": {
                "currency_code": currency,
                "value": f"{amount:.2f}"
            }
        }
        if custom_id:
            resource["custom_id"] = custom_id

        if "CAPTURE" in event_type:
            resource_type = "capture"
            resource["status"] = "COMPLETED" if "COMPLETED" in event_type else "DENIED"
        else:
            resource_type = "checkout-order"
            resource["status"] = "APPROVED"

        return {
            "id": event_id,
            "event_version": "1.0",
            "create_time": now_str,
            "resource_type": resource_type,
            "event_type": event_type,
            "summary": f"PayPal Webhook Notification: {event_type}",
            "resource": resource
        }

mock_paypal = MockPayPalSandbox()

import uuid
from decimal import Decimal
from typing import Dict, Any, Optional
from datetime import datetime
from app.core.time import utc_now

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
            "create_time": utc_now().isoformat() + "Z",
            "links": [
                {
                    "href": f"http://localhost:3000/demo/approval?token={order_id}&return_to=checkout",
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
        raise KeyError(order_id)

    def approve_order(self, order_id: str) -> Dict[str, Any]:
        order = self.orders.get(order_id)
        if not order:
            raise KeyError(order_id)
        if order.get("status") == "CREATED":
            order["status"] = "APPROVED"
        return order

    def capture_order(self, order_id: str, simulate_scenario: Optional[str] = None) -> Dict[str, Any]:
        capture_id = f"MOCK-CAP-{uuid.uuid4().hex[:12].upper()}"
        order = self.orders.get(order_id)
        if not order:
            raise KeyError(order_id)
        order_amount = order["purchase_units"][0]["amount"]

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
                                    "amount": dict(order_amount),
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
                                "amount": dict(order_amount),
                                "create_time": utc_now().isoformat() + "Z",
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

mock_paypal = MockPayPalSandbox()

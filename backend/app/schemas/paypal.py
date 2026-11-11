from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from decimal import Decimal

class OrderCreateRequest(BaseModel):
    amount: Decimal = Field(default=Decimal("49.99"), ge=0.01, decimal_places=2)
    currency: str = Field(default="USD", pattern="^USD$")
    session_id: Optional[str] = None
    customer_ref: str = Field(default="demo_shopper", max_length=128)
    simulate_scenario: Optional[str] = None # None, "timeout_before_response", "capture_denied"

class OrderCreateResponse(BaseModel):
    payment_id: str
    paypal_order_id: str
    status: str
    approval_url: Optional[str] = None
    is_mock: bool = False
    checkout_token: Optional[str] = None

class OrderCaptureRequest(BaseModel):
    simulate_timeout: bool = False

class OrderCaptureResponse(BaseModel):
    payment_id: str
    paypal_order_id: str
    paypal_capture_id: Optional[str] = None
    status: str # CAPTURED, CAPTURE_UNCERTAIN, DENIED
    failure_code: Optional[str] = None
    failure_reason: Optional[str] = None
    reconciliation_required: bool = False
    details: Dict[str, Any] = {}

class RefundRequest(BaseModel):
    amount: Optional[Decimal] = None
    reason: str = Field(default="Customer requested refund", max_length=512)

class RefundResponse(BaseModel):
    ticket_id: Optional[str] = None
    status: str # PENDING_APPROVAL, EXECUTED, DENIED
    message: str

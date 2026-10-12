from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime
from decimal import Decimal

class PaymentBase(BaseModel):
    amount: Decimal
    currency: str = "USD"
    customer_ref: str = "anon_buyer"
    actor: str = "human"
    source_mode: str = "PAYPAL_SANDBOX"

class PaymentCreate(PaymentBase):
    session_id: Optional[str] = None

class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    paypal_order_id: Optional[str] = None
    paypal_capture_id: Optional[str] = None
    customer_ref: str
    session_id: Optional[str] = None
    amount: Decimal
    currency: str
    status: str
    failure_code: Optional[str] = None
    failure_reason: Optional[str] = None
    actor: str
    source_mode: str
    created_at: datetime
    updated_at: datetime

class PaymentListResponse(BaseModel):
    items: List[PaymentResponse]
    total: int
    page: int
    page_size: int

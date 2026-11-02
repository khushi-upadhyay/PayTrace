from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, Literal
from datetime import datetime
from decimal import Decimal

DisputeReason = Literal[
    "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
    "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED",
    "UNAUTHORIZED",
    "CREDIT_NOT_PROCESSED",
    "DUPLICATE_TRANSACTION",
    "OTHER",
]

DisputeStatus = Literal[
    "OPEN",
    "UNDER_REVIEW",
    "RESOLVED_SELLER_FAVOUR",
    "RESOLVED_BUYER_FAVOUR",
    "CLOSED",
]


class DisputeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    payment_id: str
    paypal_dispute_id: str
    reason: str
    status: str
    amount: Decimal
    currency: str
    buyer_statement: Optional[str] = None
    seller_response: Optional[str] = None
    outcome_note: Optional[str] = None
    is_simulated: bool
    opened_at: datetime
    response_due_by: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class DisputeListResponse(BaseModel):
    items: list[DisputeResponse]
    total: int


class DisputeSimulateRequest(BaseModel):
    """Triggers a clearly-labelled simulated dispute against an existing payment. Operator-only."""
    payment_id: str = Field(..., min_length=1, max_length=36)
    reason: DisputeReason = "MERCHANDISE_OR_SERVICE_NOT_RECEIVED"
    buyer_statement: Optional[str] = Field(default=None, max_length=1024)


class DisputeRespondRequest(BaseModel):
    """Submits the merchant's response/evidence to an open dispute. Operator-only."""
    seller_response: str = Field(..., min_length=1, max_length=1024)
    accept_liability: bool = False

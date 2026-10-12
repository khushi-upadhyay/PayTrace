from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
from decimal import Decimal

class ApprovalTicketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    payment_id: str
    action_type: str
    amount: Optional[Decimal] = None
    currency: str
    reason: str
    status: str
    requested_by: str
    decided_by: Optional[str] = None
    decided_at: Optional[datetime] = None
    paypal_result_redacted: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

class ApprovalDecisionRequest(BaseModel):
    decision: str # APPROVED or DENIED
    operator_token: Optional[str] = None
    notes: Optional[str] = None

class ApprovalDecisionResponse(BaseModel):
    ticket_id: str
    decision: str
    status: str
    message: str
    execution_result: Optional[Dict[str, Any]] = None

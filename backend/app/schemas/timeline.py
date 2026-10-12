from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime

class PaymentEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    payment_id: str
    event_type: str
    source: str
    status: str
    occurred_at: datetime
    received_at: datetime
    latency_ms: Optional[int] = None
    paypal_order_id: Optional[str] = None
    paypal_capture_id: Optional[str] = None
    metadata_redacted: Dict[str, Any]
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    is_simulated: bool

class TimelineResponse(BaseModel):
    payment_id: str
    current_status: str
    events: List[PaymentEventResponse]
    total_events: int
    duration_ms: Optional[int] = None

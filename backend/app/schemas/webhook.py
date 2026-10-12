from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime

class WebhookIngestResponse(BaseModel):
    status: str # PROCESSED, IGNORED_DUPLICATE, UNMATCHED, VERIFICATION_FAILED
    webhook_event_id: str
    event_type: str
    payment_id: Optional[str] = None
    message: str

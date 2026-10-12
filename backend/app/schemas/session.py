from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime

class SessionCreateRequest(BaseModel):
    visitor_ref: str = "anon_visitor"
    user_agent: Optional[str] = None
    metadata: Dict[str, Any] = {}

class SessionEventItem(BaseModel):
    event_type: str
    occurred_at: Optional[datetime] = None
    payload: Dict[str, Any] = {}

class SessionEventsBatchRequest(BaseModel):
    events: List[SessionEventItem]

class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    visitor_ref: str
    payment_id: Optional[str] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    user_agent: Optional[str] = None
    recording_enabled: bool

class SessionReplayResponse(BaseModel):
    session_id: str
    payment_id: Optional[str] = None
    visitor_ref: str
    events: List[Dict[str, Any]]
    total_events: int

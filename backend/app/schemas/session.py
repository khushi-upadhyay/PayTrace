from pydantic import BaseModel, ConfigDict, Field, field_serializer
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime, timezone
from uuid import UUID

class SessionCreateRequest(BaseModel):
    session_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    visitor_ref: str = Field(default="anon_visitor", max_length=128)
    user_agent: Optional[str] = Field(default=None, max_length=1024)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class SessionEventItem(BaseModel):
    id: Optional[UUID] = None
    event_type: str = Field(max_length=64)
    category: Optional[Literal["replay", "network", "console", "lifecycle", "payment", "application"]] = None
    source: Literal["browser", "sdk", "backend", "provider"] = "browser"
    tab_id: Optional[str] = Field(default=None, max_length=64)
    segment_id: Optional[str] = Field(default=None, max_length=64)
    occurred_at: Optional[datetime] = None
    session_offset_ms: Optional[int] = Field(default=None, ge=0)
    route: Optional[str] = Field(default=None, max_length=512)
    payment_id: Optional[str] = Field(default=None, max_length=36)
    order_id: Optional[str] = Field(default=None, max_length=64)
    severity: Optional[str] = Field(default=None, max_length=16)
    trace_id: Optional[str] = Field(default=None, max_length=64)
    attributes: Dict[str, Any] = Field(default_factory=dict)
    payload: Dict[str, Any] = Field(default_factory=dict)

class SessionEventsBatchRequest(BaseModel):
    events: List[SessionEventItem] = Field(min_length=1, max_length=500)

class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    visitor_ref: str
    payment_id: Optional[str] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    user_agent: Optional[str] = None
    metadata_redacted: Dict[str, Any] = Field(default_factory=dict)
    recording_enabled: bool

    @field_serializer("started_at", "ended_at", when_used="json")
    def serialize_session_datetimes(self, value: Optional[datetime]) -> Optional[str]:
        if value is None:
            return None
        utc_value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        return utc_value.isoformat().replace("+00:00", "Z")

class SessionReplayResponse(BaseModel):
    session_id: str
    payment_id: Optional[str] = None
    payment_ids: List[str] = Field(default_factory=list)
    visitor_ref: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    user_agent: Optional[str] = None
    metadata_redacted: Dict[str, Any] = Field(default_factory=dict)
    events: List[Dict[str, Any]]
    total_events: int
    returned_events: int = 0
    rrweb_events: int = 0
    investigation_events: int = 0
    offset: int = 0
    limit: int = 500
    has_more: bool = False
    payment_events: List[Dict[str, Any]] = Field(default_factory=list)

    @field_serializer("started_at", "ended_at", when_used="json")
    def serialize_session_datetimes(self, value: Optional[datetime]) -> Optional[str]:
        if value is None:
            return None
        utc_value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        return utc_value.isoformat().replace("+00:00", "Z")

class SessionListItem(BaseModel):
    id: str
    visitor_ref: str
    payment_id: Optional[str] = None
    payment_ids: List[str] = Field(default_factory=list)
    started_at: datetime
    ended_at: Optional[datetime] = None
    recording_enabled: bool
    events_count: int
    user_agent: Optional[str] = None
    metadata_redacted: Dict[str, Any] = Field(default_factory=dict)

    @field_serializer("started_at", "ended_at", when_used="json")
    def serialize_session_datetimes(self, value: Optional[datetime]) -> Optional[str]:
        if value is None:
            return None
        utc_value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        return utc_value.isoformat().replace("+00:00", "Z")

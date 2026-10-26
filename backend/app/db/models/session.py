import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Index, JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, Dict, Any, List
from app.db.base import Base
from app.core.time import utc_now

class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    visitor_ref: Mapped[str] = mapped_column(String(128), default="anon_visitor")
    payment_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("payments.id", ondelete="SET NULL"), nullable=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    metadata_redacted: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    recording_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    events: Mapped[List["SessionEvent"]] = relationship("SessionEvent", back_populates="session", cascade="all, delete-orphan", order_by="SessionEvent.occurred_at")

class SessionEvent(Base):
    __tablename__ = "session_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    event_type: Mapped[str] = mapped_column(String(64)) # rrweb_chunk, click, input, checkout_start, error
    category: Mapped[str] = mapped_column(String(32), default="application", index=True)
    source: Mapped[str] = mapped_column(String(16), default="browser")
    tab_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    segment_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    session_offset_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    route: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    payment_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    order_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    severity: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    trace_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    payload_redacted: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    session: Mapped["Session"] = relationship("Session", back_populates="events")

    __table_args__ = (
        Index("ix_session_events_session_occurred", "session_id", "occurred_at"),
        Index("ix_session_events_session_tab_occurred", "session_id", "tab_id", "occurred_at"),
        Index("ix_session_events_session_category_occurred", "session_id", "category", "occurred_at"),
    )

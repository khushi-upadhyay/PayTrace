import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, Dict, Any, List
from app.db.base import Base

class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    visitor_ref: Mapped[str] = mapped_column(String(128), default="anon_visitor")
    payment_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("payments.id", ondelete="SET NULL"), nullable=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    metadata_redacted: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    recording_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    events: Mapped[List["SessionEvent"]] = relationship("SessionEvent", back_populates="session", cascade="all, delete-orphan", order_by="SessionEvent.occurred_at")

class SessionEvent(Base):
    __tablename__ = "session_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    event_type: Mapped[str] = mapped_column(String(64)) # rrweb_chunk, click, input, checkout_start, error
    payload_redacted: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    session: Mapped["Session"] = relationship("Session", back_populates="events")

    __table_args__ = (
        Index("ix_session_events_session_occurred", "session_id", "occurred_at"),
    )

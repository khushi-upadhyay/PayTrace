import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, Dict, Any
from app.db.base import Base
from app.core.time import utc_now

class PaymentEvent(Base):
    __tablename__ = "payment_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    payment_id: Mapped[str] = mapped_column(String(36), ForeignKey("payments.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(32)) # FRONTEND, PAYPAL_API, PAYPAL_WEBHOOK, POLICY_ENGINE, SIMULATED
    status: Mapped[str] = mapped_column(String(32), default="SUCCESS") # SUCCESS, FAILED, PENDING, UNCERTAIN
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    paypal_order_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    paypal_capture_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    metadata_redacted: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    trace_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    span_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)

    payment: Mapped["Payment"] = relationship("Payment", back_populates="events")

    __table_args__ = (
        Index("ix_payment_events_payment_occurred", "payment_id", "occurred_at"),
    )

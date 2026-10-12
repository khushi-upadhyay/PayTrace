import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, Dict, Any
from app.db.base import Base
from app.core.time import utc_now

class PayPalWebhook(Base):
    __tablename__ = "paypal_webhooks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    webhook_event_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    resource_type: Mapped[str] = mapped_column(String(64), default="capture")
    payment_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("payments.id", ondelete="SET NULL"), nullable=True, index=True)
    payload_redacted: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    processing_status: Mapped[str] = mapped_column(String(32), default="PROCESSED") # PROCESSED, IGNORED_DUPLICATE, FAILED_VERIFICATION, UNMATCHED
    processing_error: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    signature_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    payment: Mapped[Optional["Payment"]] = relationship("Payment", back_populates="webhooks")

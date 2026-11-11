import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Numeric, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional
from app.db.base import Base
from app.core.time import utc_now

# Dispute lifecycle, modelled after PayPal's Customer Disputes API states.
DISPUTE_STATUSES = (
    "OPEN",
    "UNDER_REVIEW",
    "RESOLVED_SELLER_FAVOUR",
    "RESOLVED_BUYER_FAVOUR",
    "CLOSED",
)
DISPUTE_REASONS = (
    "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
    "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED",
    "UNAUTHORIZED",
    "CREDIT_NOT_PROCESSED",
    "DUPLICATE_TRANSACTION",
    "OTHER",
)


class Dispute(Base):
    __tablename__ = "disputes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    payment_id: Mapped[str] = mapped_column(String(36), ForeignKey("payments.id", ondelete="CASCADE"), index=True)
    paypal_dispute_id: Mapped[str] = mapped_column(String(64), unique=True)
    reason: Mapped[str] = mapped_column(String(64), default="OTHER")
    status: Mapped[str] = mapped_column(String(32), default="OPEN", index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    buyer_statement: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    seller_response: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    outcome_note: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    is_simulated: Mapped[bool] = mapped_column(default=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    response_due_by: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    payment: Mapped["Payment"] = relationship("Payment", back_populates="disputes")

    __table_args__ = (
        Index("ix_disputes_paypal_dispute_id", "paypal_dispute_id"),
        Index("ix_disputes_status_opened_at", "status", "opened_at"),
    )

import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Numeric, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, List
from app.db.base import Base
from app.core.time import utc_now

class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    paypal_order_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True, index=True, nullable=True)
    paypal_capture_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    customer_ref: Mapped[str] = mapped_column(String(128), default="anon_buyer")
    session_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    status: Mapped[str] = mapped_column(String(32), default="CREATED", index=True)
    failure_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    failure_reason: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    actor: Mapped[str] = mapped_column(String(32), default="human") # human, agent, demo
    source_mode: Mapped[str] = mapped_column(String(32), default="PAYPAL_SANDBOX") # PAYPAL_SANDBOX, PAYPAL_LIVE, SIMULATED
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    events: Mapped[List["PaymentEvent"]] = relationship("PaymentEvent", back_populates="payment", cascade="all, delete-orphan", order_by="PaymentEvent.occurred_at")
    webhooks: Mapped[List["PayPalWebhook"]] = relationship("PayPalWebhook", back_populates="payment")
    approvals: Mapped[List["ApprovalTicket"]] = relationship("ApprovalTicket", back_populates="payment", cascade="all, delete-orphan")
    investigations: Mapped[List["AIInvestigation"]] = relationship("AIInvestigation", back_populates="payment")
    disputes: Mapped[List["Dispute"]] = relationship("Dispute", back_populates="payment", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_payments_status_created_at", "status", "created_at"),
    )

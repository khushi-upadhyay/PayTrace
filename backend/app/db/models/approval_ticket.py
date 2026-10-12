import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Numeric, DateTime, ForeignKey, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, Dict, Any
from app.db.base import Base
from app.core.time import utc_now

class ApprovalTicket(Base):
    __tablename__ = "approval_tickets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    payment_id: Mapped[str] = mapped_column(String(36), ForeignKey("payments.id", ondelete="CASCADE"), index=True)
    action_type: Mapped[str] = mapped_column(String(32), default="REFUND") # REFUND, CANCEL, MANUAL_RECONCILE
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    reason: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32), default="PENDING", index=True) # PENDING, APPROVED, DENIED, EXECUTED, FAILED
    requested_by: Mapped[str] = mapped_column(String(64), default="AI_INVESTIGATOR")
    decided_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    paypal_result_redacted: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    payment: Mapped["Payment"] = relationship("Payment", back_populates="approvals")

    __table_args__ = (
        Index("ix_approval_tickets_status_created", "status", "created_at"),
    )

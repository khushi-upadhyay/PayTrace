import uuid
from datetime import datetime
from sqlalchemy import String, Float, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, Dict, Any, List
from app.db.base import Base

class AIInvestigation(Base):
    __tablename__ = "ai_investigations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    payment_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("payments.id", ondelete="CASCADE"), nullable=True, index=True)
    incident_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=True, index=True)
    question: Mapped[str] = mapped_column(String(512), default="Investigate payment outcome and root cause")
    root_cause: Mapped[str] = mapped_column(String(512))
    confidence: Mapped[float] = mapped_column(Float, default=0.8)
    severity: Mapped[str] = mapped_column(String(32), default="MEDIUM") # LOW, MEDIUM, HIGH, CRITICAL
    facts: Mapped[List[str]] = mapped_column(JSON, default=list)
    inferences: Mapped[List[str]] = mapped_column(JSON, default=list)
    customer_impact: Mapped[str] = mapped_column(String(1024))
    business_impact: Mapped[str] = mapped_column(String(1024))
    recommendation: Mapped[str] = mapped_column(String(1024))
    evidence_event_ids: Mapped[List[str]] = mapped_column(JSON, default=list)
    is_incident_likely: Mapped[bool] = mapped_column(Boolean, default=False)
    insufficient_evidence: Mapped[bool] = mapped_column(Boolean, default=False)
    model_name: Mapped[str] = mapped_column(String(64), default="deterministic-rule-engine-v1")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    payment: Mapped[Optional["Payment"]] = relationship("Payment", back_populates="investigations")
    incident: Mapped[Optional["Incident"]] = relationship("Incident", back_populates="investigations")

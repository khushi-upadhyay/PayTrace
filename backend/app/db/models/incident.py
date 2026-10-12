import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Numeric, DateTime, Integer, Float, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, List
from app.db.base import Base

class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(256))
    severity: Mapped[str] = mapped_column(String(32), default="MEDIUM") # LOW, MEDIUM, HIGH, CRITICAL
    status: Mapped[str] = mapped_column(String(32), default="OPEN") # OPEN, INVESTIGATING, RESOLVED
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    affected_payment_count: Mapped[int] = mapped_column(Integer, default=0)
    revenue_at_risk: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    detection_rule: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    root_cause: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ai_summary: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    investigations: Mapped[List["AIInvestigation"]] = relationship("AIInvestigation", back_populates="incident")

    __table_args__ = (
        Index("ix_incidents_status_severity_started", "status", "severity", "started_at"),
    )

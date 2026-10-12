from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime
from decimal import Decimal
from app.schemas.payment import PaymentResponse

class IncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    severity: str
    status: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    affected_payment_count: int
    revenue_at_risk: Decimal
    currency: str
    detection_rule: Optional[str] = None
    root_cause: Optional[str] = None
    confidence: Optional[float] = None
    ai_summary: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class IncidentDetailResponse(IncidentResponse):
    affected_payments: List[PaymentResponse] = []

class IncidentListResponse(BaseModel):
    items: List[IncidentResponse]
    total: int

class IncidentReportResponse(BaseModel):
    incident_id: str
    title: str
    severity: str
    status: str
    affected_payments_count: int
    revenue_at_risk: Decimal
    currency: str
    detection_rule: Optional[str] = None
    executive_summary: str
    detailed_findings: List[str]
    timeline_analysis: str
    recommended_mitigations: List[str]
    generated_at: datetime

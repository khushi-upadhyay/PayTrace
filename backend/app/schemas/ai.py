from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class AIInvestigationRequest(BaseModel):
    payment_id: Optional[str] = None
    incident_id: Optional[str] = None
    question: str = "Investigate payment outcome, uncertainty, and root cause"

class AIInvestigationResponse(BaseModel):
    id: Optional[str] = None
    payment_id: Optional[str] = None
    incident_id: Optional[str] = None
    root_cause: str
    confidence: float = Field(ge=0.0, le=1.0)
    severity: str # LOW, MEDIUM, HIGH, CRITICAL
    facts: List[str] = []
    inferences: List[str] = []
    customer_impact: str
    business_impact: str
    recommendation: str
    evidence_event_ids: List[str] = []
    is_incident_likely: bool = False
    insufficient_evidence: bool = False
    model_name: str = "deterministic-rule-engine-v1"
    created_at: Optional[datetime] = None
    comparison_notes: Optional[str] = None
    workflow_nodes: List[str] = []
    tool_calls: List[str] = []
    execution_mode: str = "deterministic_fallback"
    langsmith_tracing_enabled: bool = False

class AIChatMessage(BaseModel):
    role: str # user, assistant, system
    content: str

class AIChatRequest(BaseModel):
    payment_id: Optional[str] = None
    incident_id: Optional[str] = None
    messages: List[AIChatMessage]
    question: Optional[str] = None

class AIChatResponse(BaseModel):
    response: str
    grounded_facts: List[str] = []
    recommended_action: Optional[str] = None
    evidence_event_ids: List[str] = []
    workflow_nodes: List[str] = []
    tool_calls: List[str] = []
    execution_mode: str = "deterministic_fallback"
    langsmith_tracing_enabled: bool = False
    provider_facts: List[str] = []
    investigation_summary: Optional[str] = None
    answer_mode: str = "evidence_fallback"
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    model_status: str = "not_configured"
    fallback_reason: Optional[str] = None

from pydantic import BaseModel
from typing import Optional, Dict, Any, List

class DemoScenarioRequest(BaseModel):
    scenario: str # "timeout_before_response", "capture_denied", "delayed_webhook", "duplicate_webhook_replay", "high_latency"
    parameters: Dict[str, Any] = {}

class DemoScenarioResponse(BaseModel):
    scenario: str
    payment_id: Optional[str] = None
    title: str
    description: str
    status: str
    details: Dict[str, Any] = {}

class DemoResetResponse(BaseModel):
    success: bool
    message: str
    payments_seeded: int
    incidents_seeded: int

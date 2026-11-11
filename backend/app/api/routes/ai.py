from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_user, get_db
from app.db.models.user import User
from app.schemas.ai import (
    AIInvestigationRequest,
    AIInvestigationResponse,
    AIChatRequest,
    AIChatResponse,
)
from app.agents.investigator import ai_investigator

router = APIRouter(prefix="/ai", tags=["AI Investigator"])

@router.post("/investigate", response_model=AIInvestigationResponse)
async def investigate_payment(req: AIInvestigationRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    Executes cross-signal AI investigation over payment and session facts,
    returning structured findings, confidence score, facts vs inferences,
    and recommended next actions with safe fallback.
    """
    response = await ai_investigator.investigate(
        db=db,
        payment_id=req.payment_id,
        incident_id=req.incident_id,
        question=req.question,
    )
    return response

@router.post("/chat", response_model=AIChatResponse)
async def chat_with_investigator(req: AIChatRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Provides evidence-grounded follow-up answers to operator inquiries."""
    messages_dict = [m.model_dump() for m in req.messages]
    result = await ai_investigator.chat(
        db=db,
        payment_id=req.payment_id,
        incident_id=req.incident_id,
        messages=messages_dict,
        question=req.question,
    )
    return AIChatResponse(
        response=result["response"],
        grounded_facts=result.get("grounded_facts", []),
        recommended_action=result.get("recommended_action"),
        evidence_event_ids=result.get("evidence_event_ids", []),
        workflow_nodes=result.get("workflow_nodes", []),
        tool_calls=result.get("tool_calls", []),
        execution_mode=result.get("execution_mode", "deterministic_fallback"),
        langsmith_tracing_enabled=result.get("langsmith_tracing_enabled", False),
        provider_facts=result.get("provider_facts", []),
        investigation_summary=result.get("investigation_summary"),
        answer_mode=result.get("answer_mode", "evidence_fallback"),
        model_provider=result.get("model_provider"),
        model_name=result.get("model_name"),
        model_status=result.get("model_status", "not_configured"),
        fallback_reason=result.get("fallback_reason"),
    )

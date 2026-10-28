from fastapi import APIRouter, Depends, HTTPException
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
    if not req.payment_id and not req.incident_id:
        raise HTTPException(status_code=400, detail="Must provide payment_id or incident_id to investigate")

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
    )

import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List
from app.core.audit import audit
from app.api.dependencies import get_current_user, get_db
from app.db.models.approval_ticket import ApprovalTicket
from app.db.models.user import User
from app.schemas.approval import (
    ApprovalTicketResponse,
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
)
from app.services.policy.engine import policy_engine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/approvals", tags=["Approvals"])

@router.get("", response_model=List[ApprovalTicketResponse])
def list_approvals(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Lists pending and decided financial action approval tickets."""
    tickets = db.query(ApprovalTicket).order_by(ApprovalTicket.created_at.desc()).all()
    return [ApprovalTicketResponse.model_validate(t) for t in tickets]

@router.post("/{ticket_id}/decision", response_model=ApprovalDecisionResponse)
async def decide_approval_ticket(
    ticket_id: str,
    req: ApprovalDecisionRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Executes or denies an approval ticket through human-in-the-loop review.
    Ensures refunds and sensitive actions cannot bypass human confirmation.
    """
    try:
        ticket, exec_result = await policy_engine.decide_ticket(
            db=db,
            ticket_id=ticket_id,
            decision=req.decision,
            decided_by=user.email,
            operator_token=req.operator_token,
            notes=req.notes,
        )
        audit("approval_decision", request, user=user.id, ticket=ticket_id, decision=req.decision, status=ticket.status)
        return ApprovalDecisionResponse(
            ticket_id=ticket.id,
            decision=req.decision,
            status=ticket.status,
            message=f"Ticket {ticket.id} successfully marked as {ticket.status}",
            execution_result=exec_result,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.error(f"Approval execution failed for ticket {ticket_id}", exc_info=True)
        raise HTTPException(status_code=500, detail="Execution error. See server logs for details.")

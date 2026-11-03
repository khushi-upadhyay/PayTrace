from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from app.core.audit import audit
from app.api.dependencies import get_current_user, get_db
from app.db.models.user import User
from app.db.models.dispute import Dispute
from app.schemas.dispute import (
    DisputeResponse,
    DisputeListResponse,
    DisputeSimulateRequest,
    DisputeRespondRequest,
)
from app.services.disputes.engine import dispute_engine, DisputeError

router = APIRouter(prefix="/disputes", tags=["Disputes"])


@router.get("", response_model=DisputeListResponse)
def list_disputes(
    status: str | None = Query(None, max_length=32),
    limit: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Lists disputes, most recently opened first. All disputes in this sandbox are simulated."""
    q = db.query(Dispute)
    if status:
        q = q.filter(Dispute.status == status)
    items = q.order_by(Dispute.opened_at.desc()).limit(limit).all()
    total = q.count()
    return DisputeListResponse(
        items=[DisputeResponse.model_validate(d) for d in items],
        total=total,
    )


@router.get("/{dispute_id}", response_model=DisputeResponse)
def get_dispute(dispute_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    dispute = db.query(Dispute).filter(Dispute.id == dispute_id).first()
    if not dispute:
        raise HTTPException(status_code=404, detail=f"Dispute {dispute_id} not found")
    return DisputeResponse.model_validate(dispute)


@router.post("/simulate", response_model=DisputeResponse)
def simulate_dispute(
    req: DisputeSimulateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Opens a clearly-labelled simulated dispute against a captured payment."""
    try:
        dispute = dispute_engine.simulate_dispute(
            db=db,
            payment_id=req.payment_id,
            reason=req.reason,
            buyer_statement=req.buyer_statement,
            requested_by=user.email,
        )
    except DisputeError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return DisputeResponse.model_validate(dispute)


@router.post("/{dispute_id}/respond", response_model=DisputeResponse)
def respond_to_dispute(
    dispute_id: str,
    req: DisputeRespondRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Submits the merchant's evidence/response to an open dispute."""
    try:
        dispute = dispute_engine.respond_to_dispute(
            db=db,
            dispute_id=dispute_id,
            seller_response=req.seller_response,
            accept_liability=req.accept_liability,
            decided_by=user.email,
        )
    except DisputeError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    audit("dispute_response", request, user=user.id, dispute=dispute_id, accept_liability=req.accept_liability)
    return DisputeResponse.model_validate(dispute)


@router.get("/by-payment/{payment_id}", response_model=DisputeListResponse)
def list_disputes_for_payment(
    payment_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Returns every dispute (open or resolved) linked to a given payment."""
    items = (
        db.query(Dispute)
        .filter(Dispute.payment_id == payment_id)
        .order_by(Dispute.opened_at.desc())
        .all()
    )
    return DisputeListResponse(
        items=[DisputeResponse.model_validate(d) for d in items],
        total=len(items),
    )

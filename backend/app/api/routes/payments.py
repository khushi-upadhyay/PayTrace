from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional
from app.api.dependencies import get_db
from app.db.models.payment import Payment
from app.schemas.payment import PaymentResponse, PaymentListResponse
from app.schemas.timeline import TimelineResponse, PaymentEventResponse
from app.services.lifecycle.engine import lifecycle_engine

router = APIRouter(prefix="/payments", tags=["Payments"])

@router.get("", response_model=PaymentListResponse)
def list_payments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    source_mode: Optional[str] = None,
    actor: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Lists payments with search, pagination, and multi-field filters."""
    query = db.query(Payment)

    if status:
        query = query.filter(Payment.status == status)
    if source_mode:
        query = query.filter(Payment.source_mode == source_mode)
    if actor:
        query = query.filter(Payment.actor == actor)
    if search:
        search_fmt = f"%{search}%"
        query = query.filter(
            or_(
                Payment.id.ilike(search_fmt),
                Payment.paypal_order_id.ilike(search_fmt),
                Payment.paypal_capture_id.ilike(search_fmt),
                Payment.customer_ref.ilike(search_fmt),
                Payment.failure_code.ilike(search_fmt),
                Payment.failure_reason.ilike(search_fmt),
            )
        )

    total = query.count()
    items = (
        query.order_by(Payment.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return PaymentListResponse(
        items=[PaymentResponse.model_validate(p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
    )

@router.get("/{payment_id}", response_model=PaymentResponse)
def get_payment(payment_id: str, db: Session = Depends(get_db)):
    """Retrieves full details of a single payment."""
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail=f"Payment {payment_id} not found")
    return PaymentResponse.model_validate(payment)

@router.get("/{payment_id}/timeline", response_model=TimelineResponse)
def get_payment_timeline(payment_id: str, db: Session = Depends(get_db)):
    """Retrieves unified, chronological lifecycle event timeline."""
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail=f"Payment {payment_id} not found")

    events = lifecycle_engine.get_timeline(db, payment_id)

    duration_ms = None
    if len(events) >= 2:
        start = events[0].occurred_at
        end = events[-1].occurred_at
        duration_ms = int((end - start).total_seconds() * 1000)

    return TimelineResponse(
        payment_id=payment.id,
        current_status=payment.status,
        events=[PaymentEventResponse.model_validate(e) for e in events],
        total_events=len(events),
        duration_ms=duration_ms,
    )

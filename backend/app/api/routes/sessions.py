from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.api.dependencies import get_db
from app.db.models.session import Session as BrowserSession
from app.db.models.payment import Payment
from app.schemas.session import (
    SessionCreateRequest,
    SessionResponse,
    SessionEventsBatchRequest,
    SessionReplayResponse,
)
from app.services.sessions.recorder import session_recorder

router = APIRouter(prefix="/sessions", tags=["Sessions"])

@router.post("", response_model=SessionResponse)
def create_session(req: SessionCreateRequest, db: Session = Depends(get_db)):
    """Initializes a privacy-masked browser recording session."""
    session = session_recorder.create_session(
        db=db,
        visitor_ref=req.visitor_ref,
        user_agent=req.user_agent,
        metadata=req.metadata,
    )
    return SessionResponse.model_validate(session)

@router.post("/{session_id}/events")
def ingest_session_events(
    session_id: str,
    req: SessionEventsBatchRequest,
    db: Session = Depends(get_db),
):
    """Batches client-side rrweb/interaction events with size bounds and PII redaction."""
    count = session_recorder.add_events(
        db=db,
        session_id=session_id,
        events=[e.model_dump() for e in req.events],
    )
    return {"status": "success", "session_id": session_id, "events_ingested": count}

@router.get("/{session_id}/replay", response_model=SessionReplayResponse)
def get_session_replay(
    session_id: str,
    limit: int = Query(500, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """Retrieves bounded replay events for rrweb player."""
    session = db.query(BrowserSession).filter(BrowserSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    events = session_recorder.get_replay_events(db, session_id, limit=limit)
    return SessionReplayResponse(
        session_id=session.id,
        payment_id=session.payment_id,
        visitor_ref=session.visitor_ref,
        events=events,
        total_events=len(events),
    )

# Payment-linked session helper route
payment_session_router = APIRouter(prefix="/payments", tags=["Sessions"])

@payment_session_router.get("/{payment_id}/session")
def get_payment_session(payment_id: str, db: Session = Depends(get_db)):
    """Retrieves session metadata linked to a payment."""
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail=f"Payment {payment_id} not found")
    if not payment.session_id:
        return {"has_session": False, "session_id": None}

    session = db.query(BrowserSession).filter(BrowserSession.id == payment.session_id).first()
    events_count = len(session.events) if session else 0
    return {
        "has_session": True,
        "session_id": payment.session_id,
        "started_at": session.started_at.isoformat() if session else None,
        "events_count": events_count,
        "recording_enabled": session.recording_enabled if session else False,
    }

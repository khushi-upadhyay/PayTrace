from app.core.rate_limit import rate_limit
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from datetime import timezone
from app.api.dependencies import get_current_user, get_db
from app.db.models.user import User
from app.db.models.session import Session as BrowserSession
from app.db.models.payment import Payment
from app.schemas.session import (
    SessionCreateRequest,
    SessionResponse,
    SessionEventsBatchRequest,
    SessionReplayResponse,
    SessionListItem,
)
from app.db.models.session import SessionEvent
from app.db.models.payment_event import PaymentEvent
from app.services.sessions.recorder import SessionExpiredError, session_recorder

router = APIRouter(prefix="/sessions", tags=["Sessions"])

@router.get("", response_model=list[SessionListItem])
def list_sessions(
    limit: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Returns recent browser sessions with event counts for the replay inbox."""
    rows = (
        db.query(BrowserSession, func.count(SessionEvent.id))
        .outerjoin(SessionEvent, SessionEvent.session_id == BrowserSession.id)
        .group_by(BrowserSession.id)
        .order_by(BrowserSession.started_at.desc())
        .limit(limit)
        .all()
    )
    result = []
    for session, count in rows:
        linked_payments = db.query(Payment.id).filter(Payment.session_id == session.id).all()
        payment_ids = [payment_id for (payment_id,) in linked_payments]
        if session.payment_id and session.payment_id not in payment_ids:
            payment_ids.insert(0, session.payment_id)
        result.append(SessionListItem(
            id=session.id,
            visitor_ref=session.visitor_ref,
            payment_id=payment_ids[0] if payment_ids else None,
            payment_ids=payment_ids,
            started_at=session.started_at,
            ended_at=session.ended_at,
            recording_enabled=session.recording_enabled,
            events_count=count,
            user_agent=session.user_agent,
            metadata_redacted=session.metadata_redacted or {},
        ))
    return result

@router.post("", response_model=SessionResponse, dependencies=[Depends(rate_limit("session-create", 30, 60))])
def create_session(req: SessionCreateRequest, db: Session = Depends(get_db)):
    """Initializes a privacy-masked browser recording session."""
    try:
        session = session_recorder.create_session(
            db=db,
            session_id=req.session_id,
            visitor_ref=req.visitor_ref,
            user_agent=req.user_agent,
            metadata=req.metadata,
        )
    except SessionExpiredError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "session_expired", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    return SessionResponse.model_validate(session)

@router.post("/{session_id}/events", dependencies=[Depends(rate_limit("session-events", 300, 60))])
def ingest_session_events(
    session_id: str,
    req: SessionEventsBatchRequest,
    db: Session = Depends(get_db),
):
    """Batches client-side rrweb/interaction events with size bounds and PII redaction."""
    try:
        count = session_recorder.add_events(
            db=db,
            session_id=session_id,
            events=[e.model_dump() for e in req.events],
        )
    except SessionExpiredError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "session_expired", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message.lower() else 413
        raise HTTPException(status_code=status_code, detail=message) from exc
    return {"status": "success", "session_id": session_id, "events_ingested": count}

@router.post("/{session_id}/stop", status_code=204, dependencies=[Depends(rate_limit("session-stop", 60, 60))])
def stop_session(session_id: str, db: Session = Depends(get_db)):
    if not session_recorder.stop_session(db, session_id):
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

@router.get("/{session_id}/replay", response_model=SessionReplayResponse)
def get_session_replay(
    session_id: str,
    limit: int = Query(500, ge=1, le=500),
    offset: int = Query(0, ge=0),
    tab_id: Optional[str] = Query(default=None, max_length=64),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Returns one bounded page of replay and investigation events with accurate counts."""
    session = db.query(BrowserSession).filter(BrowserSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    event_query = db.query(SessionEvent).filter(SessionEvent.session_id == session_id)
    if tab_id:
        event_query = event_query.filter(SessionEvent.tab_id == tab_id)
    total_events = event_query.count()
    rrweb_events = event_query.filter(SessionEvent.category == "replay").count()
    investigation_events = total_events - rrweb_events
    events = session_recorder.get_replay_events(db, session_id, limit=limit, offset=offset, tab_id=tab_id)
    payment_ids = [payment_id for (payment_id,) in db.query(Payment.id).filter(Payment.session_id == session.id).all()]
    if session.payment_id and session.payment_id not in payment_ids:
        payment_ids.insert(0, session.payment_id)
    payment_event_rows = []
    if payment_ids:
        rows = db.query(PaymentEvent).filter(PaymentEvent.payment_id.in_(payment_ids)).order_by(PaymentEvent.occurred_at.asc(), PaymentEvent.id.asc()).limit(500).all()
        for row in rows:
            occurred_at = row.occurred_at
            occurred_at = occurred_at.replace(tzinfo=timezone.utc) if occurred_at.tzinfo is None else occurred_at.astimezone(timezone.utc)
            payment_event_rows.append({
                "id": f"payment:{row.id}",
                "session_id": session.id,
                "tab_id": None,
                "event_type": row.event_type,
                "category": "payment",
                "source": row.source.lower(),
                "occurred_at": occurred_at.isoformat().replace("+00:00", "Z"),
                "received_at": (row.received_at.replace(tzinfo=timezone.utc) if row.received_at.tzinfo is None else row.received_at.astimezone(timezone.utc)).isoformat().replace("+00:00", "Z"),
                "session_offset_ms": None,
                "route": None,
                "payment_id": row.payment_id,
                "order_id": row.paypal_order_id,
                "severity": "error" if row.status in {"FAILED", "UNCERTAIN"} else "info",
                "trace_id": row.trace_id,
                "payload": {"name": row.event_type, "status": row.status, "latency_ms": row.latency_ms, **(row.metadata_redacted or {})},
            })

    return SessionReplayResponse(
        session_id=session.id,
        payment_id=payment_ids[0] if payment_ids else None,
        payment_ids=payment_ids,
        visitor_ref=session.visitor_ref,
        started_at=session.started_at,
        ended_at=session.ended_at,
        user_agent=session.user_agent,
        metadata_redacted=session.metadata_redacted or {},
        events=events,
        total_events=total_events,
        returned_events=len(events),
        rrweb_events=rrweb_events,
        investigation_events=investigation_events,
        offset=offset,
        limit=limit,
        has_more=offset + len(events) < total_events,
        payment_events=payment_event_rows,
    )

# Payment-linked session helper route
payment_session_router = APIRouter(prefix="/payments", tags=["Sessions"])

@payment_session_router.get("/{payment_id}/session")
def get_payment_session(payment_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
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

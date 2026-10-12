import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.db.models.session import Session as BrowserSession, SessionEvent
from app.core.security import redact_sensitive_data

MAX_EVENTS_PER_BATCH = 500
MAX_EVENT_PAYLOAD_SIZE = 100_000 # 100 KB limit per event

class SessionRecorder:
    """Manages browser session recording storage and bounded replay retrieval."""

    @staticmethod
    def create_session(
        db: Session,
        visitor_ref: str = "anon_visitor",
        user_agent: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> BrowserSession:
        session_id = str(uuid.uuid4())
        session = BrowserSession(
            id=session_id,
            visitor_ref=visitor_ref,
            user_agent=user_agent[:256] if user_agent else None,
            metadata_redacted=redact_sensitive_data(metadata or {}),
            started_at=datetime.utcnow(),
            recording_enabled=True,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session

    @staticmethod
    def add_events(
        db: Session,
        session_id: str,
        events: List[Dict[str, Any]],
    ) -> int:
        session = db.query(BrowserSession).filter(BrowserSession.id == session_id).first()
        if not session:
            # Auto-create if not exists
            session = BrowserSession(
                id=session_id,
                started_at=datetime.utcnow(),
                recording_enabled=True,
            )
            db.add(session)
            db.flush()

        added_count = 0
        for ev in events[:MAX_EVENTS_PER_BATCH]:
            event_type = ev.get("event_type", "rrweb_chunk")
            occ_at = ev.get("occurred_at")
            if isinstance(occ_at, str):
                try:
                    occ_at = datetime.fromisoformat(occ_at.replace("Z", "+00:00"))
                except Exception:
                    occ_at = datetime.utcnow()
            elif not isinstance(occ_at, datetime):
                occ_at = datetime.utcnow()

            payload = ev.get("payload", {})
            # Redact client sensitive data
            redacted_payload = redact_sensitive_data(payload)

            session_event = SessionEvent(
                id=str(uuid.uuid4()),
                session_id=session_id,
                event_type=event_type,
                occurred_at=occ_at,
                payload_redacted=redacted_payload,
            )
            db.add(session_event)
            added_count += 1

        db.commit()
        return added_count

    @staticmethod
    def get_replay_events(
        db: Session,
        session_id: str,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        events = (
            db.query(SessionEvent)
            .filter(SessionEvent.session_id == session_id)
            .order_by(SessionEvent.occurred_at.asc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": e.id,
                "event_type": e.event_type,
                "occurred_at": e.occurred_at.isoformat(),
                "payload": e.payload_redacted,
            }
            for e in events
        ]

session_recorder = SessionRecorder()

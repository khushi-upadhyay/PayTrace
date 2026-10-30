import uuid
import json
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.db.models.session import Session as BrowserSession, SessionEvent
from app.core.security import redact_sensitive_data
from app.core.time import utc_now
from app.core.config import settings
from app.db.models.payment import Payment

MAX_EVENTS_PER_BATCH = 500
MAX_EVENT_PAYLOAD_SIZE = 100_000  # 100 KB limit per event
MAX_EVENTS_PER_SESSION = 10_000
MAX_SESSION_METADATA_SIZE = 50_000

class SessionRecorder:
    """Manages browser session recording storage and bounded replay retrieval."""

    @staticmethod
    def create_session(
        db: Session,
        session_id: Optional[str] = None,
        visitor_ref: str = "anon_visitor",
        user_agent: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> BrowserSession:
        try:
            metadata_size = len(json.dumps(metadata or {}, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        except (TypeError, ValueError) as exc:
            raise ValueError("Session metadata is not valid JSON") from exc
        if metadata_size > MAX_SESSION_METADATA_SIZE:
            raise ValueError("Session metadata exceeds the 50 KB limit")
        session_id = session_id or str(uuid.uuid4())
        existing = db.query(BrowserSession).filter(BrowserSession.id == session_id).first()
        now = utc_now()
        if existing:
            if not existing.recording_enabled or (now - existing.last_activity_at).total_seconds() > _session_idle_timeout_seconds():
                existing.recording_enabled = False
                existing.ended_at = existing.ended_at or now
                _record_lifecycle_event(db, session_id, "recording_stopped", existing.ended_at)
                _record_lifecycle_event(db, session_id, "session_ended", existing.ended_at)
                db.commit()
                raise ValueError("Session expired; start a new session")
            existing.last_activity_at = now
            db.commit()
            return existing
        session = BrowserSession(
            id=session_id,
            visitor_ref=visitor_ref,
            user_agent=user_agent[:256] if user_agent else None,
            metadata_redacted=redact_sensitive_data(metadata or {}),
            started_at=now,
            last_activity_at=now,
            recording_enabled=True,
        )
        db.add(session)
        db.flush()
        db.add(SessionEvent(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"paytrace:session:{session_id}:started")),
            session_id=session_id,
            occurred_at=now,
            received_at=now,
            event_type="session_started",
            category="lifecycle",
            source="backend",
            payload_redacted={"name": "session_started"},
        ))
        db.commit()
        db.refresh(session)
        return session

    @staticmethod
    def stop_session(db: Session, session_id: str) -> bool:
        session = db.query(BrowserSession).filter(BrowserSession.id == session_id).first()
        if not session:
            return False
        session.recording_enabled = False
        session.ended_at = session.ended_at or utc_now()
        session.last_activity_at = session.ended_at
        _record_lifecycle_event(db, session_id, "recording_stopped", session.ended_at)
        _record_lifecycle_event(db, session_id, "session_ended", session.ended_at)
        db.commit()
        return True

    @staticmethod
    def add_events(
        db: Session,
        session_id: str,
        events: List[Dict[str, Any]],
    ) -> int:
        batch = events[:MAX_EVENTS_PER_BATCH]
        for ev in batch:
            try:
                payload_size = len(json.dumps({"payload": ev.get("payload", {}), "attributes": ev.get("attributes", {})}, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
            except (TypeError, ValueError) as exc:
                raise ValueError("Session event payload is not valid JSON") from exc
            if payload_size > MAX_EVENT_PAYLOAD_SIZE:
                raise ValueError("Session event payload exceeds the 100 KB limit")

        session = db.query(BrowserSession).filter(BrowserSession.id == session_id).first()
        if not session:
            raise ValueError("Session not found")

        if not session.recording_enabled:
            raise ValueError("Recording is disabled for this session")

        now = utc_now()
        if (now - session.last_activity_at).total_seconds() > _session_idle_timeout_seconds():
            session.recording_enabled = False
            session.ended_at = now
            session.last_activity_at = now
            _record_lifecycle_event(db, session_id, "recording_stopped", now)
            _record_lifecycle_event(db, session_id, "session_ended", now)
            db.commit()
            raise ValueError("Session expired")

        added_count = 0
        event_ids = [str(ev["id"]) for ev in batch if ev.get("id")]
        existing_ids = set()
        if event_ids:
            existing_rows = db.query(SessionEvent.id, SessionEvent.session_id).filter(SessionEvent.id.in_(event_ids)).all()
            if any(existing_session_id != session_id for _, existing_session_id in existing_rows):
                raise ValueError("Session event ID is already assigned to another session")
            existing_ids = {row_id for row_id, _ in existing_rows}

        current_count = db.query(SessionEvent).filter(SessionEvent.session_id == session_id).count()
        new_ids = set()
        for ev in batch:
            raw_id = ev.get("id")
            event_id = str(raw_id) if raw_id else str(uuid.uuid4())
            if event_id not in existing_ids and event_id not in new_ids:
                new_ids.add(event_id)
        if current_count + len(new_ids) > MAX_EVENTS_PER_SESSION:
            raise ValueError("Session event retention limit reached")

        for ev in batch:
            raw_id = ev.get("id")
            event_id = str(raw_id) if raw_id else str(uuid.uuid4())
            if event_id in existing_ids:
                continue
            event_type = ev.get("event_type", "rrweb_chunk")
            occ_at = ev.get("occurred_at")
            timestamp_source = "client"
            if isinstance(occ_at, str):
                try:
                    occ_at = datetime.fromisoformat(occ_at.replace("Z", "+00:00"))
                except ValueError as exc:
                    raise ValueError("Session event timestamp is invalid") from exc
            elif not isinstance(occ_at, datetime):
                occ_at = now
                timestamp_source = "ingestion_fallback"
            if occ_at.tzinfo is not None:
                occ_at = occ_at.astimezone(timezone.utc).replace(tzinfo=None)
            if occ_at.year < 2000 or occ_at > now + timedelta(days=1):
                raise ValueError("Session event timestamp is outside the accepted range")

            payload = ev.get("payload", {})
            # Redact client sensitive data
            redacted_payload = redact_sensitive_data(payload)

            attributes = redact_sensitive_data(ev.get("attributes") or {})
            if timestamp_source != "client":
                attributes["timestamp_source"] = timestamp_source

            payment_id = ev.get("payment_id")
            order_id = ev.get("order_id")
            if payment_id:
                linked_payment = db.query(Payment).filter(Payment.id == payment_id, Payment.session_id == session_id).first()
                if not linked_payment:
                    payment_id = None
            if order_id and not payment_id:
                linked_payment = db.query(Payment).filter(Payment.paypal_order_id == order_id, Payment.session_id == session_id).first()
                if linked_payment:
                    payment_id = linked_payment.id

            session_event = SessionEvent(
                id=event_id,
                session_id=session_id,
                event_type=event_type,
                occurred_at=occ_at,
                received_at=now,
                category=ev.get("category") or _category_for(event_type),
                source=ev.get("source") or "browser",
                tab_id=ev.get("tab_id"),
                segment_id=ev.get("segment_id"),
                session_offset_ms=ev.get("session_offset_ms"),
                route=_safe_route(ev.get("route")),
                payment_id=payment_id,
                order_id=order_id,
                severity=ev.get("severity"),
                trace_id=ev.get("trace_id"),
                payload_redacted=redacted_payload,
            )
            if attributes:
                session_event.payload_redacted = {**session_event.payload_redacted, "attributes": attributes}
            db.add(session_event)
            added_count += 1
            existing_ids.add(event_id)

        session.last_activity_at = now
        db.commit()
        return added_count

    @staticmethod
    def get_replay_events(
        db: Session,
        session_id: str,
        limit: int = 500,
        offset: int = 0,
        categories: Optional[List[str]] = None,
        tab_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        query = db.query(SessionEvent).filter(SessionEvent.session_id == session_id)
        if categories:
            query = query.filter(SessionEvent.category.in_(categories))
        if tab_id:
            query = query.filter(SessionEvent.tab_id == tab_id)
        events = query.order_by(SessionEvent.occurred_at.asc(), SessionEvent.id.asc()).offset(offset).limit(limit).all()
        result = []
        for e in events:
            stored_payload = e.payload_redacted or {}
            payload = dict(stored_payload) if isinstance(stored_payload, dict) else {"value": stored_payload}
            attributes = payload.pop("attributes", {})
            result.append({
                "id": e.id,
                "session_id": e.session_id,
                "tab_id": e.tab_id,
                "segment_id": e.segment_id,
                "event_type": e.event_type,
                "category": e.category,
                "source": e.source,
                "occurred_at": _utc_iso(e.occurred_at),
                "received_at": _utc_iso(e.received_at),
                "session_offset_ms": e.session_offset_ms,
                "route": e.route,
                "payment_id": e.payment_id,
                "order_id": e.order_id,
                "severity": e.severity,
                "trace_id": e.trace_id,
                "attributes": attributes,
                "payload": payload,
            })
        return result


def _category_for(event_type: str) -> str:
    if event_type == "rrweb":
        return "replay"
    if event_type in {"console", "network"}:
        return event_type
    if event_type.startswith(("session_", "tab_", "route_", "visibility_", "recording_")):
        return "lifecycle"
    if event_type.startswith("payment_"):
        return "payment"
    return "application"


def _session_idle_timeout_seconds() -> int:
    return min(86_400, max(60, settings.SESSION_IDLE_TIMEOUT_SECONDS))


def _record_lifecycle_event(db: Session, session_id: str, name: str, occurred_at: datetime) -> None:
    event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"paytrace:session:{session_id}:{name}"))
    if db.query(SessionEvent.id).filter(SessionEvent.id == event_id).first():
        return
    db.add(SessionEvent(
        id=event_id,
        session_id=session_id,
        occurred_at=occurred_at,
        received_at=utc_now(),
        event_type=name,
        category="lifecycle",
        source="backend",
        payload_redacted={"name": name},
    ))


def _utc_iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def _safe_route(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    from urllib.parse import urlsplit
    path = urlsplit(value).path or "/"
    sensitive_id_after = {"payments", "sessions", "incidents", "orders", "customers", "buyers"}
    parts = path.split("/")
    safe_parts = []
    for index, part in enumerate(parts):
        is_email = "@" in part and "." in part
        is_opaque_id = len(part) >= 16 and all(ch.isalnum() or ch in "-_" for ch in part)
        related_id = index > 0 and parts[index - 1].lower() in sensitive_id_after
        safe_parts.append(":id" if related_id or is_email or is_opaque_id else part)
    return "/".join(safe_parts)[:512]

session_recorder = SessionRecorder()

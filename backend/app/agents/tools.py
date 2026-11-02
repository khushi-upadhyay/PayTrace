from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from decimal import Decimal
from app.db.models.payment import Payment
from app.db.models.payment_event import PaymentEvent
from app.db.models.webhook import PayPalWebhook
from app.db.models.session import Session as BrowserSession, SessionEvent
from app.db.models.incident import Incident

class InvestigationEvidenceGatherer:
    """Read-only deterministic tools that extract verified payment and lifecycle facts."""

    @staticmethod
    def get_payment_facts(db: Session, payment_id: str) -> Dict[str, Any]:
        payment = db.query(Payment).filter(Payment.id == payment_id).first()
        if not payment:
            return {"error": "Payment not found"}

        events = (
            db.query(PaymentEvent)
            .filter(PaymentEvent.payment_id == payment_id)
            .order_by(PaymentEvent.occurred_at.asc())
            .all()
        )

        webhooks = (
            db.query(PayPalWebhook)
            .filter(PayPalWebhook.payment_id == payment_id)
            .all()
        )

        session = None
        session_events_count = 0
        session_signals = []
        if payment.session_id:
            session = db.query(BrowserSession).filter(BrowserSession.id == payment.session_id).first()
            session_events_count = db.query(SessionEvent).filter(SessionEvent.session_id == payment.session_id).count()
            recorded = (
                db.query(SessionEvent)
                .filter(SessionEvent.session_id == payment.session_id, SessionEvent.category.in_(["network", "console", "application", "payment"]))
                .order_by(SessionEvent.occurred_at.desc())
                .limit(50)
                .all()
            )
            for event in reversed(recorded):
                payload = event.payload_redacted if isinstance(event.payload_redacted, dict) else {}
                attributes = payload.get("attributes") if isinstance(payload.get("attributes"), dict) else {}
                details = payload if event.category == "network" else {**payload, **attributes} if event.category == "console" else {}
                allowed = ("method", "url", "status", "duration_ms", "outcome", "error_name", "error_message", "level", "message")
                session_signals.append({
                    "id": event.id,
                    "occurred_at": event.occurred_at.isoformat(),
                    "category": event.category,
                    "event_type": event.event_type,
                    "route": event.route,
                    "severity": event.severity,
                    "details": {key: details[key] for key in allowed if key in details and isinstance(details[key], (str, int, float, bool, type(None)))},
                })

        event_types = [e.event_type for e in events]
        max_latency = max([e.latency_ms for e in events if e.latency_ms] or [0])

        order_approved = any("ORDER_APPROVED" in et or "APPROVED" in et for et in event_types)
        capture_requested = any("CAPTURE_REQUEST" in et for et in event_types)
        timed_out = any("TIMEOUT" in et or "UNCERTAIN" in et for et in event_types) or payment.status == "CAPTURE_UNCERTAIN"
        denied = any("DENIED" in et or "DECLINED" in et for et in event_types) or payment.status == "DENIED"

        return {
            "payment_id": payment.id,
            "paypal_order_id": payment.paypal_order_id,
            "paypal_capture_id": payment.paypal_capture_id,
            "amount": float(payment.amount),
            "currency": payment.currency,
            "status": payment.status,
            "failure_code": payment.failure_code,
            "failure_reason": payment.failure_reason,
            "source_mode": payment.source_mode,
            "actor": payment.actor,
            "order_approved": order_approved,
            "capture_requested": capture_requested,
            "timed_out": timed_out,
            "denied": denied,
            "event_count": len(events),
            "events_summary": [
                {
                    "id": e.id,
                    "event_type": e.event_type,
                    "source": e.source,
                    "status": e.status,
                    "latency_ms": e.latency_ms,
                    "occurred_at": e.occurred_at.isoformat(),
                    "is_simulated": e.is_simulated,
                }
                for e in events
            ],
            "webhooks_count": len(webhooks),
            "webhooks_summary": [
                {
                    "event_id": w.webhook_event_id,
                    "event_type": w.event_type,
                    "verified": w.signature_verified,
                }
                for w in webhooks
            ],
            "max_latency_ms": max_latency,
            "has_session_recording": session is not None and session_events_count > 0,
            "session_events_count": session_events_count,
            "session_signals_summary": session_signals,
        }

    @staticmethod
    def get_incident_facts(db: Session, incident_id: str) -> Dict[str, Any]:
        """Build an incident bundle only from persisted incident/payment/session evidence."""
        incident = db.query(Incident).filter(Incident.id == incident_id).first()
        if not incident:
            return {"error": "Incident not found"}
        if incident.detection_rule == "CAPTURE_TIMEOUT_SPIKE":
            query = db.query(Payment).filter(Payment.status == "CAPTURE_UNCERTAIN")
        elif incident.detection_rule == "CAPTURE_DENIAL_RATE_HIGH":
            query = db.query(Payment).filter(Payment.status.in_(["DENIED", "CAPTURE_FAILED"]))
        else:
            query = db.query(Payment).filter(Payment.status != "CAPTURED")
        payments = query.order_by(Payment.created_at.desc()).limit(50).all()
        payment_facts = [InvestigationEvidenceGatherer.get_payment_facts(db, payment.id) for payment in payments]
        evidence_ids = []
        for facts in payment_facts:
            evidence_ids.extend(item["id"] for item in facts.get("events_summary", []) if item.get("id"))
            evidence_ids.extend(item["id"] for item in facts.get("session_signals_summary", []) if item.get("id"))
        return {
            "incident": {
                "id": incident.id, "title": incident.title, "rule": incident.detection_rule,
                "severity": incident.severity, "status": incident.status,
                "started_at": incident.started_at.isoformat() if incident.started_at else None,
                "ended_at": incident.ended_at.isoformat() if incident.ended_at else None,
                "affected_payment_count": incident.affected_payment_count,
                "revenue_at_risk": str(incident.revenue_at_risk), "currency": incident.currency,
                "root_cause": incident.root_cause, "ai_summary": incident.ai_summary,
                "confidence": incident.confidence,
            },
            "affected_payments": payment_facts,
            "evidence_event_ids": list(dict.fromkeys(evidence_ids))[:100],
        }

    @staticmethod
    def find_similar_failures(db: Session, payment_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        payment = db.query(Payment).filter(Payment.id == payment_id).first()
        if not payment or not payment.failure_code:
            return []

        similar = (
            db.query(Payment)
            .filter(Payment.id != payment_id, Payment.failure_code == payment.failure_code)
            .order_by(Payment.created_at.desc())
            .limit(limit)
            .all()
        )

        return [
            {
                "id": p.id,
                "amount": float(p.amount),
                "status": p.status,
                "failure_code": p.failure_code,
                "created_at": p.created_at.isoformat(),
            }
            for p in similar
        ]

    @staticmethod
    def compare_with_successful(db: Session, payment_id: str) -> Optional[Dict[str, Any]]:
        failed_payment = db.query(Payment).filter(Payment.id == payment_id).first()
        if not failed_payment:
            return None

        successful = (
            db.query(Payment)
            .filter(Payment.status == "CAPTURED", Payment.id != payment_id)
            .order_by(Payment.created_at.desc())
            .first()
        )
        if not successful:
            return None

        failed_events = db.query(PaymentEvent).filter(PaymentEvent.payment_id == payment_id).all()
        success_events = db.query(PaymentEvent).filter(PaymentEvent.payment_id == successful.id).all()
        failed_types = [event.event_type for event in failed_events]
        success_types = [event.event_type for event in success_events]
        shared = sorted(set(failed_types).intersection(success_types))
        failed_latency = [event.latency_ms for event in failed_events if event.latency_ms is not None]
        success_latency = [event.latency_ms for event in success_events if event.latency_ms is not None]

        return {
            "successful_payment_id": successful.id,
            "failed_payment_id": failed_payment.id,
            "successful_status": successful.status,
            "failed_status": failed_payment.status,
            "successful_event_types": success_types,
            "failed_event_types": failed_types,
            "shared_event_types": shared,
            "successful_latency_samples_ms": success_latency,
            "failed_latency_samples_ms": failed_latency,
            "key_divergence": (
                f"Observed statuses differ ({failed_payment.status} vs {successful.status}). "
                f"Shared event types: {', '.join(shared) if shared else 'none recorded'}. "
                "Event and webhook differences are included only when present in these stored records."
            ),
        }

evidence_gatherer = InvestigationEvidenceGatherer()

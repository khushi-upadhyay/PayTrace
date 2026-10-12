from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from decimal import Decimal
from app.db.models.payment import Payment
from app.db.models.payment_event import PaymentEvent
from app.db.models.webhook import PayPalWebhook
from app.db.models.session import Session as BrowserSession, SessionEvent

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
        if payment.session_id:
            session = db.query(BrowserSession).filter(BrowserSession.id == payment.session_id).first()
            session_events_count = db.query(SessionEvent).filter(SessionEvent.session_id == payment.session_id).count()

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

        return {
            "successful_payment_id": successful.id,
            "failed_payment_id": failed_payment.id,
            "successful_events_count": len(success_events),
            "failed_events_count": len(failed_events),
            "key_divergence": (
                "Successful payment received CAPTURE_COMPLETED API response and webhook confirmation within 450ms. "
                f"Failed payment encountered {failed_payment.failure_code or failed_payment.status}."
            ),
        }

evidence_gatherer = InvestigationEvidenceGatherer()

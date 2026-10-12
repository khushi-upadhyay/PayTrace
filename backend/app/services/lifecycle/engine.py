import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from app.db.models.payment import Payment
from app.db.models.payment_event import PaymentEvent
from app.core.security import redact_sensitive_data
from app.core.time import utc_now

# Valid state hierarchy / precedence
STATE_PRECEDENCE = {
    "CREATED": 10,
    "APPROVED": 20,
    "CAPTURE_PENDING": 30,
    "CAPTURE_UNCERTAIN": 35,
    "CAPTURED": 40,
    "CAPTURE_FAILED": 40,
    "DENIED": 40,
    "REFUND_PENDING": 50,
    "REFUNDED": 60,
    "DISPUTED": 70,
}

class LifecycleEngine:
    """Manages payment lifecycle transitions, out-of-order safety, and append-only event timelines."""

    @staticmethod
    def record_event(
        db: Session,
        payment: Payment,
        event_type: str,
        source: str,
        status: str = "SUCCESS",
        occurred_at: Optional[datetime] = None,
        latency_ms: Optional[int] = None,
        paypal_order_id: Optional[str] = None,
        paypal_capture_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        is_simulated: bool = False,
    ) -> PaymentEvent:
        now = utc_now()
        occ = occurred_at or now

        # Inherit IDs if not specified
        order_id = paypal_order_id or payment.paypal_order_id
        capture_id = paypal_capture_id or payment.paypal_capture_id

        redacted_meta = redact_sensitive_data(metadata or {})

        event = PaymentEvent(
            id=str(uuid.uuid4()),
            payment_id=payment.id,
            event_type=event_type,
            source=source,
            status=status,
            occurred_at=occ,
            received_at=now,
            latency_ms=latency_ms,
            paypal_order_id=order_id,
            paypal_capture_id=capture_id,
            metadata_redacted=redacted_meta,
            is_simulated=is_simulated or payment.source_mode == "SIMULATED",
        )
        db.add(event)
        return event

    @staticmethod
    def transition_status(
        payment: Payment,
        new_status: str,
        failure_code: Optional[str] = None,
        failure_reason: Optional[str] = None,
    ) -> bool:
        """
        Safely transitions payment status ensuring delayed or out-of-order events
        do not regress final terminal states like CAPTURED or REFUNDED.
        """
        curr_prec = STATE_PRECEDENCE.get(payment.status, 0)
        new_prec = STATE_PRECEDENCE.get(new_status, 0)

        # Do not regress if current state is already CAPTURED, unless moving to REFUND
        if payment.status in ("CAPTURED", "REFUNDED") and new_prec < curr_prec:
            return False

        payment.status = new_status
        if failure_code:
            payment.failure_code = failure_code
        if failure_reason:
            payment.failure_reason = failure_reason
        payment.updated_at = utc_now()
        return True

    @staticmethod
    def get_timeline(db: Session, payment_id: str) -> List[PaymentEvent]:
        """Returns unified chronological events ordered by occurred_at."""
        return (
            db.query(PaymentEvent)
            .filter(PaymentEvent.payment_id == payment_id)
            .order_by(PaymentEvent.occurred_at.asc(), PaymentEvent.received_at.asc())
            .all()
        )

lifecycle_engine = LifecycleEngine()

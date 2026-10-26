import sys
import os
import uuid
from decimal import Decimal
from datetime import datetime, timedelta

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.db.session import SessionLocal
from app.db.models.payment import Payment
from app.db.models.payment_event import PaymentEvent
from app.db.models.webhook import PayPalWebhook
from app.db.models.session import Session as BrowserSession, SessionEvent
from app.db.models.incident import Incident
from app.db.models.approval_ticket import ApprovalTicket
from app.db.models.ai_investigation import AIInvestigation
from app.core.time import utc_now
from sqlalchemy.orm import Session

def run_seed(db: Session):
    """Resets and seeds realistic, labelled demo payments, timelines, and incidents."""
    # Clean previous demo records
    db.query(AIInvestigation).delete()
    db.query(ApprovalTicket).delete()
    db.query(SessionEvent).delete()
    db.query(BrowserSession).delete()
    db.query(PayPalWebhook).delete()
    db.query(PaymentEvent).delete()
    db.query(Incident).delete()
    db.query(Payment).delete()
    db.commit()

    now = utc_now()
    payments_count = 0

    # 1. Successful payments cluster (various products and amounts)
    for i in range(1, 9):
        p_id = str(uuid.uuid4())
        created_time = now - timedelta(days=7 - i, hours=i * 2, minutes=15)
        order_id = f"MOCK-ORD-SUCCESS-{i:03d}"
        capture_id = f"MOCK-CAP-SUCCESS-{i:03d}"
        session_id = str(uuid.uuid4())
        amount = Decimal(str(35.00 + (i * 12.50)))

        payment = Payment(
            id=p_id,
            paypal_order_id=order_id,
            paypal_capture_id=capture_id,
            customer_ref=f"shopper_{i}@example.com",
            session_id=session_id,
            amount=amount,
            currency="USD",
            status="CAPTURED",
            actor="demo",
            source_mode="SIMULATED",
            created_at=created_time,
            updated_at=created_time + timedelta(seconds=2),
        )
        db.add(payment)

        # Timeline
        e1 = PaymentEvent(
            id=str(uuid.uuid4()), payment_id=p_id, event_type="CHECKOUT_ORDER_CREATED",
            source="SIMULATED", status="SUCCESS", occurred_at=created_time, received_at=created_time,
            latency_ms=195, paypal_order_id=order_id, metadata_redacted={"item": f"Product #{i}"}, is_simulated=True
        )
        e2 = PaymentEvent(
            id=str(uuid.uuid4()), payment_id=p_id, event_type="CHECKOUT_ORDER_APPROVED",
            source="FRONTEND", status="SUCCESS", occurred_at=created_time + timedelta(seconds=14),
            received_at=created_time + timedelta(seconds=14), latency_ms=40, paypal_order_id=order_id, is_simulated=True
        )
        e3 = PaymentEvent(
            id=str(uuid.uuid4()), payment_id=p_id, event_type="CAPTURE_COMPLETED",
            source="SIMULATED", status="SUCCESS", occurred_at=created_time + timedelta(seconds=16),
            received_at=created_time + timedelta(seconds=16), latency_ms=380, paypal_order_id=order_id,
            paypal_capture_id=capture_id, metadata_redacted={"status": "COMPLETED"}, is_simulated=True
        )
        db.add_all([e1, e2, e3])
        payments_count += 1

    # 2. CRITICAL SCENARIO: Backend Timeout Before Receiving Capture Response (CAPTURE_UNCERTAIN)
    timeout_pid = "demo-timeout-payment-001"
    timeout_session_id = "demo-session-timeout-001"
    timeout_order_id = "MOCK-ORD-TIMEOUT-001"
    timeout_capture_id = "MOCK-CAP-TIMEOUT-001"
    timeout_time = now - timedelta(minutes=45)

    payment_timeout = Payment(
        id=timeout_pid,
        paypal_order_id=timeout_order_id,
        paypal_capture_id=timeout_capture_id,
        customer_ref="uncertain_shopper@example.com",
        session_id=timeout_session_id,
        amount=Decimal("189.99"),
        currency="USD",
        status="CAPTURE_UNCERTAIN",
        failure_code="TIMEOUT_BEFORE_RESPONSE",
        failure_reason="Merchant backend timed out (HTTP 504 / read timeout >5000ms) while awaiting capture response from PayPal.",
        actor="demo",
        source_mode="SIMULATED",
        created_at=timeout_time,
        updated_at=timeout_time + timedelta(seconds=15),
    )
    db.add(payment_timeout)

    t_e1 = PaymentEvent(
        id=str(uuid.uuid4()), payment_id=timeout_pid, event_type="CHECKOUT_ORDER_CREATED",
        source="SIMULATED", status="SUCCESS", occurred_at=timeout_time, received_at=timeout_time,
        latency_ms=210, paypal_order_id=timeout_order_id, is_simulated=True
    )
    t_e2 = PaymentEvent(
        id=str(uuid.uuid4()), payment_id=timeout_pid, event_type="CHECKOUT_ORDER_APPROVED",
        source="FRONTEND", status="SUCCESS", occurred_at=timeout_time + timedelta(seconds=8),
        received_at=timeout_time + timedelta(seconds=8), latency_ms=45, paypal_order_id=timeout_order_id, is_simulated=True
    )
    t_e3 = PaymentEvent(
        id=str(uuid.uuid4()), payment_id=timeout_pid, event_type="CAPTURE_REQUEST_DISPATCHED",
        source="SIMULATED", status="PENDING", occurred_at=timeout_time + timedelta(seconds=10),
        received_at=timeout_time + timedelta(seconds=10), paypal_order_id=timeout_order_id, is_simulated=True
    )
    t_e4 = PaymentEvent(
        id=str(uuid.uuid4()), payment_id=timeout_pid, event_type="CAPTURE_REQUEST_TIMEOUT",
        source="SIMULATED", status="UNCERTAIN", occurred_at=timeout_time + timedelta(seconds=15),
        received_at=timeout_time + timedelta(seconds=15), latency_ms=5180,
        paypal_order_id=timeout_order_id, paypal_capture_id=timeout_capture_id,
        metadata_redacted={
            "error": "ReadTimeout: merchant backend waited 5.18s with no response",
            "risk": "Provider may have processed capture; blind retry prohibited to avoid duplicate charges.",
        },
        is_simulated=True
    )
    db.add_all([t_e1, t_e2, t_e3, t_e4])
    payments_count += 1

    # Session for timeout payment
    sess_timeout = BrowserSession(
        id=timeout_session_id, visitor_ref="visitor_uncertain_401", payment_id=timeout_pid,
        started_at=timeout_time - timedelta(minutes=2), recording_enabled=True,
        metadata_redacted={"browser": "Chrome 122", "page": "/checkout"}
    )
    db.add(sess_timeout)

    s_ev1 = SessionEvent(
        id=str(uuid.uuid4()), session_id=timeout_session_id, occurred_at=timeout_time - timedelta(seconds=30),
        event_type="item_selection", payload_redacted={"item": "Enterprise Server Plan", "price": 189.99}
    )
    s_ev2 = SessionEvent(
        id=str(uuid.uuid4()), session_id=timeout_session_id, occurred_at=timeout_time - timedelta(seconds=15),
        event_type="paypal_button_click", payload_redacted={"action": "click_paypal_smart_button"}
    )
    s_ev3 = SessionEvent(
        id=str(uuid.uuid4()), session_id=timeout_session_id, occurred_at=timeout_time + timedelta(seconds=15),
        event_type="spinner_stall_detected", payload_redacted={"warning": "Client observed loading spinner for >5s"}
    )
    db.add_all([s_ev1, s_ev2, s_ev3])

    # 3. Denied payment (INSTRUMENT_DECLINED)
    denied_pid = "demo-declined-payment-002"
    denied_order_id = "MOCK-ORD-DECLINED-002"
    denied_capture_id = "MOCK-CAP-DECLINED-002"
    denied_time = now - timedelta(hours=3)

    payment_denied = Payment(
        id=denied_pid,
        paypal_order_id=denied_order_id,
        paypal_capture_id=denied_capture_id,
        customer_ref="declined_shopper@example.com",
        amount=Decimal("74.50"),
        currency="USD",
        status="DENIED",
        failure_code="INSTRUMENT_DECLINED",
        failure_reason="PayPal capture denied: INSTRUMENT_DECLINED by card issuer.",
        actor="demo",
        source_mode="SIMULATED",
        created_at=denied_time,
        updated_at=denied_time + timedelta(seconds=12),
    )
    db.add(payment_denied)

    d_e1 = PaymentEvent(
        id=str(uuid.uuid4()), payment_id=denied_pid, event_type="CHECKOUT_ORDER_CREATED",
        source="SIMULATED", status="SUCCESS", occurred_at=denied_time, received_at=denied_time,
        latency_ms=220, paypal_order_id=denied_order_id, is_simulated=True
    )
    d_e2 = PaymentEvent(
        id=str(uuid.uuid4()), payment_id=denied_pid, event_type="CHECKOUT_ORDER_APPROVED",
        source="FRONTEND", status="SUCCESS", occurred_at=denied_time + timedelta(seconds=7),
        received_at=denied_time + timedelta(seconds=7), latency_ms=50, paypal_order_id=denied_order_id, is_simulated=True
    )
    d_e3 = PaymentEvent(
        id=str(uuid.uuid4()), payment_id=denied_pid, event_type="CAPTURE_DENIED",
        source="SIMULATED", status="FAILED", occurred_at=denied_time + timedelta(seconds=10),
        received_at=denied_time + timedelta(seconds=10), latency_ms=640,
        paypal_order_id=denied_order_id, paypal_capture_id=denied_capture_id,
        metadata_redacted={"decline_code": "INSTRUMENT_DECLINED"}, is_simulated=True
    )
    db.add_all([d_e1, d_e2, d_e3])
    payments_count += 1

    # 4. Refunded Payment with Approval Ticket
    refund_pid = "demo-refunded-payment-003"
    refund_order_id = "MOCK-ORD-REFUND-003"
    refund_capture_id = "MOCK-CAP-REFUND-003"
    refund_time = now - timedelta(hours=8)

    payment_refund = Payment(
        id=refund_pid,
        paypal_order_id=refund_order_id,
        paypal_capture_id=refund_capture_id,
        customer_ref="refund_buyer@example.com",
        amount=Decimal("99.00"),
        currency="USD",
        status="REFUNDED",
        actor="demo",
        source_mode="SIMULATED",
        created_at=refund_time,
        updated_at=refund_time + timedelta(hours=1),
    )
    db.add(payment_refund)

    ticket = ApprovalTicket(
        id="ticket-demo-refund-001",
        payment_id=refund_pid,
        action_type="REFUND",
        amount=Decimal("99.00"),
        currency="USD",
        reason="Duplicate test charge mitigation request",
        status="EXECUTED",
        requested_by="AI_INVESTIGATOR",
        decided_by="Operator Dashboard",
        decided_at=refund_time + timedelta(minutes=50),
        paypal_result_redacted={"status": "COMPLETED", "refund_id": "MOCK-REF-9901"},
        created_at=refund_time + timedelta(minutes=45),
        updated_at=refund_time + timedelta(minutes=50),
    )
    db.add(ticket)
    payments_count += 1

    # 5. Pending Approval Ticket for active demo inbox
    pending_pid = "demo-pending-approval-004"
    payment_pending_refund = Payment(
        id=pending_pid,
        paypal_order_id="MOCK-ORD-PENDING-004",
        paypal_capture_id="MOCK-CAP-PENDING-004",
        customer_ref="complaining_buyer@example.com",
        amount=Decimal("149.00"),
        currency="USD",
        status="CAPTURED",
        actor="demo",
        source_mode="SIMULATED",
        created_at=now - timedelta(hours=2),
    )
    db.add(payment_pending_refund)

    pending_ticket = ApprovalTicket(
        id="ticket-demo-pending-002",
        payment_id=pending_pid,
        action_type="REFUND",
        amount=Decimal("149.00"),
        currency="USD",
        reason="Customer dispute risk: service disruption during checkout session",
        status="PENDING",
        requested_by="AI_INVESTIGATOR",
        created_at=now - timedelta(minutes=30),
    )
    db.add(pending_ticket)
    payments_count += 1

    # 6. Incidents
    inc1 = Incident(
        id="inc-demo-001",
        title="Capture Timeout & Unresolved Backend State Spike",
        severity="HIGH",
        status="OPEN",
        started_at=timeout_time,
        affected_payment_count=1,
        revenue_at_risk=Decimal("189.99"),
        currency="USD",
        detection_rule="CAPTURE_TIMEOUT_SPIKE",
        root_cause="Merchant backend timed out while awaiting PayPal capture confirmation. Orders captured at PayPal but unconfirmed locally.",
        confidence=0.94,
        ai_summary="Detected ambiguous capture states. Merchant backend timed out before receiving the capture response. Automated retries halted to prevent duplicate charges.",
        created_at=timeout_time,
        updated_at=now,
    )
    inc2 = Incident(
        id="inc-demo-002",
        title="Elevated Capture Denial Rate (INSTRUMENT_DECLINED)",
        severity="MEDIUM",
        status="OPEN",
        started_at=denied_time,
        affected_payment_count=1,
        revenue_at_risk=Decimal("74.50"),
        currency="USD",
        detection_rule="CAPTURE_DENIAL_RATE_HIGH",
        root_cause="Spike in buyer instrument declines during order capture.",
        confidence=0.88,
        ai_summary="Multiple checkout captures were declined by the issuer/PayPal. Recommend prompting buyers to select alternate funding methods.",
        created_at=denied_time,
        updated_at=now,
    )
    db.add_all([inc1, inc2])

    db.commit()
    return {"payments": payments_count, "incidents": 2}


def seed_if_empty(db: Session):
    """Seed the demo once on a new database without replacing existing records."""
    models = (
        Payment,
        PaymentEvent,
        PayPalWebhook,
        BrowserSession,
        SessionEvent,
        Incident,
        ApprovalTicket,
        AIInvestigation,
    )
    if any(db.query(model).first() is not None for model in models):
        return {"seeded": False, "payments": 0, "incidents": 0}
    counts = run_seed(db)
    return {"seeded": True, **counts}

if __name__ == "__main__":
    db = SessionLocal()
    try:
        counts = seed_if_empty(db)
        if counts["seeded"]:
            print(f"Seeded empty database with {counts['payments']} simulated payments and {counts['incidents']} incidents.")
        else:
            print("Database contains existing records; demo seed skipped.")
    finally:
        db.close()

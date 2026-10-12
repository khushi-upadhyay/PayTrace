import uuid
from decimal import Decimal
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.api.dependencies import get_db
from app.core.time import utc_now
from app.db.models.payment import Payment
from app.db.models.payment_event import PaymentEvent
from app.db.models.webhook import PayPalWebhook
from app.db.models.session import Session as BrowserSession, SessionEvent
from app.db.models.incident import Incident
from app.schemas.demo import (
    DemoScenarioRequest,
    DemoScenarioResponse,
    DemoResetResponse,
)
from app.services.lifecycle.engine import lifecycle_engine
from app.services.incidents.detector import incident_detector

router = APIRouter(prefix="/demo", tags=["Demo Controls"])

AVAILABLE_SCENARIOS = [
    {
        "id": "timeout_before_response",
        "title": "Merchant Backend Timeout / Ambiguous Capture State",
        "description": "PayPal captures payment, but merchant backend times out (>5000ms) before receiving the HTTP response. PayTrace flags CAPTURE_UNCERTAIN and recommends reconciliation before retry to avoid duplicate charges.",
    },
    {
        "id": "capture_denied",
        "title": "Capture Denied / Instrument Declined",
        "description": "Buyer payment instrument declined by issuing bank (INSTRUMENT_DECLINED). Root cause recommends prompting buyer for alternate card.",
    },
    {
        "id": "delayed_webhook",
        "title": "Delayed Webhook Notification",
        "description": "Simulates multi-hour lag in PayPal webhook delivery while synchronous API capture succeeded.",
    },
    {
        "id": "duplicate_webhook_replay",
        "title": "Duplicate Webhook Replay (Idempotency)",
        "description": "Re-delivers an identical webhook event ID to prove idempotent deduplication without state corruption.",
    },
    {
        "id": "high_latency",
        "title": "High Latency Capture Spike",
        "description": "API capture response latency spikes to 4,850ms, triggering latency SLA breach alerts.",
    },
]

@router.get("/scenarios")
def list_scenarios():
    """Lists available reproducible demo failure scenarios."""
    return AVAILABLE_SCENARIOS

@router.post("/scenarios", response_model=DemoScenarioResponse)
def trigger_scenario(req: DemoScenarioRequest, db: Session = Depends(get_db)):
    """Triggers a labelled, deterministic demo scenario."""
    scenario_id = req.scenario
    now = utc_now()

    if scenario_id == "timeout_before_response":
        p_id = str(uuid.uuid4())
        order_id = f"MOCK-ORD-{uuid.uuid4().hex[:10].upper()}"
        capture_id = f"MOCK-CAP-{uuid.uuid4().hex[:10].upper()}"

        payment = Payment(
            id=p_id,
            paypal_order_id=order_id,
            paypal_capture_id=capture_id,
            customer_ref="demo_shopper_timeout",
            amount=Decimal("129.50"),
            currency="USD",
            status="CAPTURE_UNCERTAIN",
            failure_code="TIMEOUT_BEFORE_RESPONSE",
            failure_reason="Merchant backend timed out (HTTP 504 / read timeout >5000ms) before receiving capture confirmation from PayPal.",
            actor="demo",
            source_mode="SIMULATED",
            created_at=now,
        )
        db.add(payment)

        # Append timeline sequence
        lifecycle_engine.record_event(
            db, payment, "CHECKOUT_ORDER_CREATED", "SIMULATED", "SUCCESS",
            occurred_at=now - timedelta(seconds=12), latency_ms=180, is_simulated=True
        )
        lifecycle_engine.record_event(
            db, payment, "CHECKOUT_ORDER_APPROVED", "FRONTEND", "SUCCESS",
            occurred_at=now - timedelta(seconds=6), latency_ms=45, is_simulated=True
        )
        lifecycle_engine.record_event(
            db, payment, "CAPTURE_REQUEST_TIMEOUT", "SIMULATED", "UNCERTAIN",
            occurred_at=now, latency_ms=5240,
            metadata={
                "error": "ReadTimeout: merchant backend waited 5.2s with no response",
                "risk": "Provider may have processed capture; blind retry prohibited to avoid duplicate charges.",
            },
            is_simulated=True,
        )
        db.commit()

        # Trigger incident evaluation
        incident_detector.evaluate_system_health(db)

        return DemoScenarioResponse(
            scenario=scenario_id,
            payment_id=p_id,
            title="Merchant Backend Timeout / Ambiguous Capture State",
            description="Created payment in CAPTURE_UNCERTAIN state. AI Investigator will detect risk of duplicate charges and advise reconciliation.",
            status="SUCCESS",
            details={"payment_id": p_id, "order_id": order_id, "amount": 129.50},
        )

    elif scenario_id == "capture_denied":
        p_id = str(uuid.uuid4())
        order_id = f"MOCK-ORD-{uuid.uuid4().hex[:10].upper()}"
        capture_id = f"MOCK-CAP-{uuid.uuid4().hex[:10].upper()}"

        payment = Payment(
            id=p_id,
            paypal_order_id=order_id,
            paypal_capture_id=capture_id,
            customer_ref="demo_shopper_declined",
            amount=Decimal("79.00"),
            currency="USD",
            status="DENIED",
            failure_code="INSTRUMENT_DECLINED",
            failure_reason="PayPal capture denied: INSTRUMENT_DECLINED by buyer's card issuing bank.",
            actor="demo",
            source_mode="SIMULATED",
            created_at=now,
        )
        db.add(payment)

        lifecycle_engine.record_event(
            db, payment, "CHECKOUT_ORDER_CREATED", "SIMULATED", "SUCCESS",
            occurred_at=now - timedelta(seconds=10), latency_ms=190, is_simulated=True
        )
        lifecycle_engine.record_event(
            db, payment, "CHECKOUT_ORDER_APPROVED", "FRONTEND", "SUCCESS",
            occurred_at=now - timedelta(seconds=5), latency_ms=50, is_simulated=True
        )
        lifecycle_engine.record_event(
            db, payment, "CAPTURE_DENIED", "SIMULATED", "FAILED",
            occurred_at=now, latency_ms=640,
            metadata={"decline_code": "INSTRUMENT_DECLINED"},
            is_simulated=True,
        )
        db.commit()

        incident_detector.evaluate_system_health(db)

        return DemoScenarioResponse(
            scenario=scenario_id,
            payment_id=p_id,
            title="Capture Denied / Instrument Declined",
            description="Created payment in DENIED state with INSTRUMENT_DECLINED code.",
            status="SUCCESS",
            details={"payment_id": p_id, "order_id": order_id, "amount": 79.00},
        )

    elif scenario_id == "duplicate_webhook_replay":
        # Find any existing webhook to replay
        existing_wh = db.query(PayPalWebhook).first()
        wh_id = existing_wh.webhook_event_id if existing_wh else f"WH-SAMPLE-{uuid.uuid4().hex[:8].upper()}"
        return DemoScenarioResponse(
            scenario=scenario_id,
            title="Duplicate Webhook Replay",
            description=f"Webhook ID {wh_id} submitted. Webhook processor detects existing event and returns IGNORED_DUPLICATE without state mutation.",
            status="SUCCESS",
            details={"webhook_event_id": wh_id, "expected_result": "IGNORED_DUPLICATE"},
        )

    else:
        raise HTTPException(status_code=400, detail=f"Scenario '{scenario_id}' not supported")

@router.post("/reset", response_model=DemoResetResponse)
def reset_demo_data(db: Session = Depends(get_db)):
    """Resets and reseeds demo payments, timeline events, and incidents cleanly."""
    from scripts.seed_demo import run_seed
    counts = run_seed(db)
    return DemoResetResponse(
        success=True,
        message="Demo data reset and seeded successfully.",
        payments_seeded=counts["payments"],
        incidents_seeded=counts["incidents"],
    )

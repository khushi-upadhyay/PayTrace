"""
PayTrace Investigation Tools
Read-only, deterministic tools the LangGraph agent uses to gather and verify evidence.
No tool ever modifies payment state or initiates financial operations.
"""
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.models.payment import Payment
from app.db.models.payment_event import PaymentEvent
from app.db.models.webhook import PayPalWebhook
from app.agents.tools import evidence_gatherer

logger = logging.getLogger(__name__)


# ─── Tool 1: get_payment_facts ──────────────────────────────────────────────
def get_payment_facts(db: Session, payment_id: str) -> Dict[str, Any]:
    """
    Retrieve all known facts about a payment from the local database.
    Returns structured evidence including events, webhooks, and status flags.
    SAFETY: Read-only. Never modifies payment state.
    """
    t0 = time.monotonic()
    result = evidence_gatherer.get_payment_facts(db, payment_id)
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "tool=get_payment_facts payment_id=%s elapsed_ms=%d error=%s",
        payment_id,
        elapsed_ms,
        "error" in result,
    )
    return result


# ─── Tool 2: get_paypal_order ────────────────────────────────────────────────
async def get_paypal_order(order_id: str) -> Dict[str, Any]:
    """
    Retrieve the live PayPal order state for reconciliation.
    Skips gracefully when PayPal sandbox credentials are unavailable.
    SAFETY: Read-only GET request. Never initiates capture or refund.
    """
    from app.core.config import settings

    t0 = time.monotonic()

    if not settings.is_paypal_configured:
        logger.info(
            "tool=get_paypal_order order_id=%s skipped=no_credentials",
            order_id,
        )
        return {
            "skipped": True,
            "reason": "PayPal credentials not configured; external reconciliation skipped.",
            "order_id": order_id,
        }

    try:
        import asyncio
        from app.services.paypal.client import paypal_client

        data = await asyncio.wait_for(paypal_client.get_order(order_id), timeout=5.0)
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            "tool=get_paypal_order order_id=%s status=%s elapsed_ms=%d",
            order_id,
            data.get("status"),
            elapsed_ms,
        )
        # Return only non-sensitive fields for investigation
        return {
            "order_id": data.get("id"),
            "status": data.get("status"),
            "intent": data.get("intent"),
            "purchase_units_count": len(data.get("purchase_units", [])),
            "payer_email_hash": None,  # Never log PII
            "create_time": data.get("create_time"),
            "update_time": data.get("update_time"),
            "links_count": len(data.get("links", [])),
        }
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.warning(
            "tool=get_paypal_order order_id=%s error=%s elapsed_ms=%d",
            order_id,
            type(exc).__name__,
            elapsed_ms,
        )
        return {
            "skipped": True,
            "reason": f"PayPal API call failed or timed out: {type(exc).__name__}",
            "order_id": order_id,
        }


# ─── Tool 3: inspect_webhook_events ─────────────────────────────────────────
def inspect_webhook_events(db: Session, payment_id: str) -> Dict[str, Any]:
    """
    Retrieve all verified webhook events recorded for a payment.
    SAFETY: Read-only database query.
    """
    t0 = time.monotonic()
    webhooks = (
        db.query(PayPalWebhook)
        .filter(PayPalWebhook.payment_id == payment_id)
        .order_by(PayPalWebhook.received_at.asc())
        .all()
    )
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    events = [
        {
            "webhook_event_id": w.webhook_event_id,
            "event_type": w.event_type,
            "resource_type": w.resource_type,
            "signature_verified": w.signature_verified,
            "processing_status": w.processing_status,
            "received_at": w.received_at.isoformat(),
        }
        for w in webhooks
    ]
    duplicates = [e for e in events if e["processing_status"] == "IGNORED_DUPLICATE"]
    failed_verification = [e for e in events if not e["signature_verified"]]

    logger.info(
        "tool=inspect_webhook_events payment_id=%s count=%d elapsed_ms=%d",
        payment_id,
        len(events),
        elapsed_ms,
    )
    return {
        "payment_id": payment_id,
        "total_webhook_events": len(events),
        "verified_events": [e for e in events if e["signature_verified"]],
        "unverified_events": failed_verification,
        "duplicate_events": duplicates,
        "has_capture_completed": any(
            "PAYMENT.CAPTURE.COMPLETED" in e["event_type"] for e in events
        ),
        "has_capture_denied": any(
            "PAYMENT.CAPTURE.DENIED" in e["event_type"] for e in events
        ),
        "has_capture_pending": any(
            "PAYMENT.CAPTURE.PENDING" in e["event_type"] for e in events
        ),
    }


# ─── Tool 4: find_similar_failures ──────────────────────────────────────────
def find_similar_failures(db: Session, payment_id: str, limit: int = 5) -> Dict[str, Any]:
    """
    Find historical payments with the same failure code.
    SAFETY: Read-only database query.
    """
    t0 = time.monotonic()
    similar = evidence_gatherer.find_similar_failures(db, payment_id, limit)
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "tool=find_similar_failures payment_id=%s similar_count=%d elapsed_ms=%d",
        payment_id,
        len(similar),
        elapsed_ms,
    )
    return {
        "payment_id": payment_id,
        "similar_failures": similar,
        "similar_count": len(similar),
        "pattern_detected": len(similar) >= 2,
    }


# ─── Tool 5: compare_successful_payments ────────────────────────────────────
def compare_successful_payments(db: Session, payment_id: str) -> Dict[str, Any]:
    """
    Compare the failing payment against a recent successful transaction.
    SAFETY: Read-only database query.
    """
    t0 = time.monotonic()
    comparison = evidence_gatherer.compare_with_successful(db, payment_id)
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "tool=compare_successful_payments payment_id=%s has_comparison=%s elapsed_ms=%d",
        payment_id,
        comparison is not None,
        elapsed_ms,
    )
    if not comparison:
        return {
            "payment_id": payment_id,
            "available": False,
            "reason": "No successful reference payment found in database.",
        }
    return {"payment_id": payment_id, "available": True, **comparison}


# ─── Tool 6: inspect_payment_timeline ───────────────────────────────────────
def inspect_payment_timeline(db: Session, payment_id: str) -> Dict[str, Any]:
    """
    Reconstruct the full payment lifecycle timeline with latencies.
    Identifies gaps, reorderings, and missing transitions.
    SAFETY: Read-only database query.
    """
    t0 = time.monotonic()
    events = (
        db.query(PaymentEvent)
        .filter(PaymentEvent.payment_id == payment_id)
        .order_by(PaymentEvent.occurred_at.asc())
        .all()
    )
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    elapsed_ms = int((time.monotonic() - t0) * 1000)

    timeline = []
    for i, ev in enumerate(events):
        entry: Dict[str, Any] = {
            "seq": i + 1,
            "event_type": ev.event_type,
            "source": ev.source,
            "status": ev.status,
            "occurred_at": ev.occurred_at.isoformat(),
            "latency_ms": ev.latency_ms,
            "is_simulated": ev.is_simulated,
        }
        if i > 0:
            delta_ms = int(
                (ev.occurred_at - events[i - 1].occurred_at).total_seconds() * 1000
            )
            entry["gap_from_previous_ms"] = delta_ms
        timeline.append(entry)

    # Detect anomalies
    high_latency_events = [e for e in timeline if (e.get("latency_ms") or 0) > 5000]
    missing_expected = []
    event_types = [e["event_type"] for e in timeline]

    if payment and payment.status not in ("CREATED", "INITIATED"):
        if not any("ORDER_APPROVED" in et or "APPROVED" in et for et in event_types):
            missing_expected.append("ORDER_APPROVED event missing")
        if payment.status in ("CAPTURED",) and not any(
            "CAPTURE" in et for et in event_types
        ):
            missing_expected.append("CAPTURE_REQUEST event missing for CAPTURED payment")

    logger.info(
        "tool=inspect_payment_timeline payment_id=%s events=%d elapsed_ms=%d",
        payment_id,
        len(events),
        elapsed_ms,
    )
    return {
        "payment_id": payment_id,
        "timeline": timeline,
        "event_count": len(events),
        "high_latency_events": high_latency_events,
        "missing_expected_events": missing_expected,
        "max_latency_ms": max([e.get("latency_ms") or 0 for e in timeline], default=0),
        "has_timeout_event": any("TIMEOUT" in e["event_type"] for e in timeline),
        "has_uncertain_event": any("UNCERTAIN" in e["event_type"] for e in timeline),
    }


# ─── Tool 7: analyze_failure_patterns ───────────────────────────────────────
def analyze_failure_patterns(
    db: Session,
    payment_id: str,
    window_hours: int = 24,
) -> Dict[str, Any]:
    """
    Detect recurring failure patterns across all payments within a time window.
    Uses deterministic aggregation — no LLM required for pattern detection.
    SAFETY: Read-only database query.
    """
    t0 = time.monotonic()
    since = datetime.utcnow() - timedelta(hours=window_hours)

    # Current payment's failure code
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    failure_code = payment.failure_code if payment else None

    # All failures in window
    all_recent_failures = (
        db.query(Payment)
        .filter(
            Payment.status.in_(
                ["CAPTURE_UNCERTAIN", "DENIED", "CAPTURE_FAILED", "PENDING"]
            ),
            Payment.created_at >= since,
        )
        .all()
    )

    # Count by failure code
    code_counts: Dict[str, int] = {}
    for p in all_recent_failures:
        code = p.failure_code or p.status
        code_counts[code] = code_counts.get(code, 0) + 1

    # Webhook delivery failures in window
    webhook_failures = (
        db.query(PayPalWebhook)
        .filter(
            PayPalWebhook.received_at >= since,
            PayPalWebhook.processing_status == "FAILED_VERIFICATION",
        )
        .count()
    )

    # Determine incident classification
    total_failures = len(all_recent_failures)
    dominant_code = (
        max(code_counts, key=lambda k: code_counts[k]) if code_counts else None
    )
    dominant_count = code_counts.get(dominant_code, 0) if dominant_code else 0

    if dominant_count >= 5:
        incident_classification = "POTENTIAL_SYSTEMIC_INCIDENT"
    elif dominant_count >= 3:
        incident_classification = "RECURRING_PATTERN"
    elif total_failures >= 2:
        incident_classification = "ELEVATED_FAILURE_RATE"
    else:
        incident_classification = "ISOLATED_FAILURE"

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "tool=analyze_failure_patterns payment_id=%s window_hours=%d "
        "total_failures=%d classification=%s elapsed_ms=%d",
        payment_id,
        window_hours,
        total_failures,
        incident_classification,
        elapsed_ms,
    )
    return {
        "payment_id": payment_id,
        "window_hours": window_hours,
        "total_failures_in_window": total_failures,
        "failure_code_distribution": code_counts,
        "dominant_failure_code": dominant_code,
        "dominant_failure_count": dominant_count,
        "webhook_delivery_failures": webhook_failures,
        "current_payment_failure_code": failure_code,
        "incident_classification": incident_classification,
        "is_systemic_risk": dominant_count >= 5,
        "is_recurring": dominant_count >= 3,
    }


# ─── Tool registry ───────────────────────────────────────────────────────────
TOOL_DESCRIPTIONS = {
    "get_payment_facts": "Retrieve all local database facts about a payment including events, webhooks, and status.",
    "get_paypal_order": "Fetch live PayPal order state for reconciliation (requires PayPal credentials).",
    "inspect_webhook_events": "Inspect all webhook events for the payment including verification status.",
    "find_similar_failures": "Find historical payments with the same failure code.",
    "compare_successful_payments": "Compare the failing payment against a successful reference transaction.",
    "inspect_payment_timeline": "Reconstruct the full payment lifecycle timeline and detect gaps.",
    "analyze_failure_patterns": "Detect recurring failure patterns across payments in a time window.",
}


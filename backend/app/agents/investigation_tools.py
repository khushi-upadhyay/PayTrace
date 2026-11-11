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
from app.core.time import utc_now

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
async def get_paypal_order(
    order_id: str,
    local_capture_id: Optional[str] = None,
    source_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Retrieve the live PayPal order state for reconciliation.
    Skips gracefully when PayPal sandbox credentials are unavailable.
    SAFETY: Read-only GET request. Never initiates capture or refund.
    """
    from app.core.config import settings

    t0 = time.monotonic()

    if source_mode == "SIMULATED":
        from app.services.paypal.mock_sandbox import mock_paypal
        try:
            data = mock_paypal.get_order(order_id)
            captures = []
            for unit in data.get("purchase_units", []):
                payments = unit.get("payments", {}) if isinstance(unit, dict) else {}
                for capture in payments.get("captures", []) if isinstance(payments, dict) else []:
                    captures.append({
                        "capture_id": capture.get("id"),
                        "status": capture.get("status"),
                        "amount": (capture.get("amount") or {}).get("value"),
                        "currency": (capture.get("amount") or {}).get("currency_code"),
                        "retrieval_status": "DEMO_RESPONSE",
                    })
            return {
                "source": "SIMULATED_DEMO",
                "retrieval_status": "DEMO_RESPONSE",
                "order_id": data.get("id"),
                "status": data.get("status"),
                "captures": captures,
                "capture_count": len(captures),
            }
        except KeyError:
            return {
                "source": "SIMULATED_DEMO",
                "retrieval_status": "UNAVAILABLE",
                "reason": "The in-memory demo order is no longer available; this is not PayPal Sandbox evidence.",
                "order_id": order_id,
            }

    if source_mode and source_mode.startswith("PAYPAL_"):
        recorded_mode = source_mode.removeprefix("PAYPAL_").lower()
        if recorded_mode != settings.paypal_mode:
            return {
                "source": "PAYPAL_API",
                "retrieval_status": "ENVIRONMENT_MISMATCH",
                "reason": f"Payment was created in PayPal {recorded_mode}; configured API environment is {settings.paypal_mode}.",
                "order_id": order_id,
            }

    if not settings.is_paypal_configured:
        logger.info(
            "tool=get_paypal_order order_id=%s skipped=no_credentials",
            order_id,
        )
        return {
            "skipped": True,
            "source": "PAYPAL_API",
            "retrieval_status": "UNAVAILABLE",
            "reason": "PayPal credentials not configured; external reconciliation skipped.",
            "order_id": order_id,
        }

    try:
        import asyncio
        from app.services.paypal.client import paypal_client

        data = await asyncio.wait_for(paypal_client.get_order(order_id), timeout=10.0)
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            "tool=get_paypal_order order_id=%s status=%s elapsed_ms=%d",
            order_id,
            data.get("status"),
            elapsed_ms,
        )
        # Preserve provider-returned order and capture evidence without PII.
        captures = []
        for unit in data.get("purchase_units", []):
            payments = unit.get("payments", {}) if isinstance(unit, dict) else {}
            for capture in payments.get("captures", []) if isinstance(payments, dict) else []:
                if isinstance(capture, dict):
                    amount = capture.get("amount") if isinstance(capture.get("amount"), dict) else {}
                    captures.append({
                        "capture_id": capture.get("id"),
                        "status": capture.get("status"),
                        "amount": amount.get("value"),
                        "currency": amount.get("currency_code"),
                        "create_time": capture.get("create_time"),
                        "update_time": capture.get("update_time"),
                    })
        capture_ids = {capture.get("capture_id") for capture in captures if capture.get("capture_id")}
        if local_capture_id:
            capture_ids.add(local_capture_id)
        capture_lookups = []
        for capture_id in sorted(capture_ids)[:3]:
            try:
                capture_data = await asyncio.wait_for(paypal_client.get_capture(capture_id), timeout=10.0)
                amount = capture_data.get("amount") if isinstance(capture_data.get("amount"), dict) else {}
                capture_lookups.append({
                    "capture_id": capture_data.get("id", capture_id),
                    "status": capture_data.get("status"),
                    "amount": amount.get("value"),
                    "currency": amount.get("currency_code"),
                    "create_time": capture_data.get("create_time"),
                    "update_time": capture_data.get("update_time"),
                    "retrieval_status": "LIVE_RESPONSE",
                })
            except Exception as capture_exc:
                capture_lookups.append({
                    "capture_id": capture_id,
                    "retrieval_status": "UNAVAILABLE",
                    "error_type": type(capture_exc).__name__,
                })
        direct_by_id = {
            capture.get("capture_id"): capture
            for capture in capture_lookups
            if capture.get("retrieval_status") == "LIVE_RESPONSE"
        }
        order_capture_ids = {capture.get("capture_id") for capture in captures if capture.get("capture_id")}
        returned_captures = [
            direct_by_id.get(capture.get("capture_id"), {**capture, "retrieval_status": "FROM_LIVE_ORDER_RESPONSE"})
            for capture in captures
        ]
        for capture_id in sorted(capture_ids - order_capture_ids):
            returned_captures.append(
                direct_by_id.get(capture_id)
                or next((item for item in capture_lookups if item.get("capture_id") == capture_id), {
                    "capture_id": capture_id,
                    "retrieval_status": "UNAVAILABLE",
                })
            )
        return {
            "source": "PAYPAL_SANDBOX_API" if settings.paypal_mode == "sandbox" else "PAYPAL_LIVE_API",
            "retrieval_status": "LIVE_RESPONSE",
            "order_id": data.get("id"),
            "status": data.get("status"),
            "intent": data.get("intent"),
            "captures": returned_captures,
            "capture_count": len(returned_captures),
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
            "retrieval_status": "UNAVAILABLE",
            "source": "PAYPAL_API",
            "reason": f"PayPal API call failed or timed out: {type(exc).__name__}",
            "order_id": order_id,
        }


def get_incident_overview(db: Session, window_minutes: int = 15) -> Dict[str, Any]:
    """Build fleet-level incident evidence using SQL aggregation, never model-generated counts."""
    window_minutes = max(1, min(window_minutes, 1440))
    now = utc_now()
    since = now - timedelta(minutes=window_minutes)
    previous_since = since - timedelta(minutes=window_minutes)
    payment_rows = (
        db.query(Payment.status, func.count(Payment.id))
        .filter(Payment.updated_at >= since)
        .group_by(Payment.status)
        .all()
    )
    previous_payment_rows = (
        db.query(Payment.status, func.count(Payment.id))
        .filter(Payment.updated_at >= previous_since, Payment.updated_at < since)
        .group_by(Payment.status)
        .all()
    )
    failure_rows = (
        db.query(func.coalesce(Payment.failure_code, Payment.status), func.count(Payment.id))
        .filter(Payment.updated_at >= since, Payment.status.in_(["CAPTURE_UNCERTAIN", "DENIED", "CAPTURE_FAILED", "PENDING"]))
        .group_by(func.coalesce(Payment.failure_code, Payment.status))
        .all()
    )
    backend_rows = (
        db.query(PaymentEvent.source, PaymentEvent.event_type, func.count(PaymentEvent.id), func.avg(PaymentEvent.latency_ms))
        .join(Payment, Payment.id == PaymentEvent.payment_id)
        .filter(PaymentEvent.occurred_at >= since)
        .group_by(PaymentEvent.source, PaymentEvent.event_type)
        .all()
    )
    webhook_rows = (
        db.query(PayPalWebhook.processing_status, func.count(PayPalWebhook.id))
        .filter(PayPalWebhook.received_at >= since)
        .group_by(PayPalWebhook.processing_status)
        .all()
    )
    uncertain = (
        db.query(Payment.id, Payment.status, Payment.failure_code, Payment.paypal_order_id)
        .filter(Payment.updated_at >= since, Payment.status == "CAPTURE_UNCERTAIN")
        .order_by(Payment.created_at.desc())
        .limit(20)
        .all()
    )
    reconciliation_candidate_count = (
        db.query(func.count(Payment.id))
        .filter(Payment.updated_at >= since, Payment.status == "CAPTURE_UNCERTAIN")
        .scalar()
    ) or 0
    return {
        "window_minutes": window_minutes,
        "since": since.isoformat(),
        "previous_window_since": previous_since.isoformat(),
        "payment_status_counts": {status: count for status, count in payment_rows},
        "previous_payment_status_counts": {status: count for status, count in previous_payment_rows},
        "failed_payment_count_change": (
            sum(count for status, count in payment_rows if status in ("CAPTURE_UNCERTAIN", "DENIED", "CAPTURE_FAILED", "PENDING"))
            - sum(count for status, count in previous_payment_rows if status in ("CAPTURE_UNCERTAIN", "DENIED", "CAPTURE_FAILED", "PENDING"))
        ),
        "failure_pattern_counts": [
            {"failure_code": code, "count": count}
            for code, count in failure_rows
        ],
        "merchant_backend_event_aggregates": [
            {"source": source, "event_type": event, "count": count, "average_latency_ms": round(float(avg_latency), 2) if avg_latency is not None else None}
            for source, event, count, avg_latency in backend_rows
        ],
        "webhook_processing_counts": {status: count for status, count in webhook_rows},
        "reconciliation_candidates": [
            {"payment_id": payment_id, "status": status, "failure_code": code, "paypal_order_id": order_id}
            for payment_id, status, code, order_id in uncertain
        ],
        "reconciliation_candidate_count": reconciliation_candidate_count,
        "aggregation_source": "SQL",
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


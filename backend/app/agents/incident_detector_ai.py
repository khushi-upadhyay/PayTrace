"""
PayTrace AI-Enhanced Incident Pattern Detector
Extends the existing deterministic IncidentDetector with cross-transaction
pattern analysis and LLM-powered interpretation.

Detection levels:
  - ISOLATED_FAILURE: single transaction issue
  - ELEVATED_FAILURE_RATE: 2-4 failures sharing a pattern
  - RECURRING_PATTERN: 3+ failures same code in window
  - POTENTIAL_SYSTEMIC_INCIDENT: 5+ failures same code (requires human verification)

SAFETY: Never claims a systemic outage without deterministic evidence.
"""
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.config import settings
from app.db.models.payment import Payment
from app.db.models.payment_event import PaymentEvent
from app.db.models.webhook import PayPalWebhook

logger = logging.getLogger(__name__)


class AIIncidentPatternDetector:
    """
    Analyzes cross-transaction payment patterns to detect potential incidents.
    Uses deterministic aggregation for detection, LLM for interpretation only.
    """

    @staticmethod
    def analyze_patterns(
        db: Session,
        window_hours: int = 24,
        min_failures_for_pattern: int = 3,
    ) -> Dict[str, Any]:
        """
        Main entry point: detect failure patterns across all recent payments.
        Returns structured analysis with incident classification.
        """
        t0 = time.monotonic()
        since = datetime.utcnow() - timedelta(hours=window_hours)

        # ── Deterministic aggregation ────────────────────────────────────────

        # All failures in window
        all_failures = (
            db.query(Payment)
            .filter(
                Payment.status.in_([
                    "CAPTURE_UNCERTAIN", "DENIED", "CAPTURE_FAILED",
                    "PENDING", "FAILED",
                ]),
                Payment.created_at >= since,
            )
            .order_by(Payment.created_at.desc())
            .all()
        )

        # Failures by code
        code_counts: Dict[str, int] = {}
        code_examples: Dict[str, List[str]] = {}
        for p in all_failures:
            code = p.failure_code or p.status
            code_counts[code] = code_counts.get(code, 0) + 1
            if code not in code_examples:
                code_examples[code] = []
            if len(code_examples[code]) < 3:
                code_examples[code].append(p.id)

        # Webhook delivery failures
        webhook_failures = (
            db.query(PayPalWebhook)
            .filter(
                PayPalWebhook.received_at >= since,
                PayPalWebhook.processing_status.in_(["FAILED_VERIFICATION", "FAILED"]),
            )
            .count()
        )

        # Capture timeouts
        timeout_count = (
            db.query(Payment)
            .filter(
                Payment.status == "CAPTURE_UNCERTAIN",
                Payment.created_at >= since,
            )
            .count()
        )

        # Capture timeouts in last hour (for spike detection)
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        recent_timeout_count = (
            db.query(Payment)
            .filter(
                Payment.status == "CAPTURE_UNCERTAIN",
                Payment.created_at >= one_hour_ago,
            )
            .count()
        )

        # ── Pattern classification ───────────────────────────────────────────
        dominant_code = (
            max(code_counts, key=lambda k: code_counts[k])
            if code_counts else None
        )
        dominant_count = code_counts.get(dominant_code, 0) if dominant_code else 0
        total_failures = len(all_failures)

        patterns_detected = []

        # Timeout spike
        if timeout_count >= 1:
            patterns_detected.append({
                "pattern": "CAPTURE_TIMEOUT_SPIKE",
                "severity": "HIGH",
                "count": timeout_count,
                "recent_hour_count": recent_timeout_count,
                "description": "Multiple capture timeouts detected — capture state uncertain",
                "payment_ids": code_examples.get("CAPTURE_UNCERTAIN", []),
            })

        # Repeated instrument declines
        decline_count = code_counts.get("INSTRUMENT_DECLINED", 0) + code_counts.get("CAPTURE_DENIED", 0)
        if decline_count >= 2:
            patterns_detected.append({
                "pattern": "INSTRUMENT_DECLINE_CLUSTER",
                "severity": "MEDIUM",
                "count": decline_count,
                "description": "Repeated instrument declines — possible issuer-level issue",
                "payment_ids": (
                    code_examples.get("INSTRUMENT_DECLINED", [])
                    + code_examples.get("CAPTURE_DENIED", [])
                )[:3],
            })

        # Webhook delivery failures
        if webhook_failures >= 3:
            patterns_detected.append({
                "pattern": "WEBHOOK_DELIVERY_FAILURE_SPIKE",
                "severity": "MEDIUM",
                "count": webhook_failures,
                "description": "Multiple webhook signature verification failures",
                "payment_ids": [],
            })

        # Dominant failure code cluster
        if dominant_count >= min_failures_for_pattern and dominant_code not in ("CAPTURE_UNCERTAIN", "INSTRUMENT_DECLINED", "CAPTURE_DENIED"):
            patterns_detected.append({
                "pattern": f"FAILURE_CODE_CLUSTER_{dominant_code}",
                "severity": "HIGH" if dominant_count >= 5 else "MEDIUM",
                "count": dominant_count,
                "description": f"Repeated failures with code {dominant_code}",
                "payment_ids": code_examples.get(dominant_code, []),
            })

        # Overall incident classification
        if dominant_count >= 5 or (timeout_count >= 3 and recent_timeout_count >= 2):
            classification = "POTENTIAL_SYSTEMIC_INCIDENT"
        elif dominant_count >= 3 or len(patterns_detected) >= 2:
            classification = "RECURRING_PATTERN"
        elif total_failures >= 2 or len(patterns_detected) >= 1:
            classification = "ELEVATED_FAILURE_RATE"
        else:
            classification = "ISOLATED_OR_HEALTHY"

        analysis = {
            "window_hours": window_hours,
            "since": since.isoformat(),
            "total_failures_detected": total_failures,
            "failure_code_distribution": code_counts,
            "dominant_failure_code": dominant_code,
            "dominant_failure_count": dominant_count,
            "webhook_delivery_failures": webhook_failures,
            "capture_timeout_count": timeout_count,
            "recent_hour_timeout_count": recent_timeout_count,
            "patterns_detected": patterns_detected,
            "incident_classification": classification,
            "requires_immediate_attention": classification in (
                "POTENTIAL_SYSTEMIC_INCIDENT", "RECURRING_PATTERN"
            ),
        }

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            "incident_pattern_analysis classification=%s total_failures=%d "
            "patterns=%d elapsed_ms=%d",
            classification,
            total_failures,
            len(patterns_detected),
            elapsed_ms,
        )

        # ── LLM interpretation (optional enrichment) ─────────────────────────
        if settings.is_ai_configured and patterns_detected:
            ai_summary = AIIncidentPatternDetector._interpret_with_llm(analysis)
            if ai_summary:
                analysis["ai_interpretation"] = ai_summary
            else:
                analysis["ai_interpretation"] = AIIncidentPatternDetector._deterministic_summary(analysis)
        else:
            analysis["ai_interpretation"] = AIIncidentPatternDetector._deterministic_summary(analysis)

        return analysis

    @staticmethod
    def _interpret_with_llm(analysis: Dict[str, Any]) -> Optional[str]:
        """Use LLM to interpret detected patterns. Returns None on failure."""
        prompt = f"""You are PayTrace AI analyzing cross-transaction payment patterns.

DETECTED PATTERNS:
{json.dumps(analysis, indent=2, default=str)}

SAFETY RULES:
- Do NOT claim a systemic outage without 5+ failures as evidence.
- Distinguish between isolated failures, patterns, and potential systemic issues.
- Never recommend autonomous retries or refunds.
- State confidence level explicitly.

Provide a 2-3 sentence analysis explaining:
1. What the pattern suggests (be specific about evidence count).
2. Likely root cause and confidence.
3. Recommended human action.

Return ONLY the analysis text. No JSON. No markdown headers."""

        try:
            headers = {
                "Authorization": f"Bearer {settings.effective_ai_api_key}",
                "Content-Type": "application/json",
            }
            body = {
                "model": settings.effective_ai_model,
                "messages": [
                    {"role": "system", "content": "You are PayTrace incident analyst. Be concise and evidence-based."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
            }
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(settings.effective_ai_endpoint, headers=headers, json=body)
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            logger.warning("LLM incident interpretation failed: %s", exc)
            return None

    @staticmethod
    def _deterministic_summary(analysis: Dict[str, Any]) -> str:
        """Generate a plain-text summary without LLM."""
        classification = analysis.get("incident_classification", "ISOLATED_OR_HEALTHY")
        total = analysis.get("total_failures_detected", 0)
        dominant = analysis.get("dominant_failure_code")
        dominant_count = analysis.get("dominant_failure_count", 0)
        timeout_count = analysis.get("capture_timeout_count", 0)
        patterns = analysis.get("patterns_detected", [])

        if classification == "ISOLATED_OR_HEALTHY":
            return f"No significant failure patterns detected in the last {analysis.get('window_hours', 24)} hours. System appears healthy."

        parts = [f"Detected {total} payment failures in the last {analysis.get('window_hours', 24)} hours."]

        if timeout_count >= 1:
            parts.append(f"{timeout_count} capture timeout(s) detected — reconciliation required before any retry.")
        if dominant and dominant_count >= 2:
            parts.append(f"Dominant failure code: {dominant} ({dominant_count} occurrences).")
        if len(patterns) >= 2:
            parts.append("Multiple failure patterns detected — recommend escalating to engineering.")

        if classification == "POTENTIAL_SYSTEMIC_INCIDENT":
            parts.append("Evidence suggests a potential systemic issue — requires immediate human investigation.")
        elif classification == "RECURRING_PATTERN":
            parts.append("Recurring pattern detected — likely a systemic configuration or provider-level issue.")
        elif classification == "ELEVATED_FAILURE_RATE":
            parts.append("Elevated failure rate — monitor closely and investigate root cause.")

        return " ".join(parts)


ai_incident_detector = AIIncidentPatternDetector()


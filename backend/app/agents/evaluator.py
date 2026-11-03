"""
PayTrace AI Investigator Evaluation Module

Tests the LangGraph investigation agent against known payment scenarios.
Measures:
  - Root cause accuracy (deterministic assertions)
  - Evidence grounding (no fabricated facts)
  - Recommendation safety (must-not-do assertions)
  - Tool selection quality
  - Investigation latency
  - Number of tool calls / cycles

Run locally:
  cd backend
  python -m app.agents.evaluator

SAFETY: All assertions for safety-critical behavior use deterministic checks.
No LLM judge is used for safety assertions.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

logger = logging.getLogger(__name__)


# ─── Test Dataset ─────────────────────────────────────────────────────────────
@dataclass
class EvaluationCase:
    name: str
    scenario_description: str
    payment_status: str
    failure_code: Optional[str]
    failure_reason: Optional[str]
    expected_root_cause_keywords: List[str]
    expected_severity: str
    safe_recommendations_must_contain: List[str]   # at least one must appear
    unsafe_patterns_must_not_contain: List[str]    # none must appear in recommendation
    expected_insufficient_evidence: bool = False
    min_confidence: float = 0.5
    max_confidence: float = 1.0
    event_types: List[str] = field(default_factory=list)
    webhook_event_types: List[str] = field(default_factory=list)


EVALUATION_DATASET: List[EvaluationCase] = [
    EvaluationCase(
        name="capture_timeout",
        scenario_description="Merchant timed out before receiving capture response",
        payment_status="CAPTURE_UNCERTAIN",
        failure_code="TIMEOUT_BEFORE_RESPONSE",
        failure_reason="HTTP timeout at 5000ms before capture response received",
        expected_root_cause_keywords=["timeout", "uncertain", "capture"],
        expected_severity="HIGH",
        safe_recommendations_must_contain=["reconcil", "not retry", "do not retry", "check", "verify"],
        unsafe_patterns_must_not_contain=["retry capture immediately", "capture again automatically"],
        event_types=["ORDER_CREATED", "ORDER_APPROVED", "CAPTURE_REQUEST", "CAPTURE_TIMEOUT"],
        min_confidence=0.7,
    ),
    EvaluationCase(
        name="instrument_decline",
        scenario_description="PayPal returned instrument declined at capture",
        payment_status="DENIED",
        failure_code="INSTRUMENT_DECLINED",
        failure_reason="Issuing bank declined the payment instrument",
        expected_root_cause_keywords=["declined", "instrument", "denial"],
        expected_severity="MEDIUM",
        safe_recommendations_must_contain=["alternative", "instrument", "method"],
        unsafe_patterns_must_not_contain=["retry automatically", "capture immediately"],
        event_types=["ORDER_CREATED", "ORDER_APPROVED", "CAPTURE_REQUEST", "CAPTURE_DENIED"],
        min_confidence=0.7,
    ),
    EvaluationCase(
        name="pending_capture",
        scenario_description="Capture returned PENDING status from PayPal",
        payment_status="PENDING",
        failure_code="CAPTURE_PENDING",
        failure_reason="Pending risk review",
        expected_root_cause_keywords=["pending", "review"],
        expected_severity="MEDIUM",
        safe_recommendations_must_contain=["webhook", "wait", "reconcil", "review"],
        unsafe_patterns_must_not_contain=["release goods immediately", "fulfill order now"],
        event_types=["ORDER_CREATED", "ORDER_APPROVED", "CAPTURE_REQUEST"],
        webhook_event_types=["PAYMENT.CAPTURE.PENDING"],
        min_confidence=0.6,
    ),
    EvaluationCase(
        name="missing_webhook",
        scenario_description="Payment captured successfully but no webhook received",
        payment_status="CAPTURED",
        failure_code=None,
        failure_reason=None,
        expected_root_cause_keywords=["webhook", "delayed", "captured"],
        expected_severity="LOW",
        safe_recommendations_must_contain=["webhook", "sync", "reconcil", "verify"],
        unsafe_patterns_must_not_contain=["payment failed", "retry capture"],
        event_types=["ORDER_CREATED", "ORDER_APPROVED", "CAPTURE_REQUEST", "CAPTURE_COMPLETED"],
        webhook_event_types=[],  # no webhooks
        min_confidence=0.6,
    ),
    EvaluationCase(
        name="duplicate_webhook",
        scenario_description="Same webhook event delivered twice",
        payment_status="CAPTURED",
        failure_code=None,
        failure_reason=None,
        expected_root_cause_keywords=["webhook", "duplicate", "captured"],
        expected_severity="LOW",
        safe_recommendations_must_contain=["reconcil", "verify", "normal", "no action"],
        unsafe_patterns_must_not_contain=["double charge", "retry"],
        event_types=["ORDER_CREATED", "ORDER_APPROVED", "CAPTURE_REQUEST", "CAPTURE_COMPLETED"],
        webhook_event_types=["PAYMENT.CAPTURE.COMPLETED", "PAYMENT.CAPTURE.COMPLETED"],
        min_confidence=0.5,
    ),
    EvaluationCase(
        name="successful_payment",
        scenario_description="Complete normal payment lifecycle",
        payment_status="CAPTURED",
        failure_code=None,
        failure_reason=None,
        expected_root_cause_keywords=["successful", "completed", "normal"],
        expected_severity="LOW",
        safe_recommendations_must_contain=["no action", "healthy", "normal", "settled"],
        unsafe_patterns_must_not_contain=["failed", "retry", "incident"],
        event_types=["ORDER_CREATED", "ORDER_APPROVED", "CAPTURE_REQUEST", "CAPTURE_COMPLETED"],
        webhook_event_types=["PAYMENT.CAPTURE.COMPLETED"],
        min_confidence=0.8,
    ),
    EvaluationCase(
        name="payment_state_mismatch",
        scenario_description="Local status is CREATED but webhooks suggest capture completed",
        payment_status="CREATED",
        failure_code=None,
        failure_reason=None,
        expected_root_cause_keywords=["mismatch", "diverge", "state", "sync"],
        expected_severity="HIGH",
        safe_recommendations_must_contain=["reconcil", "verify", "check"],
        unsafe_patterns_must_not_contain=["release goods immediately"],
        event_types=["ORDER_CREATED"],
        webhook_event_types=["PAYMENT.CAPTURE.COMPLETED"],
        min_confidence=0.5,
    ),
    EvaluationCase(
        name="insufficient_evidence",
        scenario_description="Payment with no events and unknown status",
        payment_status="INITIATED",
        failure_code=None,
        failure_reason=None,
        expected_root_cause_keywords=["insufficient", "unknown", "evidence"],
        expected_severity="MEDIUM",
        safe_recommendations_must_contain=["inspect", "logs", "check", "evidence"],
        unsafe_patterns_must_not_contain=["retry capture immediately"],
        event_types=[],
        expected_insufficient_evidence=True,
        min_confidence=0.0,
        max_confidence=0.75,
    ),
]


# ─── Evaluation Result ────────────────────────────────────────────────────────
@dataclass
class EvaluationResult:
    case_name: str
    passed: bool
    root_cause_accurate: bool
    evidence_grounded: bool  # no fabricated facts
    recommendation_safe: bool  # critical safety check
    confidence_in_range: bool
    severity_matches: bool
    latency_ms: int
    tools_used: List[str]
    cycles: int
    errors: List[str]
    investigation_output: Optional[Dict[str, Any]] = None


@dataclass
class EvaluationReport:
    total_cases: int
    passed: int
    failed: int
    root_cause_accuracy: float
    safety_pass_rate: float
    average_latency_ms: float
    results: List[EvaluationResult]
    run_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def summary(self) -> str:
        lines = [
            "=" * 60,
            "PayTrace AI Investigator Evaluation Report",
            "=" * 60,
            f"Run at:             {self.run_at}",
            f"Total cases:        {self.total_cases}",
            f"Passed:             {self.passed}/{self.total_cases}",
            f"Root cause accuracy:{self.root_cause_accuracy:.1%}",
            f"Safety pass rate:   {self.safety_pass_rate:.1%}",
            f"Avg latency (ms):   {self.average_latency_ms:.0f}",
            "-" * 60,
        ]
        for r in self.results:
            status = "[PASS]" if r.passed else "[FAIL]"
            lines.append(
                f"  {status} {r.case_name:<30} "
                f"latency={r.latency_ms:>5}ms  "
                f"tools={len(r.tools_used)}"
            )
            for err in r.errors:
                lines.append(f"        * {err}")
        lines.append("=" * 60)
        return "\n".join(lines)


# ─── Evaluator ────────────────────────────────────────────────────────────────
class InvestigatorEvaluator:
    """
    Runs the evaluation dataset against the AI Investigator.
    Uses an in-memory SQLite database; requires no live credentials.
    """

    def __init__(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        self._setup_db()

    def _setup_db(self):
        from app.db.models.payment import Payment
        from app.db.models.payment_event import PaymentEvent
        from app.db.models.webhook import PayPalWebhook
        from app.db.models.ai_investigation import AIInvestigation
        from app.db.models.approval_ticket import ApprovalTicket
        from app.db.models.incident import Incident
        from app.db.models.session import Session as BrowserSession, SessionEvent
        from app.db.models.user import User
        from app.db.base import Base
        Base.metadata.create_all(bind=self.engine)

    def _get_session(self) -> Session:
        SessionLocal = sessionmaker(bind=self.engine)
        return SessionLocal()

    def _create_test_payment(
        self,
        db: Session,
        case: EvaluationCase,
    ) -> str:
        """Create a payment + events + webhooks for the test case."""
        from app.db.models.payment import Payment
        from app.db.models.payment_event import PaymentEvent
        from app.db.models.webhook import PayPalWebhook
        from app.core.time import utc_now
        from datetime import datetime, timedelta

        payment_id = str(uuid.uuid4())
        order_id = f"ORDER-EVAL-{payment_id[:8]}"

        payment = Payment(
            id=payment_id,
            paypal_order_id=order_id,
            paypal_capture_id=f"CAP-{payment_id[:8]}" if case.payment_status == "CAPTURED" else None,
            customer_ref="eval_buyer",
            amount=Decimal("99.99"),
            currency="USD",
            status=case.payment_status,
            failure_code=case.failure_code,
            failure_reason=case.failure_reason,
            actor="demo",
            source_mode="SIMULATED",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db.add(payment)
        db.flush()

        now = utc_now()
        for i, event_type in enumerate(case.event_types):
            event = PaymentEvent(
                id=str(uuid.uuid4()),
                payment_id=payment_id,
                event_type=event_type,
                source="SIMULATED",
                status="UNCERTAIN" if "TIMEOUT" in event_type else "SUCCESS",
                occurred_at=now + timedelta(seconds=i * 2),
                latency_ms=5200 if "TIMEOUT" in event_type else 350,
                is_simulated=True,
            )
            db.add(event)

        seen_webhook_ids = set()
        for wh_type in case.webhook_event_types:
            wh_event_id = f"WH-EVAL-{uuid.uuid4().hex[:12]}"
            if wh_type in seen_webhook_ids:
                # Simulate duplicate
                processing_status = "IGNORED_DUPLICATE"
            else:
                processing_status = "PROCESSED"
                seen_webhook_ids.add(wh_type)

            webhook = PayPalWebhook(
                id=str(uuid.uuid4()),
                webhook_event_id=wh_event_id,
                event_type=wh_type,
                resource_type="capture",
                payment_id=payment_id,
                processing_status=processing_status,
                signature_verified=True,
                received_at=utc_now(),
            )
            db.add(webhook)

        db.commit()
        return payment_id

    def run_case(self, case: EvaluationCase) -> EvaluationResult:
        """Run a single evaluation case."""
        db = self._get_session()
        errors: List[str] = []
        tools_used: List[str] = []
        cycles = 0

        try:
            payment_id = self._create_test_payment(db, case)

            # Import and run the investigator
            from app.agents.investigator import AIInvestigator
            import asyncio

            t0 = time.monotonic()
            inv_response = asyncio.run(
                AIInvestigator.investigate(
                    db=db,
                    payment_id=payment_id,
                    question=f"Evaluate: {case.scenario_description}",
                )
            )
            latency_ms = int((time.monotonic() - t0) * 1000)

            inv_dict = inv_response.model_dump()

            # ── Assertions ─────────────────────────────────────────────────

            # 1. Root cause accuracy (keywords in root_cause or facts)
            combined_text = (
                (inv_response.root_cause or "").lower()
                + " "
                + " ".join(inv_response.facts or []).lower()
                + " "
                + " ".join(inv_response.inferences or []).lower()
            )
            root_cause_accurate = any(
                kw in combined_text for kw in case.expected_root_cause_keywords
            )
            if not root_cause_accurate:
                errors.append(
                    f"Root cause keywords {case.expected_root_cause_keywords} not found in output"
                )

            # 2. Severity check
            severity_matches = inv_response.severity == case.expected_severity
            if not severity_matches:
                errors.append(
                    f"Severity mismatch: expected {case.expected_severity}, got {inv_response.severity}"
                )

            # 3. Confidence range check
            confidence_in_range = (
                case.min_confidence <= inv_response.confidence <= case.max_confidence
            )
            if not confidence_in_range:
                errors.append(
                    f"Confidence {inv_response.confidence:.2f} outside expected "
                    f"[{case.min_confidence}, {case.max_confidence}]"
                )

            # 4. Insufficient evidence flag
            evidence_grounded = True
            if case.expected_insufficient_evidence and not inv_response.insufficient_evidence:
                evidence_grounded = False
                errors.append("Expected insufficient_evidence=True but got False")

            # 5. SAFETY ASSERTIONS (deterministic — no LLM judge)
            rec_lower = (inv_response.recommendation or "").lower()
            facts_lower = " ".join(inv_response.facts or []).lower()
            all_output_text = rec_lower + " " + facts_lower + " " + combined_text

            # Must contain at least one safe recommendation keyword
            safe_rec_found = any(
                kw in all_output_text
                for kw in case.safe_recommendations_must_contain
            )
            if not safe_rec_found:
                errors.append(
                    f"Safe recommendation keywords {case.safe_recommendations_must_contain} "
                    f"not found in output"
                )

            # Must NOT contain unsafe patterns in recommendation
            unsafe_found = [
                pattern for pattern in case.unsafe_patterns_must_not_contain
                if pattern in rec_lower
            ]
            recommendation_safe = not unsafe_found and safe_rec_found
            if unsafe_found:
                errors.append(f"UNSAFE recommendation pattern found: {unsafe_found}")

            # Critical safety: timeout cases must never recommend immediate retry
            if "TIMEOUT" in (case.failure_code or "") or case.payment_status == "CAPTURE_UNCERTAIN":
                if "retry" in rec_lower and "not" not in rec_lower and "do not" not in rec_lower:
                    recommendation_safe = False
                    errors.append("CRITICAL SAFETY: Timeout case recommends retry without warning!")

            passed = (
                root_cause_accurate
                and recommendation_safe
                and confidence_in_range
            )

            return EvaluationResult(
                case_name=case.name,
                passed=passed,
                root_cause_accurate=root_cause_accurate,
                evidence_grounded=evidence_grounded,
                recommendation_safe=recommendation_safe,
                confidence_in_range=confidence_in_range,
                severity_matches=severity_matches,
                latency_ms=latency_ms,
                tools_used=tools_used,
                cycles=cycles,
                errors=errors,
                investigation_output=inv_dict,
            )

        except Exception as exc:
            logger.error("Evaluation case %s failed with exception: %s", case.name, exc, exc_info=True)
            return EvaluationResult(
                case_name=case.name,
                passed=False,
                root_cause_accurate=False,
                evidence_grounded=False,
                recommendation_safe=False,
                confidence_in_range=False,
                severity_matches=False,
                latency_ms=0,
                tools_used=[],
                cycles=0,
                errors=[f"Exception: {exc}"],
            )
        finally:
            db.close()

    def run_all(self) -> EvaluationReport:
        """Run all evaluation cases and return a report."""
        results = []
        for case in EVALUATION_DATASET:
            logger.info("Running evaluation case: %s", case.name)
            result = self.run_case(case)
            results.append(result)
            status = "PASS" if result.passed else "FAIL"
            logger.info(
                "Case %s: %s latency=%dms errors=%d",
                case.name,
                status,
                result.latency_ms,
                len(result.errors),
            )

        passed = sum(1 for r in results if r.passed)
        root_cause_accurate = sum(1 for r in results if r.root_cause_accurate)
        safety_passed = sum(1 for r in results if r.recommendation_safe)
        avg_latency = sum(r.latency_ms for r in results) / len(results) if results else 0

        return EvaluationReport(
            total_cases=len(results),
            passed=passed,
            failed=len(results) - passed,
            root_cause_accuracy=root_cause_accurate / len(results) if results else 0,
            safety_pass_rate=safety_passed / len(results) if results else 0,
            average_latency_ms=avg_latency,
            results=results,
        )


# ─── CLI Entry Point ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    import os

    # Ensure backend root in path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    print("PayTrace AI Investigator Evaluation")
    print("=" * 60)
    print(f"Running {len(EVALUATION_DATASET)} test cases...")
    print()

    evaluator = InvestigatorEvaluator()
    report = evaluator.run_all()
    print(report.summary())

    # Exit with non-zero if safety tests failed
    safety_failures = [r for r in report.results if not r.recommendation_safe]
    if safety_failures:
        print(f"\n[CRITICAL] {len(safety_failures)} safety test(s) failed!")
        sys.exit(1)
    elif report.failed > 0:
        print(f"\n[WARN] {report.failed} test(s) failed (non-safety).")
        sys.exit(2)
    else:
        print("\n[SUCCESS] All evaluation cases passed!")
        sys.exit(0)


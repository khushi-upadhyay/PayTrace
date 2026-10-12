import uuid
from decimal import Decimal
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.models.incident import Incident
from app.db.models.payment import Payment

class IncidentDetector:
    """Evaluates payment patterns and evaluates deterministic threshold incident rules."""

    @staticmethod
    def evaluate_system_health(db: Session) -> List[Incident]:
        """Runs deterministic detection rules and returns active or new incidents."""
        incidents: List[Incident] = []

        # Rule 1: Check for Unresolved Capture Timeouts (CRITICAL)
        uncertain_payments = (
            db.query(Payment)
            .filter(Payment.status == "CAPTURE_UNCERTAIN")
            .all()
        )
        if len(uncertain_payments) >= 1:
            rev_at_risk = sum([p.amount for p in uncertain_payments], Decimal("0.00"))
            existing = (
                db.query(Incident)
                .filter(Incident.detection_rule == "CAPTURE_TIMEOUT_SPIKE", Incident.status != "RESOLVED")
                .first()
            )
            if existing:
                existing.affected_payment_count = len(uncertain_payments)
                existing.revenue_at_risk = rev_at_risk
                existing.updated_at = datetime.utcnow()
                incidents.append(existing)
            else:
                inc = Incident(
                    id=str(uuid.uuid4()),
                    title="Capture Timeout & Unresolved Backend State Spike",
                    severity="HIGH",
                    status="OPEN",
                    started_at=uncertain_payments[0].created_at,
                    affected_payment_count=len(uncertain_payments),
                    revenue_at_risk=rev_at_risk,
                    currency="USD",
                    detection_rule="CAPTURE_TIMEOUT_SPIKE",
                    root_cause="Merchant backend timed out while awaiting PayPal capture confirmation. Orders may be captured at PayPal but unconfirmed locally.",
                    confidence=0.92,
                    ai_summary="Detected ambiguous capture states. Merchant backend timed out before receiving the capture response. Automated retries halted to prevent duplicate charges.",
                )
                db.add(inc)
                incidents.append(inc)

        # Rule 2: Capture Denied / Declined Spikes (MEDIUM/HIGH)
        denied_payments = (
            db.query(Payment)
            .filter(Payment.status.in_(["DENIED", "CAPTURE_FAILED"]))
            .all()
        )
        if len(denied_payments) >= 2:
            rev_at_risk = sum([p.amount for p in denied_payments], Decimal("0.00"))
            existing = (
                db.query(Incident)
                .filter(Incident.detection_rule == "CAPTURE_DENIAL_RATE_HIGH", Incident.status != "RESOLVED")
                .first()
            )
            if existing:
                existing.affected_payment_count = len(denied_payments)
                existing.revenue_at_risk = rev_at_risk
                incidents.append(existing)
            else:
                inc = Incident(
                    id=str(uuid.uuid4()),
                    title="Elevated Capture Denial Rate (INSTRUMENT_DECLINED)",
                    severity="MEDIUM",
                    status="OPEN",
                    started_at=denied_payments[0].created_at,
                    affected_payment_count=len(denied_payments),
                    revenue_at_risk=rev_at_risk,
                    currency="USD",
                    detection_rule="CAPTURE_DENIAL_RATE_HIGH",
                    root_cause="Spike in buyer instrument declines during order capture.",
                    confidence=0.88,
                    ai_summary="Multiple checkout captures were declined by the issuer/PayPal. Recommend prompting buyers to select alternate funding methods.",
                )
                db.add(inc)
                incidents.append(inc)

        db.commit()
        return incidents

incident_detector = IncidentDetector()

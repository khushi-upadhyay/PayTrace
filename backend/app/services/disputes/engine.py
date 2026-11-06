import uuid
from datetime import timedelta
from typing import Optional
from sqlalchemy.orm import Session
from app.db.models.dispute import Dispute, DISPUTE_REASONS
from app.db.models.payment import Payment
from app.core.security import redact_sensitive_data
from app.core.time import utc_now
from app.services.lifecycle.engine import lifecycle_engine

# Mirrors PayPal's real-world dispute response SLA so the "time remaining"
# shown to an operator is a believable, deterministic number.
RESPONSE_WINDOW_DAYS = 10


class DisputeError(ValueError):
    """Raised for invalid dispute operations; routes map this to 4xx, never 5xx."""


class DisputeEngine:
    """Deterministic, clearly-labelled simulated dispute lifecycle tied to a payment."""

    @staticmethod
    def simulate_dispute(
        db: Session,
        payment_id: str,
        reason: str = "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
        buyer_statement: Optional[str] = None,
        requested_by: str = "operator",
    ) -> Dispute:
        payment = db.query(Payment).filter(Payment.id == payment_id).first()
        if not payment:
            raise DisputeError(f"Payment {payment_id} not found.")
        if payment.status != "CAPTURED":
            raise DisputeError(
                f"Only a CAPTURED payment can be disputed (current status: {payment.status})."
            )
        if reason not in DISPUTE_REASONS:
            raise DisputeError(f"Unknown dispute reason: {reason}")

        existing_open = (
            db.query(Dispute)
            .filter(Dispute.payment_id == payment_id, Dispute.status.in_(["OPEN", "UNDER_REVIEW"]))
            .first()
        )
        if existing_open:
            raise DisputeError(f"Payment {payment_id} already has an open dispute ({existing_open.id}).")

        now = utc_now()
        safe_statement = redact_sensitive_data(buyer_statement.strip()) if buyer_statement else None

        dispute = Dispute(
            id=str(uuid.uuid4()),
            payment_id=payment.id,
            paypal_dispute_id=f"MOCK-DISPUTE-{uuid.uuid4().hex[:10].upper()}",
            reason=reason,
            status="OPEN",
            amount=payment.amount,
            currency=payment.currency,
            buyer_statement=safe_statement,
            is_simulated=True,
            opened_at=now,
            response_due_by=now + timedelta(days=RESPONSE_WINDOW_DAYS),
        )
        db.add(dispute)

        lifecycle_engine.record_event(
            db=db,
            payment=payment,
            event_type="DISPUTE_OPENED",
            source="SIMULATED",
            status="UNCERTAIN",
            metadata={
                "dispute_id": dispute.id,
                "paypal_dispute_id": dispute.paypal_dispute_id,
                "reason": reason,
                "requested_by": requested_by,
            },
            is_simulated=True,
        )
        db.commit()
        db.refresh(dispute)
        return dispute

    @staticmethod
    def respond_to_dispute(
        db: Session,
        dispute_id: str,
        seller_response: str,
        accept_liability: bool,
        decided_by: str = "operator",
    ) -> Dispute:
        dispute = db.query(Dispute).filter(Dispute.id == dispute_id).first()
        if not dispute:
            raise DisputeError(f"Dispute {dispute_id} not found.")
        if dispute.status not in ("OPEN", "UNDER_REVIEW"):
            raise DisputeError(f"Dispute {dispute_id} is already in a terminal state ({dispute.status}).")

        if accept_liability:
            # Compare-and-set claim: of several simultaneous responses, exactly one may resolve the dispute.
            claimed = db.query(Dispute).filter(
                Dispute.id == dispute_id, Dispute.status.in_(("OPEN", "UNDER_REVIEW"))
            ).update({"status": "RESOLVED_BUYER_FAVOUR"}, synchronize_session=False)
            if not claimed:
                db.rollback()
                raise DisputeError(f"Dispute {dispute_id} is already in a terminal state.")
            db.refresh(dispute)

        payment = db.query(Payment).filter(Payment.id == dispute.payment_id).first()
        now = utc_now()
        dispute.seller_response = redact_sensitive_data(seller_response.strip())

        if accept_liability:
            dispute.status = "RESOLVED_BUYER_FAVOUR"
            dispute.outcome_note = (
                "Merchant accepted liability. In a live PayPal environment this would release funds "
                "back to the buyer; route an operator-approved refund through the Approvals inbox to "
                "reconcile PayTrace's own ledger."
            )
            dispute.resolved_at = now
        else:
            dispute.status = "UNDER_REVIEW"
            dispute.outcome_note = (
                "Evidence submitted for review. This sandbox does not call PayPal's live adjudication "
                "API, so PayTrace cannot fabricate a verdict; resolve manually once the real case closes."
            )

        if payment:
            lifecycle_engine.record_event(
                db=db,
                payment=payment,
                event_type="DISPUTE_RESPONSE_SUBMITTED",
                source="OPERATOR_UI",
                status="SUCCESS",
                metadata={
                    "dispute_id": dispute.id,
                    "accept_liability": accept_liability,
                    "new_status": dispute.status,
                    "decided_by": decided_by,
                },
                is_simulated=True,
            )
        db.commit()
        db.refresh(dispute)
        return dispute


dispute_engine = DisputeEngine()

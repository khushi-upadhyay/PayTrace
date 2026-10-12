import uuid
import logging
from decimal import Decimal
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from app.db.models.approval_ticket import ApprovalTicket
from app.db.models.payment import Payment
from app.services.lifecycle.engine import lifecycle_engine
from app.services.paypal.client import paypal_client
from app.services.paypal.mock_sandbox import mock_paypal
from app.core.config import settings

logger = logging.getLogger(__name__)

class PolicyEngine:
    """Enforces Human-in-the-Loop policy checks for sensitive financial actions like refunds."""

    @staticmethod
    def propose_refund(
        db: Session,
        payment_id: str,
        amount: Optional[Decimal] = None,
        reason: str = "Investigation recommendation",
        requested_by: str = "AI_INVESTIGATOR",
    ) -> ApprovalTicket:
        payment = db.query(Payment).filter(Payment.id == payment_id).first()
        if not payment:
            raise ValueError(f"Payment {payment_id} not found.")

        refund_amt = amount or payment.amount

        # Create pending approval ticket
        ticket = ApprovalTicket(
            id=str(uuid.uuid4()),
            payment_id=payment_id,
            action_type="REFUND",
            amount=refund_amt,
            currency=payment.currency,
            reason=reason,
            status="PENDING",
            requested_by=requested_by,
        )
        db.add(ticket)

        # Record proposal in payment timeline
        lifecycle_engine.record_event(
            db=db,
            payment=payment,
            event_type="REFUND_PROPOSED_WAITING_APPROVAL",
            source="POLICY_ENGINE",
            status="PENDING",
            metadata={
                "ticket_id": ticket.id,
                "amount": float(refund_amt),
                "reason": reason,
                "requested_by": requested_by,
            },
            is_simulated=payment.source_mode == "SIMULATED",
        )
        db.commit()
        db.refresh(ticket)
        return ticket

    @staticmethod
    async def decide_ticket(
        db: Session,
        ticket_id: str,
        decision: str, # "APPROVED" or "DENIED"
        decided_by: str = "operator",
        operator_token: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Tuple[ApprovalTicket, Optional[Dict[str, Any]]]:
        ticket = db.query(ApprovalTicket).filter(ApprovalTicket.id == ticket_id).first()
        if not ticket:
            raise ValueError(f"Approval ticket {ticket_id} not found.")

        if ticket.status != "PENDING":
            raise ValueError(f"Ticket {ticket_id} is already in state {ticket.status}.")

        ticket.decided_by = decided_by
        ticket.decided_at = datetime.utcnow()

        payment = db.query(Payment).filter(Payment.id == ticket.payment_id).first()

        if decision.upper() == "DENIED":
            ticket.status = "DENIED"
            if payment:
                lifecycle_engine.record_event(
                    db=db,
                    payment=payment,
                    event_type="REFUND_DENIED_BY_OPERATOR",
                    source="POLICY_ENGINE",
                    status="FAILED",
                    metadata={"ticket_id": ticket.id, "decided_by": decided_by, "notes": notes},
                    is_simulated=payment.source_mode == "SIMULATED",
                )
            db.commit()
            return ticket, None

        if decision.upper() == "APPROVED":
            ticket.status = "APPROVED"
            execution_res: Dict[str, Any] = {}

            if payment and payment.source_mode == "SIMULATED":
                # Simulated refund
                execution_res = {
                    "id": f"MOCK-REFUND-{uuid.uuid4().hex[:8].upper()}",
                    "status": "COMPLETED",
                    "amount": {"value": str(ticket.amount), "currency_code": ticket.currency},
                    "note": notes or "Refund approved in demo mode",
                }
                ticket.status = "EXECUTED"
                ticket.paypal_result_redacted = execution_res
                lifecycle_engine.transition_status(payment, "REFUNDED")
                lifecycle_engine.record_event(
                    db=db,
                    payment=payment,
                    event_type="REFUND_EXECUTED_SUCCESS",
                    source="SIMULATED",
                    status="SUCCESS",
                    metadata=execution_res,
                    is_simulated=True,
                )
            elif payment and payment.paypal_capture_id and settings.is_paypal_configured:
                try:
                    res = await paypal_client.refund_capture(
                        capture_id=payment.paypal_capture_id,
                        amount=ticket.amount,
                        currency=ticket.currency,
                        note=notes or ticket.reason,
                    )
                    ticket.status = "EXECUTED"
                    ticket.paypal_result_redacted = res
                    lifecycle_engine.transition_status(payment, "REFUNDED")
                    lifecycle_engine.record_event(
                        db=db,
                        payment=payment,
                        event_type="REFUND_EXECUTED_SUCCESS",
                        source="PAYPAL_API",
                        status="SUCCESS",
                        metadata=res,
                    )
                    execution_res = res
                except Exception as e:
                    logger.error(f"Refund execution failed: {e}")
                    ticket.status = "FAILED"
                    ticket.paypal_result_redacted = {"error": str(e)}
            else:
                # No live capture ID available
                execution_res = {
                    "status": "COMPLETED_MANUAL",
                    "note": "Reconciled and marked refunded locally"
                }
                ticket.status = "EXECUTED"
                ticket.paypal_result_redacted = execution_res
                if payment:
                    lifecycle_engine.transition_status(payment, "REFUNDED")

            db.commit()
            return ticket, execution_res

        raise ValueError(f"Invalid decision '{decision}'. Must be APPROVED or DENIED.")

policy_engine = PolicyEngine()

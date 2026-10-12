import uuid
import logging
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.api.dependencies import get_db
from app.db.models.payment import Payment
from app.schemas.paypal import (
    OrderCreateRequest,
    OrderCreateResponse,
    OrderCaptureRequest,
    OrderCaptureResponse,
    RefundRequest,
    RefundResponse,
)
from app.services.paypal.client import paypal_client
from app.services.paypal.mock_sandbox import mock_paypal
from app.services.lifecycle.engine import lifecycle_engine
from app.services.policy.engine import policy_engine
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/paypal", tags=["PayPal"])

@router.post("/orders", response_model=OrderCreateResponse)
async def create_order(req: OrderCreateRequest, db: Session = Depends(get_db)):
    """Creates a PayPal Sandbox order and registers a local PayTrace payment."""
    payment_id = str(uuid.uuid4())
    is_mock = not settings.is_paypal_configured

    paypal_order_id = ""
    approval_url = None

    if settings.is_paypal_configured:
        try:
            order_data = await paypal_client.create_order(
                amount=req.amount,
                currency=req.currency,
                custom_id=payment_id,
            )
            paypal_order_id = order_data["id"]
            for link in order_data.get("links", []):
                if link.get("rel") == "approve":
                    approval_url = link.get("href")
        except Exception as e:
            logger.warning(f"PayPal Sandbox order creation failed, falling back to mock sandbox: {e}")
            is_mock = True

    if is_mock:
        order_data = mock_paypal.create_order(
            amount=req.amount,
            currency=req.currency,
            custom_id=payment_id,
        )
        paypal_order_id = order_data["id"]
        approval_url = order_data["links"][0]["href"]

    # Persist Payment record
    payment = Payment(
        id=payment_id,
        paypal_order_id=paypal_order_id,
        customer_ref=req.customer_ref,
        session_id=req.session_id,
        amount=req.amount,
        currency=req.currency,
        status="CREATED",
        actor="demo" if req.simulate_scenario else "human",
        source_mode="SIMULATED" if is_mock else "PAYPAL_SANDBOX",
        failure_code=req.simulate_scenario if req.simulate_scenario else None,
    )
    db.add(payment)

    # Append Timeline Event
    lifecycle_engine.record_event(
        db=db,
        payment=payment,
        event_type="CHECKOUT_ORDER_CREATED",
        source="PAYPAL_API" if not is_mock else "SIMULATED",
        status="SUCCESS",
        latency_ms=280 if not is_mock else 45,
        paypal_order_id=paypal_order_id,
        metadata={"amount": float(req.amount), "currency": req.currency, "is_mock": is_mock},
        is_simulated=is_mock,
    )
    db.commit()

    return OrderCreateResponse(
        payment_id=payment.id,
        paypal_order_id=paypal_order_id,
        status="CREATED",
        approval_url=approval_url,
        is_mock=is_mock,
    )

@router.get("/orders/{order_id}")
async def get_order_details(order_id: str, db: Session = Depends(get_db)):
    """Reconciles provider order status directly with PayPal."""
    if settings.is_paypal_configured:
        try:
            return await paypal_client.get_order(order_id)
        except Exception as e:
            logger.warning(f"Failed to fetch live order {order_id}: {e}")
    return mock_paypal.get_order(order_id)

@router.post("/orders/{order_id}/capture", response_model=OrderCaptureResponse)
async def capture_order(
    order_id: str,
    req: OrderCaptureRequest = OrderCaptureRequest(),
    db: Session = Depends(get_db),
):
    """
    Captures an approved PayPal order.
    Demonstrates safe unknown-outcome handling on merchant backend timeouts.
    """
    payment = db.query(Payment).filter(Payment.paypal_order_id == order_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail=f"No payment linked to order {order_id}")

    # Record buyer approval event prior to capture
    lifecycle_engine.record_event(
        db=db,
        payment=payment,
        event_type="CHECKOUT_ORDER_APPROVED",
        source="FRONTEND",
        status="SUCCESS",
        paypal_order_id=order_id,
        is_simulated=payment.source_mode == "SIMULATED",
    )
    lifecycle_engine.transition_status(payment, "APPROVED")

    # CRITICAL SCENARIO: Simulated backend timeout before receiving response
    if req.simulate_timeout or payment.failure_code == "timeout_before_response":
        # Simulate that in PayPal's system, capture was created (id: MOCK-CAP-...)
        # but the merchant's HTTP connection timed out before the 200 OK could be received!
        simulated_capture_id = f"MOCK-CAP-{uuid.uuid4().hex[:10].upper()}"
        payment.paypal_capture_id = simulated_capture_id
        lifecycle_engine.transition_status(
            payment,
            new_status="CAPTURE_UNCERTAIN",
            failure_code="TIMEOUT_BEFORE_RESPONSE",
            failure_reason="Merchant backend timed out (HTTP 504/timeout >5000ms) before receiving capture response from PayPal.",
        )
        lifecycle_engine.record_event(
            db=db,
            payment=payment,
            event_type="CAPTURE_REQUEST_TIMEOUT",
            source="SIMULATED",
            status="UNCERTAIN",
            latency_ms=5240,
            paypal_order_id=order_id,
            paypal_capture_id=simulated_capture_id,
            metadata={
                "error": "ReadTimeout: merchant backend waited 5.2s with no response",
                "risk": "Provider may have processed capture; blind retry prohibited to avoid duplicate charges.",
            },
            is_simulated=True,
        )
        db.commit()

        return OrderCaptureResponse(
            payment_id=payment.id,
            paypal_order_id=order_id,
            paypal_capture_id=simulated_capture_id,
            status="CAPTURE_UNCERTAIN",
            failure_code="TIMEOUT_BEFORE_RESPONSE",
            failure_reason="Merchant backend timed out waiting for PayPal response. Do NOT retry blindly. Reconcile provider state first.",
            reconciliation_required=True,
            details={"advice": "Call GET /paypal/orders/{order_id} or await webhook confirmation."},
        )

    # Normal execution (Real or Mock)
    is_mock = payment.source_mode == "SIMULATED" or not settings.is_paypal_configured
    capture_data = {}

    if not is_mock:
        try:
            capture_data = await paypal_client.capture_order(order_id)
        except Exception as e:
            logger.warning(f"Live capture failed: {e}")
            is_mock = True

    if is_mock:
        scenario = "capture_denied" if payment.failure_code == "capture_denied" else None
        capture_data = mock_paypal.capture_order(order_id, simulate_scenario=scenario)

    # Inspect capture outcome
    payments_data = capture_data.get("purchase_units", [{}])[0].get("payments", {})
    captures = payments_data.get("captures", [{}])
    first_capture = captures[0] if captures else {}
    capture_id = first_capture.get("id")
    cap_status = first_capture.get("status", "COMPLETED")

    payment.paypal_capture_id = capture_id

    if cap_status == "DECLINED" or cap_status == "DENIED":
        reason = first_capture.get("status_details", {}).get("reason", "INSTRUMENT_DECLINED")
        lifecycle_engine.transition_status(payment, "DENIED", failure_code="INSTRUMENT_DECLINED", failure_reason=reason)
        lifecycle_engine.record_event(
            db=db,
            payment=payment,
            event_type="CAPTURE_DENIED",
            source="PAYPAL_API" if not is_mock else "SIMULATED",
            status="FAILED",
            latency_ms=620,
            paypal_order_id=order_id,
            paypal_capture_id=capture_id,
            metadata={"decline_reason": reason},
            is_simulated=is_mock,
        )
        db.commit()
        return OrderCaptureResponse(
            payment_id=payment.id,
            paypal_order_id=order_id,
            paypal_capture_id=capture_id,
            status="DENIED",
            failure_code="INSTRUMENT_DECLINED",
            failure_reason=reason,
            reconciliation_required=False,
            details=capture_data,
        )

    # Success
    lifecycle_engine.transition_status(payment, "CAPTURED")
    lifecycle_engine.record_event(
        db=db,
        payment=payment,
        event_type="CAPTURE_COMPLETED",
        source="PAYPAL_API" if not is_mock else "SIMULATED",
        status="SUCCESS",
        latency_ms=480 if not is_mock else 65,
        paypal_order_id=order_id,
        paypal_capture_id=capture_id,
        metadata={"capture_status": "COMPLETED"},
        is_simulated=is_mock,
    )
    db.commit()

    return OrderCaptureResponse(
        payment_id=payment.id,
        paypal_order_id=order_id,
        paypal_capture_id=capture_id,
        status="CAPTURED",
        reconciliation_required=False,
        details=capture_data,
    )

@router.post("/payments/{payment_id}/refund", response_model=RefundResponse)
def request_refund(payment_id: str, req: RefundRequest, db: Session = Depends(get_db)):
    """Submits a refund proposal to the Human Approval Inbox."""
    try:
        ticket = policy_engine.propose_refund(
            db=db,
            payment_id=payment_id,
            amount=req.amount,
            reason=req.reason,
            requested_by="OPERATOR_UI",
        )
        return RefundResponse(
            ticket_id=ticket.id,
            status="PENDING_APPROVAL",
            message="Refund proposal submitted. Awaiting human operator approval in Inbox.",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

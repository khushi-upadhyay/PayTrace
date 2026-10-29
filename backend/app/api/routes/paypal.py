import uuid
import logging
import httpx
from decimal import Decimal, InvalidOperation
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_user, get_db
from app.db.models.payment import Payment
from app.db.models.user import User
from app.schemas.paypal import (
    OrderCreateRequest,
    OrderCreateResponse,
    OrderCaptureRequest,
    OrderCaptureResponse,
    RefundRequest,
    RefundResponse,
)
from app.services.paypal.client import (
    paypal_client,
    safe_paypal_error_diagnostics,
    validate_created_order_amount,
)
from app.services.paypal.mock_sandbox import mock_paypal
from app.services.lifecycle.engine import lifecycle_engine
from app.services.policy.engine import policy_engine
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/paypal", tags=["PayPal"])


def _capture_records(provider_order: dict) -> list[dict]:
    units = provider_order.get("purchase_units")
    if not isinstance(units, list):
        raise ValueError("missing_purchase_units")
    captures = []
    for unit in units:
        if not isinstance(unit, dict):
            continue
        payments = unit.get("payments")
        if not isinstance(payments, dict):
            continue
        unit_captures = payments.get("captures")
        if isinstance(unit_captures, list):
            captures.extend(item for item in unit_captures if isinstance(item, dict))
    return captures


def _completed_capture(provider_order: dict, payment: Payment) -> dict:
    """Return exactly one completed capture matching the local order amount/currency."""
    captures = _capture_records(provider_order)
    completed = [item for item in captures if item.get("status") == "COMPLETED"]
    if len(completed) != 1:
        raise ValueError("expected_one_completed_capture")
    capture = completed[0]
    capture_id = capture.get("id")
    amount = capture.get("amount")
    if not isinstance(capture_id, str) or not capture_id.strip():
        raise ValueError("missing_capture_id")
    if not isinstance(amount, dict) or not isinstance(amount.get("currency_code"), str):
        raise ValueError("missing_capture_amount_or_currency")
    try:
        actual_amount = Decimal(str(amount.get("value")))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("malformed_capture_amount")
    if not actual_amount.is_finite() or actual_amount != Decimal(str(payment.amount)):
        raise ValueError("capture_amount_mismatch")
    if amount["currency_code"] != payment.currency:
        raise ValueError("capture_currency_mismatch")
    return capture


def _commit_capture_or_reconcile(db: Session, payment: Payment, order_id: str) -> None:
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("PayPal capture confirmed but PayTrace persistence failed", extra={"paypal_order_id": order_id})
        raise HTTPException(
            status_code=503,
            detail="PayPal capture state could not be saved. Retry reconciliation; PayTrace will check PayPal before any further capture.",
        ) from exc


def _validate_payment_environment(payment: Payment) -> None:
    if not payment.source_mode.startswith("PAYPAL_"):
        return
    if not settings.is_paypal_configured:
        raise HTTPException(status_code=503, detail="PayPal credentials are not configured for this real order")
    recorded_mode = payment.source_mode.removeprefix("PAYPAL_").lower()
    if recorded_mode != settings.paypal_mode:
        raise HTTPException(
            status_code=409,
            detail=f"Order belongs to PayPal {recorded_mode}; current API is configured for {settings.paypal_mode}",
        )

@router.post("/orders", response_model=OrderCreateResponse)
async def create_order(req: OrderCreateRequest, db: Session = Depends(get_db)):
    """Creates a PayPal Sandbox order and registers a local PayTrace payment."""
    payment_id = str(uuid.uuid4())
    # Deterministic demo simulation takes precedence if explicitly requested or if PayPal is not configured
    is_mock = bool(req.simulate_scenario) or not settings.is_paypal_configured

    paypal_order_id = ""
    approval_url = None

    if not is_mock:
        try:
            order_data = await paypal_client.create_order(
                amount=req.amount,
                currency=req.currency,
                custom_id=payment_id,
            )
            validate_created_order_amount(order_data, req.amount, req.currency)
            paypal_order_id = order_data["id"]
            for link in order_data.get("links", []):
                if link.get("rel") == "approve":
                    approval_url = link.get("href")
        except Exception as e:
            diagnostics = (
                safe_paypal_error_diagnostics(e)
                if isinstance(e, httpx.HTTPStatusError)
                else {
                    "http_status": None,
                    "error_type": type(e).__name__,
                    "validation_reason": str(e) if isinstance(e, ValueError) else None,
                }
            )
            diagnostics.update({
                "requested_amount": f"{req.amount:.2f}",
                "requested_currency": req.currency,
            })
            logger.error("PayPal Sandbox order creation failed", extra={"paypal_diagnostics": diagnostics})
            if isinstance(e, httpx.HTTPStatusError):
                error_description = "; ".join(
                    part for part in (
                        diagnostics.get("error_name"),
                        ",".join(diagnostics.get("issues", [])) or None,
                        f"debug_id={diagnostics['debug_id']}" if diagnostics.get("debug_id") else None,
                    ) if part
                )
                detail = f"PayPal Sandbox rejected order creation (HTTP {diagnostics['http_status']})"
                if error_description:
                    detail += f": {error_description}"
            else:
                detail = f"Failed to create order on PayPal Sandbox: {str(e)}"
            raise HTTPException(
                status_code=502,
                detail=detail,
            )

    if is_mock:
        order_data = mock_paypal.create_order(
            amount=req.amount,
            currency=req.currency,
            custom_id=payment_id,
        )
        paypal_order_id = order_data["id"]
        approval_url = f"{settings.FRONTEND_ORIGIN}/demo/approval?token={paypal_order_id}&return_to=checkout"

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
        source_mode="SIMULATED" if is_mock else f"PAYPAL_{settings.paypal_mode.upper()}",
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
    payment = db.query(Payment).filter(Payment.paypal_order_id == order_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail=f"No payment linked to order {order_id}")
    _validate_payment_environment(payment)
    if payment.source_mode.startswith("PAYPAL_"):
        try:
            return await paypal_client.get_order(order_id)
        except Exception as e:
            logger.warning(f"Failed to fetch live order {order_id}: {e}")
            raise HTTPException(status_code=502, detail=f"Failed to fetch live PayPal order: {str(e)}")
    try:
        return mock_paypal.get_order(order_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Simulated order {order_id} is unavailable")

@router.post("/orders/{order_id}/approve")
def approve_mock_order(order_id: str, db: Session = Depends(get_db)):
    """Completes the buyer approval step for a simulated PayPal order."""
    payment = db.query(Payment).filter(Payment.paypal_order_id == order_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail=f"No payment linked to order {order_id}")
    if payment.source_mode != "SIMULATED":
        raise HTTPException(status_code=400, detail="Only simulated orders can use mock approval")
    try:
        return mock_paypal.approve_order(order_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Mock order {order_id} was not found")

@router.post("/orders/{order_id}/capture", response_model=OrderCaptureResponse)
async def capture_order(
    order_id: str,
    req: OrderCaptureRequest = OrderCaptureRequest(),
    db: Session = Depends(get_db),
):
    """
    Captures an approved PayPal order.
    Demonstrates safe unknown-outcome handling on merchant backend timeouts and duplicate prevention.
    """
    payment = db.query(Payment).filter(Payment.paypal_order_id == order_id).with_for_update().first()
    if not payment:
        raise HTTPException(status_code=404, detail=f"No payment linked to order {order_id}")

    # Idempotency / Duplicate Capture Guard: If already captured or refunded, return existing state
    if payment.status == "REFUNDED" or (payment.status == "CAPTURED" and payment.paypal_capture_id):
        return OrderCaptureResponse(
            payment_id=payment.id,
            paypal_order_id=order_id,
            paypal_capture_id=payment.paypal_capture_id,
            status=payment.status,
            reconciliation_required=False,
            details={"message": f"Payment already in terminal state: {payment.status}. Duplicate capture prevented."},
        )

    # Verify the provider state before every capture, including simulated orders.
    _validate_payment_environment(payment)
    is_mock = payment.source_mode == "SIMULATED"

    try:
        if is_mock:
            provider_order = mock_paypal.get_order(order_id)
        else:
            live_order = await paypal_client.get_order(order_id)
            provider_order = live_order
        provider_status = provider_order.get("status")
        if payment.status == "CAPTURED" and provider_status != "COMPLETED":
            raise HTTPException(
                status_code=502,
                detail="PayTrace has a captured state without a capture ID, but PayPal does not confirm completion. No capture was issued.",
            )
        if provider_status not in ("APPROVED", "COMPLETED"):
            logger.warning(f"Attempted to capture order {order_id} with PayPal status '{provider_status}'.")
            raise HTTPException(
                status_code=422,
                detail=f"Order {order_id} cannot be captured because buyer has not approved it (current PayPal status: {provider_status})."
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to check order approval for {order_id}: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Unable to verify order approval status from PayPal: {str(e)}"
        )

    if provider_status == "COMPLETED":
        try:
            capture = _completed_capture(provider_order, payment)
        except ValueError as exc:
            logger.error(
                "Completed PayPal order did not contain a valid matching capture",
                extra={"paypal_order_id": order_id, "validation_reason": str(exc)},
            )
            raise HTTPException(status_code=502, detail="PayPal reports a completed order, but its capture details could not be safely reconciled.") from exc
        capture_id = capture["id"]
        payment.paypal_capture_id = capture_id
        lifecycle_engine.transition_status(payment, "CAPTURED")
        lifecycle_engine.record_event(
            db,
            payment,
            "CAPTURE_RECONCILED",
            "PAYPAL_API",
            "SUCCESS",
            paypal_order_id=order_id,
            paypal_capture_id=payment.paypal_capture_id,
            metadata={
                "provider_order_status": "COMPLETED",
                "already_captured": True,
                "capture_status": capture["status"],
                "capture_amount": capture["amount"]["value"],
                "capture_currency": capture["amount"]["currency_code"],
            },
            is_simulated=is_mock,
        )
        _commit_capture_or_reconcile(db, payment, order_id)
        return OrderCaptureResponse(
            payment_id=payment.id,
            paypal_order_id=order_id,
            paypal_capture_id=payment.paypal_capture_id,
            status="CAPTURED",
            reconciliation_required=False,
            details={"message": "Provider order was already completed; local state was reconciled without another capture request."},
        )

    # Record buyer approval event prior to capture if not already marked APPROVED
    if payment.status != "APPROVED":
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
    capture_data = {}

    if not is_mock:
        try:
            capture_data = await paypal_client.capture_order(order_id, idempotency_key=payment.id)
        except Exception as e:
            error_detail = str(e)
            paypal_error_body = None
            status_code = 502
            if isinstance(e, httpx.HTTPStatusError):
                status_code = e.response.status_code
                try:
                    paypal_error_body = e.response.json()
                    error_detail = paypal_error_body.get("message") or paypal_error_body.get("name") or e.response.text
                except Exception:
                    error_detail = e.response.text

            logger.error(f"Live PayPal capture failed for order {order_id}: {error_detail}")
            lifecycle_engine.transition_status(
                payment,
                "CAPTURE_FAILED",
                failure_code="ORDER_NOT_APPROVED" if status_code == 422 else "PAYPAL_API_ERROR",
                failure_reason=error_detail,
            )
            lifecycle_engine.record_event(
                db=db,
                payment=payment,
                event_type="CAPTURE_FAILED",
                source="PAYPAL_API",
                status="FAILED",
                latency_ms=450,
                paypal_order_id=order_id,
                metadata={"error": error_detail, "status_code": status_code, "paypal_response": paypal_error_body},
                is_simulated=False,
            )
            db.commit()
            raise HTTPException(
                status_code=status_code if status_code in (400, 422) else 502,
                detail=f"PayPal capture failed ({status_code}): {error_detail}"
            )

    if is_mock:
        scenario = "capture_denied" if payment.failure_code == "capture_denied" else None
        capture_data = mock_paypal.capture_order(order_id, simulate_scenario=scenario)

    # Require PayPal's actual capture object. If the capture response is minimal,
    # reconcile with GET; never infer success from a missing status or retry capture here.
    try:
        response_captures = _capture_records(capture_data)
        if len(response_captures) == 1 and response_captures[0].get("status") in ("DECLINED", "DENIED", "PENDING"):
            first_capture = response_captures[0]
            if not isinstance(first_capture.get("id"), str) or not first_capture["id"].strip():
                raise ValueError("missing_capture_id")
        else:
            first_capture = _completed_capture(capture_data, payment)
    except ValueError:
        try:
            reconciled_order = await (
                mock_paypal.get_order(order_id) if is_mock else paypal_client.get_order(order_id)
            )
            if reconciled_order.get("status") == "COMPLETED":
                capture_data = reconciled_order
                first_capture = _completed_capture(capture_data, payment)
            else:
                raise ValueError("provider_order_not_completed")
        except Exception as exc:
            logger.error(
                "PayPal capture response could not be safely reconciled",
                extra={"paypal_order_id": order_id, "validation_reason": str(exc)},
            )
            db.rollback()
            raise HTTPException(
                status_code=502,
                detail="PayPal capture outcome could not be verified. Retry reconciliation; no second capture was issued.",
            ) from exc
    capture_id = first_capture["id"]
    cap_status = first_capture["status"]
    payment.paypal_capture_id = capture_id

    if cap_status in ("DECLINED", "DENIED"):
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
            metadata={"decline_reason": reason, "capture_status": cap_status, "capture_amount": first_capture.get("amount", {}).get("value"), "capture_currency": first_capture.get("amount", {}).get("currency_code")},
            is_simulated=is_mock,
        )
        _commit_capture_or_reconcile(db, payment, order_id)
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

    if cap_status == "PENDING":
        pending_reason = first_capture.get("status_details", {}).get("reason", "PENDING_REVIEW")
        lifecycle_engine.transition_status(payment, "PENDING", failure_code="CAPTURE_PENDING", failure_reason=pending_reason)
        lifecycle_engine.record_event(
            db=db,
            payment=payment,
            event_type="CAPTURE_PENDING",
            source="PAYPAL_API" if not is_mock else "SIMULATED",
            status="PENDING",
            latency_ms=410,
            paypal_order_id=order_id,
            paypal_capture_id=capture_id,
            metadata={"pending_reason": pending_reason, "capture_status": cap_status, "capture_amount": first_capture.get("amount", {}).get("value"), "capture_currency": first_capture.get("amount", {}).get("currency_code")},
            is_simulated=is_mock,
        )
        _commit_capture_or_reconcile(db, payment, order_id)
        return OrderCaptureResponse(
            payment_id=payment.id,
            paypal_order_id=order_id,
            paypal_capture_id=capture_id,
            status="PENDING",
            failure_code="CAPTURE_PENDING",
            failure_reason=pending_reason,
            reconciliation_required=True,
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
        metadata={
            "capture_status": cap_status,
            "capture_amount": first_capture["amount"]["value"],
            "capture_currency": first_capture["amount"]["currency_code"],
            "final_capture": first_capture.get("final_capture"),
        },
        is_simulated=is_mock,
    )
    _commit_capture_or_reconcile(db, payment, order_id)

    return OrderCaptureResponse(
        payment_id=payment.id,
        paypal_order_id=order_id,
        paypal_capture_id=capture_id,
        status="CAPTURED",
        reconciliation_required=False,
        details=capture_data,
    )

@router.post("/payments/{payment_id}/refund", response_model=RefundResponse)
def request_refund(payment_id: str, req: RefundRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
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

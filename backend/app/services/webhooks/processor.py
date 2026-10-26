import uuid
import logging
from decimal import Decimal, InvalidOperation
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from app.db.models.webhook import PayPalWebhook
from app.db.models.payment import Payment
from app.db.models.shelfswipe import ShelfProduct
from app.services.lifecycle.engine import lifecycle_engine
from app.core.security import redact_sensitive_data
from app.services.paypal.client import paypal_client
from app.core.config import settings
from app.core.time import utc_now

logger = logging.getLogger(__name__)

class WebhookProcessor:
    """Processes, verifies, deduplicates, and correlates PayPal Webhook events."""

    @staticmethod
    async def process_webhook(
        db: Session,
        payload: Dict[str, Any],
        headers: Dict[str, str],
        raw_body: bytes,
        skip_verification_for_test: bool = False,
    ) -> Tuple[str, str, Optional[str]]:
        """
        Returns (status, message, payment_id).
        Statuses: PROCESSED, IGNORED_DUPLICATE, VERIFICATION_FAILED, UNMATCHED
        """
        if not isinstance(payload, dict):
            return "INVALID_PAYLOAD", "Webhook body must be a JSON object", None

        event_id = payload.get("id")
        event_type = payload.get("event_type", "UNKNOWN")
        resource_type = payload.get("resource_type", "capture")
        resource = payload.get("resource", {})
        if not isinstance(event_id, str) or not event_id.strip() or len(event_id) > 64:
            return "INVALID_PAYLOAD", "Missing webhook event id", None
        if not isinstance(event_type, str) or not event_type or len(event_type) > 64:
            return "INVALID_PAYLOAD", "Invalid webhook event type", None
        if not isinstance(resource_type, str) or not resource_type or len(resource_type) > 64:
            return "INVALID_PAYLOAD", "Invalid webhook resource type", None
        if not isinstance(resource, dict):
            return "INVALID_PAYLOAD", "Webhook resource must be a JSON object", None

        # 1. Idempotency Check
        existing_wh = db.query(PayPalWebhook).filter(PayPalWebhook.webhook_event_id == event_id).first()
        if existing_wh:
            logger.info(f"Duplicate webhook received: {event_id}. Skipping processing.")
            return "IGNORED_DUPLICATE", f"Webhook event {event_id} already ingested (idempotent)", existing_wh.payment_id

        # 2. Signature verification
        is_verified = False
        if skip_verification_for_test or (
            settings.APP_ENV == "test" and headers.get("x-mock-webhook") == "true"
        ):
            is_verified = True
        elif settings.is_paypal_configured and settings.PAYPAL_WEBHOOK_ID:
            try:
                is_verified = await paypal_client.verify_webhook_signature(headers, raw_body)
            except Exception as e:
                logger.warning(f"Webhook signature verification failed with error: {e}")
                is_verified = False
        else:
            logger.warning("PayPal Webhook ID or credentials are not configured; webhook cannot be verified.")

        # Never apply or correlate an event unless its signature was verified.
        if not is_verified:
            logger.warning(f"Rejecting unverified webhook event {event_id} of type {event_type}")
            wh_record = PayPalWebhook(
                id=str(uuid.uuid4()),
                webhook_event_id=event_id,
                event_type=event_type,
                resource_type=resource_type,
                payment_id=None,
                payload_redacted=redact_sensitive_data(payload),
                received_at=utc_now(),
                processed_at=utc_now(),
                processing_status="VERIFICATION_FAILED",
                processing_error="PayPal signature could not be verified; event was not applied",
                signature_verified=False,
            )
            db.add(wh_record)
            db.commit()
            return "VERIFICATION_FAILED", f"Webhook signature verification failed for event {event_id}", None

        # 3. Correlation: Find Payment by order_id, capture_id, or custom_id
        supplementary_data = resource.get("supplementary_data")
        if not isinstance(supplementary_data, dict):
            supplementary_data = {}
        related_ids = supplementary_data.get("related_ids")
        if not isinstance(related_ids, dict):
            related_ids = {}
        order_id = related_ids.get("order_id")
        if not isinstance(order_id, str):
            order_id = None
        if not order_id and resource_type in ("checkout-order", "order"):
            order_id = resource.get("id")

        capture_id = resource.get("id") if "CAPTURE" in event_type else None
        if not isinstance(capture_id, str):
            capture_id = None
        custom_id = resource.get("custom_id")
        if not isinstance(custom_id, str):
            custom_id = None

        payment: Optional[Payment] = None
        if custom_id:
            payment = db.query(Payment).filter(Payment.id == custom_id).first()
        if not payment and order_id:
            payment = db.query(Payment).filter(Payment.paypal_order_id == order_id).first()
        if not payment and capture_id:
            payment = db.query(Payment).filter(Payment.paypal_capture_id == capture_id).first()

        # A signed capture-completed event is still not sufficient to mutate payment state
        # unless its resource proves the actual capture ID, status, amount, and currency.
        capture_amount = None
        capture_currency = None
        if event_type == "PAYMENT.CAPTURE.COMPLETED" and payment:
            amount = resource.get("amount")
            if not isinstance(capture_id, str) or not capture_id.strip():
                return "INVALID_CAPTURE", "Capture event is missing the PayPal capture ID", payment.id
            if payment.paypal_capture_id and payment.paypal_capture_id != capture_id:
                return "INVALID_CAPTURE", "Capture event ID conflicts with the PayTrace capture ID", payment.id
            if resource.get("status") != "COMPLETED":
                return "INVALID_CAPTURE", "Capture event resource is not completed", payment.id
            if not isinstance(amount, dict):
                return "INVALID_CAPTURE", "Capture event is missing amount details", payment.id
            capture_currency = amount.get("currency_code")
            try:
                capture_amount = Decimal(str(amount.get("value")))
            except (InvalidOperation, TypeError, ValueError):
                return "INVALID_CAPTURE", "Capture event amount is malformed", payment.id
            if (not capture_amount.is_finite() or capture_amount != Decimal(str(payment.amount))
                    or capture_currency != payment.currency):
                return "INVALID_CAPTURE", "Capture event amount or currency does not match the PayTrace order", payment.id

        payment_id = payment.id if payment else None

        # 4. Save Webhook Record
        wh_record = PayPalWebhook(
            id=str(uuid.uuid4()),
            webhook_event_id=event_id,
            event_type=event_type,
            resource_type=resource_type,
            payment_id=payment_id,
            payload_redacted=redact_sensitive_data(payload),
            received_at=utc_now(),
            processed_at=utc_now(),
            processing_status="PROCESSED" if payment else "UNMATCHED",
            signature_verified=is_verified,
        )
        db.add(wh_record)

        # 5. Attach event to lifecycle and update payment status if correlated
        if payment:
            if capture_id and not payment.paypal_capture_id:
                payment.paypal_capture_id = capture_id

            # Append to timeline
            lifecycle_engine.record_event(
                db=db,
                payment=payment,
                event_type=f"WEBHOOK_{event_type.replace('.', '_')}",
                source="PAYPAL_WEBHOOK",
                status="SUCCESS",
                paypal_order_id=order_id,
                paypal_capture_id=capture_id,
                metadata={
                    "webhook_event_id": event_id,
                    "event_type": event_type,
                    "summary": payload.get("summary", ""),
                    "signature_verified": is_verified,
                    **({
                        "capture_status": resource.get("status"),
                        "capture_amount": str(capture_amount),
                        "capture_currency": capture_currency,
                    } if event_type == "PAYMENT.CAPTURE.COMPLETED" else {}),
                },
                is_simulated=payment.source_mode == "SIMULATED",
            )

            # Concurrency and valid state transitions (do not regress terminal states)
            current_status = payment.status

            if event_type == "PAYMENT.CAPTURE.COMPLETED":
                if current_status != "REFUNDED":
                    lifecycle_engine.transition_status(payment, "CAPTURED")
                prior_capture_webhook = any(
                    event.event_type == "WEBHOOK_PAYMENT_CAPTURE_COMPLETED"
                    and event.paypal_capture_id == capture_id
                    and (event.metadata_redacted or {}).get("webhook_event_id") != event_id
                    for event in payment.events
                )
                if capture_id and not prior_capture_webhook:
                    for event in payment.events:
                        metadata = event.metadata_redacted or {}
                        product_name = metadata.get("product_name")
                        if product_name:
                            product = db.query(ShelfProduct).filter(ShelfProduct.name == product_name).first()
                            if product and product.stock > 0:
                                quantity = metadata.get("quantity", 1)
                                product.stock = max(0, product.stock - quantity)
                                break
            elif event_type == "PAYMENT.CAPTURE.DENIED":
                if current_status not in ("CAPTURED", "REFUNDED"):
                    reason = resource.get("status_details", {}).get("reason", "Capture Denied by PayPal")
                    lifecycle_engine.transition_status(payment, "DENIED", failure_code="CAPTURE_DENIED", failure_reason=reason)
            elif event_type == "PAYMENT.CAPTURE.PENDING":
                if current_status not in ("CAPTURED", "DENIED", "REFUNDED"):
                    pending_reason = resource.get("status_details", {}).get("reason", "Capture Pending Review")
                    lifecycle_engine.transition_status(payment, "PENDING", failure_code="CAPTURE_PENDING", failure_reason=pending_reason)
            elif event_type == "CHECKOUT.ORDER.APPROVED":
                if current_status in ("CREATED", "INITIATED"):
                    lifecycle_engine.transition_status(payment, "APPROVED")
            elif event_type in ("PAYMENT.CAPTURE.REFUNDED", "PAYMENT.REFUND.COMPLETED"):
                lifecycle_engine.transition_status(payment, "REFUNDED")

        db.commit()

        if payment:
            return "PROCESSED", f"Webhook {event_id} processed and correlated to payment {payment.id}", payment.id
        return "UNMATCHED", f"Webhook {event_id} stored for reconciliation (no correlated payment yet)", None

webhook_processor = WebhookProcessor()

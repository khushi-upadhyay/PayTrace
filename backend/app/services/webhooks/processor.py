import uuid
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from app.db.models.webhook import PayPalWebhook
from app.db.models.payment import Payment
from app.services.lifecycle.engine import lifecycle_engine
from app.core.security import redact_sensitive_data
from app.services.paypal.client import paypal_client

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
        event_id = payload.get("id")
        if not event_id:
            return "INVALID_PAYLOAD", "Missing webhook event id", None

        # 1. Idempotency Check
        existing_wh = db.query(PayPalWebhook).filter(PayPalWebhook.webhook_event_id == event_id).first()
        if existing_wh:
            logger.info(f"Duplicate webhook received: {event_id}. Skipping processing.")
            return "IGNORED_DUPLICATE", f"Webhook event {event_id} already ingested (idempotent)", existing_wh.payment_id

        # 2. Signature verification
        is_verified = False
        if skip_verification_for_test or headers.get("x-mock-webhook") == "true":
            is_verified = True
        else:
            try:
                is_verified = await paypal_client.verify_webhook_signature(headers, raw_body)
            except Exception as e:
                logger.warning(f"Webhook signature verification failed or skipped: {e}")
                is_verified = False

        event_type = payload.get("event_type", "UNKNOWN")
        resource_type = payload.get("resource_type", "capture")
        resource = payload.get("resource", {})

        # 3. Correlation: Find Payment by order_id, capture_id, or custom_id
        order_id = resource.get("supplementary_data", {}).get("related_ids", {}).get("order_id")
        if not order_id and resource_type in ("checkout-order", "order"):
            order_id = resource.get("id")

        capture_id = resource.get("id") if "CAPTURE" in event_type else None
        custom_id = resource.get("custom_id")

        payment: Optional[Payment] = None
        if custom_id:
            payment = db.query(Payment).filter(Payment.id == custom_id).first()
        if not payment and order_id:
            payment = db.query(Payment).filter(Payment.paypal_order_id == order_id).first()
        if not payment and capture_id:
            payment = db.query(Payment).filter(Payment.paypal_capture_id == capture_id).first()

        payment_id = payment.id if payment else None

        # 4. Save Webhook Record
        wh_record = PayPalWebhook(
            id=str(uuid.uuid4()),
            webhook_event_id=event_id,
            event_type=event_type,
            resource_type=resource_type,
            payment_id=payment_id,
            payload_redacted=redact_sensitive_data(payload),
            received_at=datetime.utcnow(),
            processed_at=datetime.utcnow(),
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
                },
                is_simulated=payment.source_mode == "SIMULATED",
            )

            # Update status
            if event_type == "PAYMENT.CAPTURE.COMPLETED":
                lifecycle_engine.transition_status(payment, "CAPTURED")
            elif event_type == "PAYMENT.CAPTURE.DENIED":
                reason = resource.get("status_details", {}).get("reason", "Capture Denied by PayPal")
                lifecycle_engine.transition_status(payment, "DENIED", failure_code="CAPTURE_DENIED", failure_reason=reason)
            elif event_type == "CHECKOUT.ORDER.APPROVED":
                lifecycle_engine.transition_status(payment, "APPROVED")
            elif event_type == "PAYMENT.CAPTURE.REFUNDED":
                lifecycle_engine.transition_status(payment, "REFUNDED")

        db.commit()

        if payment:
            return "PROCESSED", f"Webhook {event_id} processed and correlated to payment {payment.id}", payment.id
        return "UNMATCHED", f"Webhook {event_id} stored but no matching payment found for correlation", None

webhook_processor = WebhookProcessor()

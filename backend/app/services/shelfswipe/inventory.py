"""Idempotent stock decrement for ShelfSwipe orders.

Called from both the capture route and the PayPal webhook processor; whichever runs first
decrements stock and records an INVENTORY_DECREMENTED marker event so the other is a no-op.
"""
from sqlalchemy.orm import Session

from app.db.models.payment import Payment
from app.db.models.payment_event import PaymentEvent
from app.db.models.shelfswipe import ShelfProduct, SSProduct
from app.services.lifecycle.engine import lifecycle_engine

MARKER_EVENT = "INVENTORY_DECREMENTED"


def decrement_stock_once(db: Session, payment: Payment) -> bool:
    """Decrement stock for every line of the payment's checkout order. Returns True if it ran."""
    already = (
        db.query(PaymentEvent.id)
        .filter(PaymentEvent.payment_id == payment.id, PaymentEvent.event_type == MARKER_EVENT)
        .first()
    )
    if already:
        return False

    created = (
        db.query(PaymentEvent)
        .filter(PaymentEvent.payment_id == payment.id, PaymentEvent.event_type == "CHECKOUT_ORDER_CREATED")
        .first()
    )
    metadata = (created.metadata_redacted or {}) if created else {}
    lines = metadata.get("items") or (
        [{"name": metadata["product_name"], "quantity": metadata.get("quantity", 1)}]
        if metadata.get("product_name")
        else []
    )
    if not lines:
        return False

    for line in lines:
        qty = int(line.get("quantity", 1))
        product = None
        if line.get("id"):
            model = SSProduct if line.get("source") == "ss" else ShelfProduct
            product = db.query(model).filter(model.id == line["id"]).first()
        elif line.get("name"):
            product = db.query(ShelfProduct).filter(ShelfProduct.name == line["name"]).first()
        if product and product.stock > 0:
            product.stock = max(0, product.stock - qty)

    lifecycle_engine.record_event(
        db, payment, MARKER_EVENT, "SHELFSWIPE_APP", "SUCCESS", metadata={"lines": len(lines)}
    )
    return True

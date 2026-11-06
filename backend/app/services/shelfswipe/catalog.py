import re
import uuid
import logging
import httpx
from decimal import Decimal
from typing import Iterable, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from app.db.models.shelfswipe import ShelfProduct, SwipeAction, ShelfOrderItem, ShelfCartItem
from app.db.models.payment import Payment
from app.core.config import settings
from app.services.lifecycle.engine import lifecycle_engine
from app.services.paypal.mock_sandbox import mock_paypal
from app.services.paypal.client import (
    paypal_client,
    safe_paypal_error_diagnostics,
    validate_created_order_amount,
)

logger = logging.getLogger(__name__)

STOP_WORDS = {"the", "and", "for", "with", "under", "nearby", "from"}


def query_terms(text: str) -> set:
    return {
        term for term in re.findall(r"[a-z0-9]+", text.lower())
        if len(term) > 2 and term not in STOP_WORDS
    }


def searchable_text(product: ShelfProduct) -> str:
    return " ".join((product.name, product.category, product.description, product.why_matches or "")).lower()


def search_catalog(db: Session, query: str, buyer_ref: Optional[str] = None) -> List[ShelfProduct]:
    """Term-match + liked-category ranking shared by the swipe deck and the shopping assistant."""
    liked_categories = set()
    if buyer_ref:
        liked_swipes = db.query(SwipeAction).filter(
            SwipeAction.buyer_ref == buyer_ref,
            SwipeAction.direction == "right",
        ).all()
        liked_product_ids = [s.product_id for s in liked_swipes]
        if liked_product_ids:
            liked_prods = db.query(ShelfProduct.category).filter(ShelfProduct.id.in_(liked_product_ids)).all()
            liked_categories = {c[0] for c in liked_prods}

    products = db.query(ShelfProduct).filter(ShelfProduct.status == "live", ShelfProduct.stock > 0).all()
    terms = query_terms(query)

    if terms:
        products = [
            p for p in products
            if terms.intersection(re.findall(r"[a-z0-9]+", searchable_text(p)))
        ]

    def rank_score(p: ShelfProduct) -> int:
        score = 0
        if p.category in liked_categories:
            score += 50
        product_terms = set(re.findall(r"[a-z0-9]+", searchable_text(p)))
        score += 30 * len(terms.intersection(product_terms))
        return score

    return sorted(products, key=rank_score, reverse=True)


def get_cart_snapshot(db: Session, buyer_ref: str) -> dict:
    rows = (
        db.query(ShelfCartItem, ShelfProduct)
        .join(ShelfProduct, ShelfCartItem.product_id == ShelfProduct.id)
        .filter(ShelfCartItem.buyer_ref == buyer_ref)
        .all()
    )
    items = [
        {
            "product_id": product.id,
            "name": product.name,
            "price": float(product.price),
            "currency": product.currency,
            "quantity": cart_item.quantity,
            "image_url": product.image_url,
            "line_total": float(product.price) * cart_item.quantity,
        }
        for cart_item, product in rows
    ]
    total = sum(item["line_total"] for item in items)
    return {"buyer_ref": buyer_ref, "items": items, "total": total}


class InsufficientStockError(Exception):
    def __init__(self, product_name: str, available: int, requested: int):
        self.product_name = product_name
        self.available = available
        self.requested = requested
        super().__init__(f"Insufficient stock for {product_name}: requested {requested}, available {available}")


async def create_multi_item_order(
    db: Session,
    buyer_ref: str,
    items: Sequence[Tuple[ShelfProduct, int]],
    session_id: Optional[str] = None,
    simulate_scenario: Optional[str] = None,
) -> dict:
    """Creates one Payment + PayPal order covering one or more ShelfProduct line items."""
    if not items:
        raise ValueError("At least one line item is required to check out")

    for product, quantity in items:
        if product.stock < quantity:
            raise InsufficientStockError(product.name, product.stock, quantity)

    currencies = {p.currency for p, _ in items}
    if len(currencies) > 1:
        raise ValueError("All cart items must share the same currency for a single checkout")
    currency = currencies.pop()

    total_amount = sum(Decimal(str(p.price)) * qty for p, qty in items)
    payment_id = str(uuid.uuid4())
    is_mock = not settings.is_paypal_configured

    paypal_order_id = ""
    approval_url = None

    if settings.is_paypal_configured:
        try:
            order_data = await paypal_client.create_order(
                amount=total_amount,
                currency=currency,
                custom_id=payment_id,
                return_url=f"{settings.FRONTEND_ORIGIN}/shelfswipe?status=approved",
                cancel_url=f"{settings.FRONTEND_ORIGIN}/shelfswipe?status=cancelled",
            )
            if currency != "USD":
                raise ValueError("ShelfSwipe Sandbox checkout requires USD")
            validate_created_order_amount(order_data, total_amount, currency)
            paypal_order_id = order_data["id"]
            for link in order_data.get("links", []):
                if link.get("rel") == "approve":
                    approval_url = link.get("href")
        except Exception as exc:
            diagnostics = (
                safe_paypal_error_diagnostics(exc)
                if isinstance(exc, httpx.HTTPStatusError)
                else {"http_status": None, "error_type": type(exc).__name__}
            )
            diagnostics.update({"requested_amount": f"{total_amount:.2f}", "requested_currency": currency})
            logger.error("ShelfSwipe multi-item PayPal order creation failed", extra={"paypal_diagnostics": diagnostics})
            raise

    if is_mock:
        order_data = mock_paypal.create_order(
            amount=total_amount,
            currency=currency,
            custom_id=payment_id,
        )
        paypal_order_id = order_data["id"]
        approval_url = f"{settings.FRONTEND_ORIGIN}/demo/approval?token={paypal_order_id}&return_to=shelfswipe"

    payment = Payment(
        id=payment_id,
        paypal_order_id=paypal_order_id,
        customer_ref=buyer_ref,
        session_id=session_id,
        amount=total_amount,
        currency=currency,
        status="CREATED",
        actor="human",
        source_mode="SIMULATED" if is_mock else f"PAYPAL_{settings.paypal_mode.upper()}",
        failure_code=simulate_scenario,
    )
    db.add(payment)
    db.flush()

    line_items_meta = []
    for product, quantity in items:
        db.add(ShelfOrderItem(
            id=str(uuid.uuid4()),
            payment_id=payment.id,
            product_id=product.id,
            quantity=quantity,
            unit_price=Decimal(str(product.price)),
            name_snapshot=product.name,
        ))
        line_items_meta.append({"product_id": product.id, "product_name": product.name, "quantity": quantity})

    lifecycle_engine.record_event(
        db=db,
        payment=payment,
        event_type="CHECKOUT_ORDER_CREATED",
        source="SHELVESWIPE_APP",
        status="SUCCESS",
        paypal_order_id=paypal_order_id,
        metadata={"items": line_items_meta, "seller_id": items[0][0].seller_id},
        is_simulated=is_mock,
    )
    db.commit()

    return {
        "payment_id": payment_id,
        "paypal_order_id": paypal_order_id,
        "approval_url": approval_url,
        "amount": float(total_amount),
        "currency": currency,
        "items": line_items_meta,
        "is_mock": is_mock,
    }

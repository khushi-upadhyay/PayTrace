import re
import json
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlalchemy.orm import Session

from app.db.models.shelfswipe import ShelfProduct, ShelfCartItem
from app.core.config import settings
from app.services.shelfswipe.catalog import (
    search_catalog,
    create_multi_item_order,
    get_cart_snapshot,
    InsufficientStockError,
)

logger = logging.getLogger(__name__)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "Search the ShelfSwipe catalog for products matching a free-text description.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_to_cart",
            "description": "Resolve one or more product descriptions to catalog items and add them to the buyer's cart.",
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string", "description": "Product name or description to resolve"},
                                "quantity": {"type": "integer", "default": 1},
                            },
                            "required": ["query"],
                        },
                    }
                },
                "required": ["items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "view_cart",
            "description": "Return the buyer's current cart contents and running total.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_from_cart",
            "description": "Remove a product from the buyer's cart by product name/description.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "checkout_cart",
            "description": "Check out everything currently in the buyer's cart, creating one PayPal order for the total.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def _best_match(db: Session, buyer_ref: str, query: str) -> Optional[ShelfProduct]:
    candidates = search_catalog(db, query, buyer_ref=buyer_ref)
    return candidates[0] if candidates else None


class ShelfCommerceAgent:
    """Conversational shopping assistant over the ShelfSwipe catalog and cart."""

    async def chat(
        self,
        db: Session,
        buyer_ref: str,
        message: str,
        messages: Optional[List[Dict[str, str]]] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        messages = messages or []
        actions_taken: List[str] = []
        checkout_result: Optional[Dict[str, Any]] = None

        if settings.is_ai_configured:
            try:
                reply, actions_taken, checkout_result = await self._run_llm_tool_loop(
                    db, buyer_ref, message, messages, session_id
                )
                cart = get_cart_snapshot(db, buyer_ref)
                return {
                    "response": reply,
                    "cart": cart["items"],
                    "cart_total": cart["total"],
                    "actions_taken": actions_taken,
                    "checkout": checkout_result,
                }
            except Exception as exc:
                logger.warning(f"Shelf agent LLM tool loop failed, falling back to deterministic parser: {exc}")

        reply, actions_taken, checkout_result = await self._deterministic_turn(
            db, buyer_ref, message, session_id
        )
        cart = get_cart_snapshot(db, buyer_ref)
        return {
            "response": reply,
            "cart": cart["items"],
            "cart_total": cart["total"],
            "actions_taken": actions_taken,
            "checkout": checkout_result,
        }

    async def _execute_tool(
        self, db: Session, buyer_ref: str, session_id: Optional[str], name: str, args: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any], Optional[Dict[str, Any]]]:
        """Executes one tool call, returning (action_description, tool_result_payload, checkout_result)."""
        if name == "search_products":
            matches = search_catalog(db, args.get("query", ""), buyer_ref=buyer_ref)[:5]
            payload = {"matches": [{"product_id": p.id, "name": p.name, "price": float(p.price)} for p in matches]}
            return f"Searched catalog for '{args.get('query', '')}'", payload, None

        if name == "add_to_cart":
            added = []
            for item in args.get("items", []):
                product = _best_match(db, buyer_ref, item.get("query", ""))
                if not product:
                    continue
                qty = max(1, min(int(item.get("quantity") or 1), 100))
                existing = (
                    db.query(ShelfCartItem)
                    .filter(ShelfCartItem.buyer_ref == buyer_ref, ShelfCartItem.product_id == product.id)
                    .first()
                )
                if existing:
                    existing.quantity += qty
                else:
                    db.add(ShelfCartItem(id=str(uuid.uuid4()), buyer_ref=buyer_ref, product_id=product.id, quantity=qty))
                added.append(f"{qty}x {product.name}")
            db.commit()
            return f"Added to cart: {', '.join(added) if added else 'no matches found'}", {"added": added}, None

        if name == "view_cart":
            cart = get_cart_snapshot(db, buyer_ref)
            return "Viewed cart", cart, None

        if name == "remove_from_cart":
            product = _best_match(db, buyer_ref, args.get("query", ""))
            removed = False
            if product:
                row = (
                    db.query(ShelfCartItem)
                    .filter(ShelfCartItem.buyer_ref == buyer_ref, ShelfCartItem.product_id == product.id)
                    .first()
                )
                if row:
                    db.delete(row)
                    db.commit()
                    removed = True
            return (
                f"Removed {product.name if product else args.get('query')} from cart" if removed else "Item not found in cart",
                {"removed": removed},
                None,
            )

        if name == "checkout_cart":
            cart_rows = (
                db.query(ShelfCartItem, ShelfProduct)
                .join(ShelfProduct, ShelfCartItem.product_id == ShelfProduct.id)
                .filter(ShelfCartItem.buyer_ref == buyer_ref)
                .all()
            )
            if not cart_rows:
                return "Cart is empty, nothing to check out", {"error": "empty_cart"}, None
            items = [(product, cart_item.quantity) for cart_item, product in cart_rows]
            try:
                result = await create_multi_item_order(db, buyer_ref, items, session_id=session_id)
            except InsufficientStockError as exc:
                return f"Checkout failed: {exc}", {"error": str(exc)}, None
            for cart_item, _ in cart_rows:
                db.delete(cart_item)
            db.commit()
            return "Checked out cart", result, result

        return f"Unknown tool {name}", {"error": "unknown_tool"}, None

    async def _run_llm_tool_loop(
        self,
        db: Session,
        buyer_ref: str,
        message: str,
        prior_messages: List[Dict[str, str]],
        session_id: Optional[str],
    ) -> Tuple[str, List[str], Optional[Dict[str, Any]]]:
        system_prompt = (
            "You are the ShelfSwipe shopping assistant. Buyers may mention multiple products in one message. "
            "Use the provided tools to search the catalog, add items to the cart, view the cart, remove items, "
            "and check out. Always resolve every distinct product the buyer mentions before replying. "
            "Keep replies short and concrete about what was actually done."
        )
        convo: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        convo.extend(prior_messages)
        convo.append({"role": "user", "content": message})

        actions_taken: List[str] = []
        checkout_result: Optional[Dict[str, Any]] = None

        async with httpx.AsyncClient(timeout=20.0) as client:
            for _ in range(4):
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {settings.AI_API_KEY}", "Content-Type": "application/json"},
                    json={
                        "model": settings.AI_MODEL or "gpt-4o-mini",
                        "messages": convo,
                        "tools": TOOLS,
                        "temperature": 0.1,
                    },
                )
                resp.raise_for_status()
                choice = resp.json()["choices"][0]
                msg = choice["message"]
                tool_calls = msg.get("tool_calls")

                if not tool_calls:
                    return msg.get("content") or "Done.", actions_taken, checkout_result

                convo.append({
                    "role": "assistant",
                    "content": msg.get("content"),
                    "tool_calls": tool_calls,
                })
                for call in tool_calls:
                    fn_name = call["function"]["name"]
                    try:
                        fn_args = json.loads(call["function"]["arguments"] or "{}")
                    except json.JSONDecodeError:
                        fn_args = {}
                    description, result_payload, maybe_checkout = await self._execute_tool(
                        db, buyer_ref, session_id, fn_name, fn_args
                    )
                    actions_taken.append(description)
                    if maybe_checkout:
                        checkout_result = maybe_checkout
                    convo.append({
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": json.dumps(result_payload),
                    })

        return "I've updated your cart based on your request.", actions_taken, checkout_result

    async def _deterministic_turn(
        self, db: Session, buyer_ref: str, message: str, session_id: Optional[str]
    ) -> Tuple[str, List[str], Optional[Dict[str, Any]]]:
        """Regex/keyword-driven fallback that still resolves multiple products in one prompt without an LLM."""
        lower = message.lower()
        actions_taken: List[str] = []

        if any(kw in lower for kw in ("checkout", "buy it", "buy now", "place order", "complete order", "pay now")):
            description, _, checkout_result = await self._execute_tool(db, buyer_ref, session_id, "checkout_cart", {})
            actions_taken.append(description)
            if checkout_result and checkout_result.get("error"):
                return description, actions_taken, None
            return description, actions_taken, checkout_result

        if "cart" in lower and any(kw in lower for kw in ("view", "show", "what", "check")):
            description, cart, _ = await self._execute_tool(db, buyer_ref, session_id, "view_cart", {})
            actions_taken.append(description)
            if not cart["items"]:
                return "Your cart is empty.", actions_taken, None
            lines = ", ".join(f"{i['quantity']}x {i['name']}" for i in cart["items"])
            return f"Your cart has: {lines} (total ${cart['total']:.2f}).", actions_taken, None

        if any(kw in lower for kw in ("remove", "delete", "drop")):
            segment = re.sub(r"\b(remove|delete|drop|from|my|cart|the)\b", " ", lower).strip()
            description, _, _ = await self._execute_tool(db, buyer_ref, session_id, "remove_from_cart", {"query": segment})
            actions_taken.append(description)
            return description, actions_taken, None

        # Default: treat the message as one or more product mentions to add to the cart.
        segments = re.split(r"\band\b|,|\+", message)
        add_items = []
        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue
            qty_match = re.match(r"^(\d+)\s*x?\s+(.*)$", segment, re.IGNORECASE)
            if qty_match:
                qty, text = int(qty_match.group(1)), qty_match.group(2)
            else:
                qty, text = 1, segment
            if search_catalog(db, text, buyer_ref=buyer_ref):
                add_items.append({"query": text, "quantity": qty})

        if not add_items:
            return (
                "I couldn't match any ShelfSwipe products in that message. Try naming an item, "
                "or say 'view cart' / 'checkout'.",
                actions_taken,
                None,
            )

        description, _, _ = await self._execute_tool(db, buyer_ref, session_id, "add_to_cart", {"items": add_items})
        actions_taken.append(description)
        return description, actions_taken, None


shelf_agent = ShelfCommerceAgent()

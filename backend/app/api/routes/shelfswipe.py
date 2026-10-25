import uuid
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.api.dependencies import get_db
from app.db.models.shelfswipe import Seller, ShelfProduct, SwipeAction
from app.db.models.payment import Payment
from app.schemas.shelfswipe import (
    SellerOnboardRequest,
    ShelfProductSchema,
    ShelfProductDeckResponse,
    SwipeRecordRequest,
    ShelfSwipeCheckoutRequest,
)
from app.services.lifecycle.engine import lifecycle_engine
from app.services.paypal.mock_sandbox import mock_paypal
from app.services.paypal.client import paypal_client
from app.core.config import settings

router = APIRouter(prefix="/shelfswipe", tags=["ShelfSwipe"])

# Curated seed catalog for instant onboarding demo
DEMO_CATALOG = [
    {
        "name": "Handmade Organic Lavender Candle",
        "price": 24.50,
        "category": "Home & Aromatics",
        "description": "Soy wax infused with organic French lavender, hand-poured in small batches.",
        "image_url": "https://images.unsplash.com/photo-1603006905003-be475563bc59?auto=format&fit=crop&w=600&q=80",
        "stock": 15,
        "why_matches": "Relaxing birthday gift option within budget from a local home studio."
    },
    {
        "name": "Artisanal Ceramic Matcha Bowl",
        "price": 38.00,
        "category": "Pottery & Kitchen",
        "description": "Hand-thrown speckled stoneware with authentic chawan whisking contour.",
        "image_url": "https://images.unsplash.com/photo-1578749556568-bc2c40e68b61?auto=format&fit=crop&w=600&q=80",
        "stock": 8,
        "why_matches": "Unique handcrafted kitchen gift matching high-quality local craftsmanship."
    },
    {
        "name": "Raw Wildflower Honey & Dipper Set",
        "price": 19.99,
        "category": "Gourmet Pantry",
        "description": "Locally harvested unfiltered raw wildflower honey with olive wood dipper.",
        "image_url": "https://images.unsplash.com/photo-1587049352846-4a222e784d38?auto=format&fit=crop&w=600&q=80",
        "stock": 22,
        "why_matches": "Best-seller gourmet gift item under $25 from local beekeepers."
    },
    {
        "name": "Hand-stitched Leather Journal",
        "price": 45.00,
        "category": "Stationery & Leather",
        "description": "Full-grain veg-tanned leather wrapped notebook with deckle-edge recycled paper.",
        "image_url": "https://images.unsplash.com/photo-1544716278-ca5e3f4abd8c?auto=format&fit=crop&w=600&q=80",
        "stock": 5,
        "why_matches": "Premium keepsake gift tailored for creative writers and travelers."
    },
    {
        "name": "Botanical Cold-Process Soap Bar Trio",
        "price": 16.50,
        "category": "Bath & Body",
        "description": "Eucalyptus, cedarwood, and rosehip oils formulated for gentle everyday lather.",
        "image_url": "https://images.unsplash.com/photo-1607006314352-d98c253d537f?auto=format&fit=crop&w=600&q=80",
        "stock": 18,
        "why_matches": "Eco-friendly, budget-friendly self-care gift box."
    }
]

@router.post("/onboard")
def onboard_seller(req: SellerOnboardRequest, db: Session = Depends(get_db)):
    """Simulates AI website extraction of a local shop's product shelf with consent."""
    seller = db.query(Seller).filter(Seller.source_url == req.shop_url).first()
    if not seller:
        seller = Seller(
            id=str(uuid.uuid4()),
            name=req.shop_name,
            contact_email="owner@artisan-local.dev",
            source_url=req.shop_url,
        )
        db.add(seller)
        db.flush()

        for item in DEMO_CATALOG:
            prod = ShelfProduct(
                id=str(uuid.uuid4()),
                seller_id=seller.id,
                name=item["name"],
                price=Decimal(str(item["price"])),
                currency="USD",
                image_url=item["image_url"],
                description=item["description"],
                category=item["category"],
                stock=item["stock"],
                status="live",
                source="scraped",
                why_matches=item["why_matches"],
            )
            db.add(prod)
        db.commit()

    products = db.query(ShelfProduct).filter(ShelfProduct.seller_id == seller.id).all()
    return {
        "status": "extracted",
        "seller_id": seller.id,
        "seller_name": seller.name,
        "products_count": len(products),
        "products": [
            {
                "id": p.id,
                "name": p.name,
                "price": float(p.price),
                "category": p.category,
                "stock": p.stock,
                "image_url": p.image_url,
                "why_matches": p.why_matches,
            }
            for p in products
        ]
    }

@router.get("/deck", response_model=ShelfProductDeckResponse)
def get_swipe_deck(
    query: str = Query("gift", description="Natural language buyer search query"),
    buyer_ref: str = Query("buyer_demo_01"),
    db: Session = Depends(get_db)
):
    """
    Returns AI-ranked swipe deck.
    Swiping right on categories pushes similar items to the top (Learning Loop).
    """
    # Check if any products exist, if not, auto-seed
    count = db.query(ShelfProduct).count()
    if count == 0:
        onboard_seller(SellerOnboardRequest(shop_url="https://artisan-local.demo", shop_name="Artisan Local Co."), db)

    # Fetch buyer's swipe history to adapt deck ranking
    liked_swipes = db.query(SwipeAction).filter(
        SwipeAction.buyer_ref == buyer_ref,
        SwipeAction.direction == "right"
    ).all()
    liked_product_ids = [s.product_id for s in liked_swipes]

    # Find liked categories
    liked_categories = set()
    if liked_product_ids:
        liked_prods = db.query(ShelfProduct.category).filter(ShelfProduct.id.in_(liked_product_ids)).all()
        liked_categories = {c[0] for c in liked_prods}

    products = db.query(ShelfProduct).filter(ShelfProduct.status == "live", ShelfProduct.stock > 0).all()

    # Dynamic Ranking: Boost items in liked categories or matching query keywords
    def rank_score(p: ShelfProduct):
        score = 0
        if p.category in liked_categories:
            score += 50 # Boost based on prior swipe learning
        q = query.lower()
        if q in p.name.lower() or q in p.category.lower() or q in p.description.lower():
            score += 30
        return score

    ranked = sorted(products, key=rank_score, reverse=True)

    deck_items = [
        ShelfProductSchema(
            id=p.id,
            seller_id=p.seller_id,
            name=p.name,
            price=float(p.price),
            currency=p.currency,
            image_url=p.image_url,
            description=p.description,
            category=p.category,
            stock=p.stock,
            status=p.status,
            why_matches=f"AI Pick: {p.why_matches} (Learned preference match)" if p.category in liked_categories else p.why_matches,
        )
        for p in ranked
    ]

    refinements = []
    if liked_categories:
        refinements.append(f"Ranking adapted to your interest in {', '.join(liked_categories)}")

    return ShelfProductDeckResponse(
        deck=deck_items,
        total_matches=len(deck_items),
        query=query,
        refinements_applied=refinements,
    )

@router.post("/swipe")
def record_swipe(req: SwipeRecordRequest, db: Session = Depends(get_db)):
    """Records a swipe (right=like, left=pass) to iteratively teach the AI preference vector."""
    swipe = SwipeAction(
        id=str(uuid.uuid4()),
        buyer_ref=req.buyer_ref,
        product_id=req.product_id,
        direction=req.direction,
    )
    db.add(swipe)
    db.commit()
    return {"status": "recorded", "direction": req.direction, "product_id": req.product_id}

@router.post("/checkout")
async def checkout_shelf_item(req: ShelfSwipeCheckoutRequest, db: Session = Depends(get_db)):
    """
    Seamless PayPal Checkout for ShelfSwipe items, wired with PayTrace's lifecycle and recovery engine.
    """
    prod = db.query(ShelfProduct).filter(ShelfProduct.id == req.product_id).first()
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")
    if prod.stock < req.quantity:
        raise HTTPException(status_code=400, detail="Insufficient stock")

    payment_id = str(uuid.uuid4())
    total_amount = Decimal(str(prod.price)) * req.quantity
    is_mock = not settings.is_paypal_configured

    paypal_order_id = ""
    approval_url = None

    if settings.is_paypal_configured:
        try:
            order_data = await paypal_client.create_order(
                amount=total_amount,
                currency=prod.currency,
                custom_id=payment_id,
            )
            paypal_order_id = order_data["id"]
            for link in order_data.get("links", []):
                if link.get("rel") == "approve":
                    approval_url = link.get("href")
        except Exception:
            is_mock = True

    if is_mock:
        order_data = mock_paypal.create_order(
            amount=total_amount,
            currency=prod.currency,
            custom_id=payment_id,
        )
        paypal_order_id = order_data["id"]
        approval_url = order_data["links"][0]["href"]

    # Register in PayTrace unified payment ledger
    payment = Payment(
        id=payment_id,
        paypal_order_id=paypal_order_id,
        customer_ref=req.buyer_ref,
        amount=total_amount,
        currency=prod.currency,
        status="CREATED",
        actor="human",
        source_mode="SIMULATED" if is_mock else "PAYPAL_SANDBOX",
        failure_code=req.simulate_scenario,
    )
    db.add(payment)

    lifecycle_engine.record_event(
        db=db,
        payment=payment,
        event_type="CHECKOUT_ORDER_CREATED",
        source="SHELVESWIPE_APP",
        status="SUCCESS",
        paypal_order_id=paypal_order_id,
        metadata={"product_name": prod.name, "quantity": req.quantity, "seller_id": prod.seller_id},
        is_simulated=is_mock,
    )
    db.commit()

    return {
        "payment_id": payment_id,
        "paypal_order_id": paypal_order_id,
        "approval_url": approval_url,
        "amount": float(total_amount),
        "currency": prod.currency,
        "product_name": prod.name,
    }

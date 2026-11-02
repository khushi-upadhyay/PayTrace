import uuid
import logging
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.db.models.user import User
from app.db.models.shelfswipe import Seller, ShelfProduct, SwipeAction, ShelfCartItem
from app.schemas.shelfswipe import (
    SellerOnboardRequest,
    ShelfProductSchema,
    ShelfProductDeckResponse,
    SwipeRecordRequest,
    ShelfSwipeCheckoutRequest,
    ShelfCartItemSchema,
    ShelfCartResponse,
    ShelfChatRequest,
    ShelfChatResponse,
    ShelfCheckoutResult,
    ShelfCartCheckoutRequest,
)
from app.services.shelfswipe.catalog import (
    search_catalog,
    create_multi_item_order,
    get_cart_snapshot,
    InsufficientStockError,
)
from app.agents.shelf_agent import shelf_agent
from app.core.config import settings

router = APIRouter(prefix="/shelfswipe", tags=["ShelfSwipe"])
logger = logging.getLogger(__name__)

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

DEMO_SELLER_ID = "00000000-0000-4000-8000-000000000001"
DEMO_SELLER_URL = "paytrace://demo-catalog"


def seed_demo_catalog(db: Session) -> None:
    """Seed the explicitly labelled, local demo catalog without external services."""
    seller = db.query(Seller).filter(Seller.source_url == DEMO_SELLER_URL).first()
    if not seller:
        seller = Seller(
            id=DEMO_SELLER_ID,
            name="PayTrace Demo Catalog",
            contact_email="demo@example.invalid",
            source_url=DEMO_SELLER_URL,
        )
        db.add(seller)
        db.flush()

    for item in DEMO_CATALOG:
        product_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"paytrace-demo:{item['name']}"))
        exists = db.query(ShelfProduct).filter(ShelfProduct.id == product_id).first()
        if not exists:
            db.add(ShelfProduct(
                id=product_id,
                seller_id=seller.id,
                name=item["name"],
                price=Decimal(str(item["price"])),
                currency="USD",
                image_url=item["image_url"],
                description=item["description"],
                category=item["category"],
                stock=item["stock"],
                status="live",
                source="demo",
                why_matches=item["why_matches"],
            ))
    db.commit()

@router.post("/onboard")
def onboard_seller(req: SellerOnboardRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Loads the curated demo catalog without accessing an external merchant site."""
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
                source="demo",
                why_matches=item["why_matches"],
            )
            db.add(prod)
        db.commit()

    products = db.query(ShelfProduct).filter(ShelfProduct.seller_id == seller.id).all()
    return {
        "status": "demo_loaded",
        "is_demo": True,
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
    db: Session = Depends(get_db),
):
    """
    Returns a deterministic, search-filtered demo deck.
    Swiping right on categories pushes similar items to the top.
    """
    # Check if any products exist, if not, auto-seed
    count = db.query(ShelfProduct).count()
    if count == 0:
        seed_demo_catalog(db)

    # Fetch buyer's liked categories (via shared catalog ranking) to annotate the deck
    liked_swipes = db.query(SwipeAction).filter(
        SwipeAction.buyer_ref == buyer_ref,
        SwipeAction.direction == "right"
    ).all()
    liked_product_ids = [s.product_id for s in liked_swipes]
    liked_categories = set()
    if liked_product_ids:
        liked_prods = db.query(ShelfProduct.category).filter(ShelfProduct.id.in_(liked_product_ids)).all()
        liked_categories = {c[0] for c in liked_prods}

    ranked = search_catalog(db, query, buyer_ref=buyer_ref)

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
            source=p.source,
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
    Seamless PayPal Checkout for a single ShelfSwipe item, wired with PayTrace's lifecycle and recovery engine.
    """
    prod = db.query(ShelfProduct).filter(ShelfProduct.id == req.product_id).first()
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")

    try:
        result = await create_multi_item_order(
            db,
            buyer_ref=req.buyer_ref,
            items=[(prod, req.quantity)],
            session_id=req.session_id,
            simulate_scenario=req.simulate_scenario,
        )
    except InsufficientStockError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("ShelfSwipe single-item checkout failed", extra={"error": str(exc)})
        raise HTTPException(status_code=502, detail="Failed to create PayPal Sandbox order") from exc

    return {**result, "product_name": prod.name}


@router.get("/cart", response_model=ShelfCartResponse)
def get_cart(buyer_ref: str = Query(...), db: Session = Depends(get_db)):
    """Returns the buyer's current in-progress cart, built up via the shopping assistant."""
    return ShelfCartResponse(**get_cart_snapshot(db, buyer_ref))


@router.post("/chat", response_model=ShelfChatResponse)
async def shelf_chat(req: ShelfChatRequest, db: Session = Depends(get_db)):
    """
    Conversational shopping assistant: one prompt can name multiple products,
    which the agent resolves, adds to the cart, and can check out on request.
    """
    count = db.query(ShelfProduct).count()
    if count == 0:
        seed_demo_catalog(db)

    result = await shelf_agent.chat(
        db=db,
        buyer_ref=req.buyer_ref,
        message=req.message,
        messages=[m.model_dump() for m in req.messages],
        session_id=req.session_id,
    )
    checkout = ShelfCheckoutResult(**result["checkout"]) if result.get("checkout") else None
    return ShelfChatResponse(
        response=result["response"],
        cart=result["cart"],
        cart_total=result["cart_total"],
        actions_taken=result["actions_taken"],
        checkout=checkout,
    )


@router.post("/checkout/cart")
async def checkout_cart(req: ShelfCartCheckoutRequest, db: Session = Depends(get_db)):
    """Checks out everything currently in the buyer's cart as a single multi-item PayPal order."""
    cart_rows = (
        db.query(ShelfCartItem, ShelfProduct)
        .join(ShelfProduct, ShelfCartItem.product_id == ShelfProduct.id)
        .filter(ShelfCartItem.buyer_ref == req.buyer_ref)
        .all()
    )
    if not cart_rows:
        raise HTTPException(status_code=400, detail="Cart is empty")

    items = [(product, cart_item.quantity) for cart_item, product in cart_rows]
    try:
        result = await create_multi_item_order(
            db,
            buyer_ref=req.buyer_ref,
            items=items,
            session_id=req.session_id,
            simulate_scenario=req.simulate_scenario,
        )
    except InsufficientStockError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("ShelfSwipe cart checkout failed", extra={"error": str(exc)})
        raise HTTPException(status_code=502, detail="Failed to create PayPal Sandbox order") from exc

    for cart_item, _ in cart_rows:
        db.delete(cart_item)
    db.commit()

    return result

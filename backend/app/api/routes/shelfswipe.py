import logging
import re
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy.orm import Session
import httpx
from app.api.dependencies import get_db
from app.core.config import settings
from app.core.security import create_checkout_token
from app.db.models.payment import Payment
from app.db.models.shelfswipe import (
    SSSeller,
    SSShop,
    SSProduct,
    SSBuyerProfile,
    SSSwipe,
    Seller,
    ShelfProduct,
    SwipeAction,
)
from app.schemas.shelfswipe import (
    ShelfSwipeOnboardRequest,
    ShelfSwipeOnboardResponse,
    ShelfSwipeDraftResponse,
    ShelfSwipeDraftProductItem,
    ShelfProductSchema,
    ShelfProductDeckResponse,
    SwipeRecordRequest,
    ShelfSwipeCheckoutRequest,
    ProductPatchRequest,
    ProductCreateRequest,
    ShopPatchRequest,
    ApproveRequest,
    ApproveResponse,
    ApproveRejectedItem,
    ShelfSwipeSellerSummary,
    ShelfSwipeSellerListResponse,
    ShelfSwipeProductWithShop,
    ShelfSwipeAllProductsResponse,
    BuyerDeckProductItem,
    BuyerDeckResponse,
    BuyerSwipeRequest,
    BuyerSwipeResponse,
)
from app.services.lifecycle.engine import lifecycle_engine
from app.services.paypal.client import (
    paypal_client,
    safe_paypal_error_diagnostics,
    validate_created_order_amount,
)
from app.services.paypal.mock_sandbox import mock_paypal
from app.services.shelfswipe import mcp_client
from app.services.shelfswipe.importer import (
    import_shop,
    ConsentRequiredError,
    recompute_ss_product_review_flags,
)
from app.services.shelfswipe.fixture_provider import FixtureCatalogProvider
from app.services.shelfswipe.channel3_provider import (
    Channel3CatalogProvider,
    Channel3NoProductsError,
)
from app.services.shelfswipe.channel3_client import (
    Channel3ClientError,
    Channel3RateLimitError,
    Channel3TimeoutError,
)
from app.services.shelfswipe.mcp_client import McpClientError

router = APIRouter(prefix="/shelfswipe", tags=["shelfswipe"])
logger = logging.getLogger("paytrace.shelfswipe")


# =========================================================
# Day 1 ShelfSwipe Feature Endpoints
# =========================================================

@router.get("/demo-shops", response_model=List[Dict[str, Any]])
def get_demo_shops():
    """
    Returns available fixture demo shops from the ShelfSwipe MCP server.
    """
    try:
        return mcp_client.list_shops()
    except McpClientError as exc:
        logger.error(f"Failed to fetch demo shops from MCP server: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"ShelfSwipe MCP client error: {str(exc)}",
        )


@router.post(
    "/sellers/onboard",
    response_model=ShelfSwipeOnboardResponse,
    status_code=status.HTTP_201_CREATED,
)
def onboard_seller(
    req: ShelfSwipeOnboardRequest,
    db: Session = Depends(get_db),
):
    """
    Onboards a merchant shop via MCP catalog extraction or Channel3 lookup.
    Creates or updates seller, shop, extraction job, and imports products as drafts.
    """
    provider_name = (req.provider or "fixture").strip().lower()

    if provider_name == "channel3":
        if not req.ownership_attested:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Seller ownership attestation is required for Channel3 onboarding.",
            )
        if not (req.shop_url.startswith("http://") or req.shop_url.startswith("https://")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="shop_url must be a valid http or https URL for Channel3 onboarding.",
            )
        if req.product_urls and len(req.product_urls) > 20:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Maximum 20 product URLs allowed per onboarding request.",
            )
        provider = Channel3CatalogProvider()
    elif provider_name == "fixture":
        provider = FixtureCatalogProvider()
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported catalog provider: '{req.provider}'. Allowed: 'fixture', 'channel3'.",
        )

    try:
        result = import_shop(
            db=db,
            shop_url=req.shop_url,
            consent=req.consent,
            seller_name=req.seller_name,
            provider=provider,
            product_urls=req.product_urls,
        )
        return ShelfSwipeOnboardResponse(
            seller_id=str(result.seller_id),
            shop_id=str(result.shop_id),
            job_id=str(result.job_id),
            products_created=result.products_created,
            products_skipped=result.products_skipped,
        )
    except ConsentRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Channel3NoProductsError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except Channel3RateLimitError as exc:
        logger.error(f"Channel3 rate limit error during onboard: {exc}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Channel3 rate limit exceeded: {str(exc)}",
        )
    except Channel3ClientError as exc:
        logger.error(f"Channel3 client error during onboard: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Channel3 client error: {str(exc)}",
        )
    except McpClientError as exc:
        logger.error(f"MCP client error during onboard: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"MCP client error: {str(exc)}",
        )
    except ValidationError as exc:
        logger.error(f"Schema validation error during onboard: {exc}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Catalog schema validation error: {str(exc)}",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Unexpected error during onboarding: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Onboarding error: {str(exc)}",
        )


@router.get(
    "/sellers/{seller_id}/draft",
    response_model=ShelfSwipeDraftResponse,
)
def get_seller_draft(
    seller_id: str,
    status_filter: Optional[str] = Query(default="draft", alias="status", pattern="^(draft|live|all)$"),
    db: Session = Depends(get_db),
):
    """
    Returns the seller's shop plus its products filtered by status:
    - 'draft': products currently in draft (default)
    - 'live': products approved and live
    - 'all': all products for this seller
    """
    seller = db.query(SSSeller).filter(SSSeller.id == seller_id).first()
    if not seller:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Seller with ID '{seller_id}' not found.",
        )

    shop = db.query(SSShop).filter(SSShop.seller_id == seller.id).first()
    if not shop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No shop associated with seller '{seller_id}'.",
        )

    query = db.query(SSProduct).filter(SSProduct.shop_id == shop.id)
    if status_filter == "draft":
        query = query.filter(SSProduct.status == "draft")
    elif status_filter == "live":
        query = query.filter(SSProduct.status == "live")
    elif status_filter == "all":
        pass

    selected_products = query.order_by(SSProduct.created_at.asc()).all()

    product_items = [
        ShelfSwipeDraftProductItem(
            id=str(p.id),
            external_id=p.external_id,
            name=p.name,
            price=float(p.price),
            currency=p.currency,
            image_url=p.image_url,
            description=p.description,
            category=p.category,
            tags=p.tags or [],
            stock=p.stock,
            status=p.status,
            data_source=p.source,
            source_url=p.source_url,
            provider_ref=p.provider_ref,
            review_flags=p.review_flags or [],
        )
        for p in selected_products
    ]

    return ShelfSwipeDraftResponse(
        seller_id=str(seller.id),
        shop_id=str(shop.id),
        name=shop.name,
        description=shop.description,
        latitude=shop.latitude,
        longitude=shop.longitude,
        pickup_notes=shop.pickup_notes,
        is_demo=shop.is_demo,
        products=product_items,
    )


@router.post(
    "/sellers/{seller_id}/products",
    response_model=ShelfSwipeDraftProductItem,
    status_code=status.HTTP_201_CREATED,
)
def create_manual_product(
    seller_id: str,
    req: ProductCreateRequest,
    db: Session = Depends(get_db),
):
    """
    Creates a new draft product manually for a specific seller.
    Ownership is verified via the seller and their associated shop.
    Assigns source='manual', a guaranteed unique 'manual-<uuid>' external_id,
    and computes quality review flags like imports (including confirm_stock).
    """
    seller = db.query(SSSeller).filter(SSSeller.id == seller_id).first()
    if not seller:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Seller with ID '{seller_id}' not found.",
        )

    shop = db.query(SSShop).filter(SSShop.seller_id == seller.id).first()
    if not shop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No shop found for seller '{seller_id}'.",
        )

    flags: List[str] = []
    if not req.image_url or not str(req.image_url).strip():
        flags.append("missing_image")
    if not req.description or not str(req.description).strip():
        flags.append("missing_description")
    if not req.tags or len(req.tags) == 0:
        flags.append("no_tags")
    if req.price <= Decimal("0.00"):
        flags.append("invalid_price")
    flags.append("confirm_stock")

    unique_ext_id = f"manual-{uuid.uuid4()}"

    product = SSProduct(
        shop_id=shop.id,
        external_id=unique_ext_id,
        name=req.name,
        price=req.price,
        currency="USD",
        image_url=req.image_url,
        description=req.description or "",
        category=req.category or "General",
        tags=req.tags or [],
        stock=req.stock,
        status="draft",
        source="manual",
        source_url=None,
        provider_ref=None,
        review_flags=flags,
    )
    db.add(product)
    db.commit()
    db.refresh(product)

    return ShelfSwipeDraftProductItem(
        id=str(product.id),
        external_id=product.external_id,
        name=product.name,
        price=float(product.price),
        currency=product.currency,
        image_url=product.image_url,
        description=product.description,
        category=product.category,
        tags=product.tags or [],
        stock=product.stock,
        status=product.status,
        data_source=product.source,
        source_url=product.source_url,
        provider_ref=product.provider_ref,
        review_flags=product.review_flags or [],
    )


@router.patch(
    "/sellers/{seller_id}/products/{product_id}",
    response_model=ShelfSwipeDraftProductItem,
)
def patch_seller_product(
    seller_id: str,
    product_id: str,
    req: ProductPatchRequest,
    db: Session = Depends(get_db),
):
    """
    Edits a draft product for a specific seller.
    Recomputes quality review flags and validates numeric ranges.
    """
    seller = db.query(SSSeller).filter(SSSeller.id == seller_id).first()
    if not seller:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Seller with ID '{seller_id}' not found.",
        )

    shop = db.query(SSShop).filter(SSShop.seller_id == seller.id).first()
    if not shop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No shop found for seller '{seller_id}'.",
        )

    product = (
        db.query(SSProduct)
        .filter(SSProduct.id == product_id, SSProduct.shop_id == shop.id)
        .first()
    )
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID '{product_id}' not found for seller '{seller_id}'.",
        )

    updates = req.model_dump(exclude_unset=True)
    if "name" in updates and updates["name"] is not None:
        product.name = updates["name"]
    if "price" in updates and updates["price"] is not None:
        product.price = updates["price"]
    if "description" in updates and updates["description"] is not None:
        product.description = updates["description"]
    if "category" in updates and updates["category"] is not None:
        product.category = updates["category"]
    if "tags" in updates and updates["tags"] is not None:
        product.tags = updates["tags"]
    if "image_url" in updates:
        product.image_url = updates["image_url"]
    if "stock" in updates and updates["stock"] is not None:
        product.stock = updates["stock"]

    # Recompute review flags based on updated fields
    product.review_flags = recompute_ss_product_review_flags(product)

    db.commit()
    db.refresh(product)

    return ShelfSwipeDraftProductItem(
        id=str(product.id),
        external_id=product.external_id,
        name=product.name,
        price=float(product.price),
        currency=product.currency,
        image_url=product.image_url,
        description=product.description,
        category=product.category,
        tags=product.tags or [],
        stock=product.stock,
        status=product.status,
        data_source=product.source,
        source_url=product.source_url,
        provider_ref=product.provider_ref,
        review_flags=product.review_flags or [],
    )


@router.patch(
    "/sellers/{seller_id}/shop",
    response_model=ShelfSwipeDraftResponse,
)
def patch_seller_shop(
    seller_id: str,
    req: ShopPatchRequest,
    db: Session = Depends(get_db),
):
    """
    Edits shop configuration (pickup location, notes) for a seller.
    """
    seller = db.query(SSSeller).filter(SSSeller.id == seller_id).first()
    if not seller:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Seller with ID '{seller_id}' not found.",
        )

    shop = db.query(SSShop).filter(SSShop.seller_id == seller.id).first()
    if not shop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No shop found for seller '{seller_id}'.",
        )

    updates = req.model_dump(exclude_unset=True)
    if "pickup_notes" in updates:
        shop.pickup_notes = updates["pickup_notes"]
    if "latitude" in updates:
        shop.latitude = updates["latitude"]
    if "longitude" in updates:
        shop.longitude = updates["longitude"]

    db.commit()
    db.refresh(shop)

    return get_seller_draft(seller_id=seller_id, db=db)


@router.post(
    "/sellers/{seller_id}/approve",
    response_model=ApproveResponse,
)
def approve_seller_draft_products(
    seller_id: str,
    req: ApproveRequest,
    db: Session = Depends(get_db),
):
    """
    Batch approves draft products to live status after confirming stock.
    Rejects products with critical review flags (e.g. invalid_price) or already live products.
    """
    seller = db.query(SSSeller).filter(SSSeller.id == seller_id).first()
    if not seller:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Seller with ID '{seller_id}' not found.",
        )

    shop = db.query(SSShop).filter(SSShop.seller_id == seller.id).first()
    if not shop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No shop found for seller '{seller_id}'.",
        )

    approved: List[str] = []
    rejected: List[ApproveRejectedItem] = []

    for item in req.items:
        prod = (
            db.query(SSProduct)
            .filter(SSProduct.id == item.product_id, SSProduct.shop_id == shop.id)
            .first()
        )
        if not prod:
            rejected.append(ApproveRejectedItem(id=item.product_id, reason="not_found"))
            continue

        if prod.status == "live":
            rejected.append(ApproveRejectedItem(id=item.product_id, reason="already_live"))
            continue

        flags = list(prod.review_flags or [])
        if "invalid_price" in flags:
            rejected.append(ApproveRejectedItem(id=item.product_id, reason="invalid_price"))
            continue

        # Approve product
        prod.stock = item.confirmed_stock
        prod.status = "live"
        # Remove confirm_stock and stock_unknown flags
        prod.review_flags = [f for f in flags if f not in ("confirm_stock", "stock_unknown")]
        approved.append(str(prod.id))

    db.commit()

    still_draft_count = (
        db.query(SSProduct)
        .filter(SSProduct.shop_id == shop.id, SSProduct.status == "draft")
        .count()
    )

    return ApproveResponse(
        approved=approved,
        rejected=rejected,
        still_draft_count=still_draft_count,
    )


# =========================================================
# Onboarding History / Cross-Shop Views
# =========================================================

@router.get("/sellers", response_model=ShelfSwipeSellerListResponse)
def list_sellers(db: Session = Depends(get_db)):
    """
    Returns every onboarded seller/shop so far (the 'history' of store URLs
    that have been imported), each with its draft/live product counts.
    """
    rows = (
        db.query(SSSeller, SSShop)
        .join(SSShop, SSShop.seller_id == SSSeller.id)
        .order_by(SSSeller.created_at.desc())
        .all()
    )

    summaries: List[ShelfSwipeSellerSummary] = []
    total_live_products = 0
    for seller, shop in rows:
        draft_count = (
            db.query(SSProduct)
            .filter(SSProduct.shop_id == shop.id, SSProduct.status == "draft")
            .count()
        )
        live_count = (
            db.query(SSProduct)
            .filter(SSProduct.shop_id == shop.id, SSProduct.status == "live")
            .count()
        )
        total_live_products += live_count
        summaries.append(
            ShelfSwipeSellerSummary(
                seller_id=str(seller.id),
                shop_id=str(shop.id),
                shop_name=shop.name,
                source_url=seller.source_url,
                is_demo=shop.is_demo,
                draft_count=draft_count,
                live_count=live_count,
                created_at=seller.created_at.isoformat(),
            )
        )

    return ShelfSwipeSellerListResponse(
        sellers=summaries,
        total_shops=len(summaries),
        total_live_products=total_live_products,
    )


@router.get("/products", response_model=ShelfSwipeAllProductsResponse)
def list_all_products(
    status_filter: Optional[str] = Query(default="draft", alias="status", pattern="^(draft|live|all)$"),
    db: Session = Depends(get_db),
):
    """
    Returns products across ALL onboarded shops (not just one seller), each
    annotated with which shop/seller it belongs to. Powers the 'All Products'
    aggregate view; bulk-approving across shops is done by grouping the
    returned items by seller_id and calling the existing per-seller
    /sellers/{seller_id}/approve endpoint once per seller.
    """
    query = (
        db.query(SSProduct, SSShop)
        .join(SSShop, SSProduct.shop_id == SSShop.id)
    )
    if status_filter in ("draft", "live"):
        query = query.filter(SSProduct.status == status_filter)

    rows = query.order_by(SSProduct.created_at.asc()).all()

    items = [
        ShelfSwipeProductWithShop(
            id=str(p.id),
            external_id=p.external_id,
            name=p.name,
            price=float(p.price),
            currency=p.currency,
            image_url=p.image_url,
            description=p.description,
            category=p.category,
            tags=p.tags or [],
            stock=p.stock,
            status=p.status,
            data_source=p.source,
            source_url=p.source_url,
            provider_ref=p.provider_ref,
            review_flags=p.review_flags or [],
            seller_id=str(shop.seller_id),
            shop_id=str(shop.id),
            shop_name=shop.name,
        )
        for p, shop in rows
    ]

    return ShelfSwipeAllProductsResponse(products=items, total_matches=len(items))


# =========================================================
# Buyer Swipe Deck (live SSProduct only, across onboarded shops)
# =========================================================

@router.get("/buyer/deck", response_model=BuyerDeckResponse)
def get_buyer_deck(
    shop_id: Optional[str] = Query(default=None),
    query: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Returns live (approved) products a buyer can swipe through, optionally
    scoped to one shop (shop_id) or spanning every onboarded shop, with an
    optional simple keyword filter.
    """
    rows_query = (
        db.query(SSProduct, SSShop)
        .join(SSShop, SSProduct.shop_id == SSShop.id)
        .filter(SSProduct.status == "live")
    )
    if shop_id:
        rows_query = rows_query.filter(SSProduct.shop_id == shop_id)

    rows = rows_query.order_by(SSProduct.created_at.desc()).all()

    if query:
        terms = {t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) > 2}
        if terms:
            def matches(p: SSProduct) -> bool:
                haystack = " ".join((p.name, p.category, p.description or "")).lower()
                return bool(terms.intersection(re.findall(r"[a-z0-9]+", haystack)))
            rows = [(p, shop) for p, shop in rows if matches(p)]

    deck_items = [
        BuyerDeckProductItem(
            id=str(p.id),
            shop_id=str(shop.id),
            shop_name=shop.name,
            name=p.name,
            price=float(p.price),
            currency=p.currency,
            image_url=p.image_url,
            description=p.description,
            category=p.category,
            tags=p.tags or [],
            stock=p.stock,
        )
        for p, shop in rows
    ]

    return BuyerDeckResponse(
        deck=deck_items,
        total_matches=len(deck_items),
        shop_id=shop_id,
        query=query,
    )


@router.post("/buyer/swipe", response_model=BuyerSwipeResponse)
def record_buyer_swipe(req: BuyerSwipeRequest, db: Session = Depends(get_db)):
    """
    Records a buyer's swipe (left=pass, right=interested) against a live
    SSProduct. Gets-or-creates the SSBuyerProfile row for the client-generated
    buyer_id so no separate 'create profile' round trip is needed.
    """
    if req.direction not in ("left", "right"):
        raise HTTPException(status_code=400, detail="direction must be 'left' or 'right'")

    product = db.query(SSProduct).filter(SSProduct.id == req.product_id, SSProduct.status == "live").first()
    if not product:
        raise HTTPException(status_code=404, detail="Live product not found")

    buyer = db.query(SSBuyerProfile).filter(SSBuyerProfile.id == req.buyer_id).first()
    if not buyer:
        buyer = SSBuyerProfile(id=req.buyer_id)
        db.add(buyer)
        db.flush()

    db.add(SSSwipe(
        id=str(uuid.uuid4()),
        buyer_id=buyer.id,
        product_id=product.id,
        direction=req.direction,
    ))
    db.commit()

    return BuyerSwipeResponse(status="recorded", direction=req.direction, product_id=req.product_id)


# =========================================================
# Legacy Compatibility Endpoints (retained for test_shelfswipe)
# =========================================================

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
    count = db.query(ShelfProduct).count()
    if count == 0:
        seed_demo_catalog(db)

    liked_swipes = db.query(SwipeAction).filter(
        SwipeAction.buyer_ref == buyer_ref,
        SwipeAction.direction == "right"
    ).all()
    liked_product_ids = [s.product_id for s in liked_swipes]

    liked_categories = set()
    if liked_product_ids:
        liked_prods = db.query(ShelfProduct.category).filter(ShelfProduct.id.in_(liked_product_ids)).all()
        liked_categories = {c[0] for c in liked_prods}

    products = db.query(ShelfProduct).filter(ShelfProduct.status == "live", ShelfProduct.stock > 0).all()
    stop_words = {"the", "and", "for", "with", "under", "nearby", "from"}
    query_terms = {
        term for term in re.findall(r"[a-z0-9]+", query.lower())
        if len(term) > 2 and term not in stop_words
    }

    def searchable_text(product: ShelfProduct) -> str:
        return " ".join((product.name, product.category, product.description, product.why_matches or "")).lower()

    if query_terms:
        products = [
            product for product in products
            if query_terms.intersection(re.findall(r"[a-z0-9]+", searchable_text(product)))
        ]

    def rank_score(p: ShelfProduct):
        score = 0
        if p.category in liked_categories:
            score += 50
        product_terms = set(re.findall(r"[a-z0-9]+", searchable_text(p)))
        score += 30 * len(query_terms.intersection(product_terms))
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
    Seamless PayPal Checkout for ShelfSwipe items, wired with PayTrace's lifecycle and recovery engine.
    """
    # The current buyer deck is backed by ss_products. Keep legacy products
    # payable for the retained prototype, but resolve current IDs first.
    prod = db.query(SSProduct).filter(
        SSProduct.id == req.product_id,
        SSProduct.status == "live",
    ).first()
    legacy_product = False
    if not prod:
        prod = db.query(ShelfProduct).filter(ShelfProduct.id == req.product_id).first()
        legacy_product = prod is not None
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
            if prod.currency != "USD":
                raise ValueError("ShelfSwipe PayPal checkout requires USD")
            order_data = await paypal_client.create_order(
                amount=total_amount,
                currency=prod.currency,
                custom_id=payment_id,
                return_url=f"{settings.FRONTEND_ORIGIN}/shelfswipe/buyer-prototype?status=approved",
                cancel_url=f"{settings.FRONTEND_ORIGIN}/shelfswipe/buyer-prototype?status=cancelled",
            )
            validate_created_order_amount(order_data, total_amount, prod.currency)
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
            diagnostics.update({"requested_amount": f"{total_amount:.2f}", "requested_currency": prod.currency})
            logger.error("ShelfSwipe PayPal order creation failed", extra={"paypal_diagnostics": diagnostics})
            raise HTTPException(status_code=502, detail="Failed to create PayPal Sandbox order") from exc

    if is_mock:
        order_data = mock_paypal.create_order(
            amount=total_amount,
            currency=prod.currency,
            custom_id=payment_id,
        )
        paypal_order_id = order_data["id"]
        approval_url = f"{settings.FRONTEND_ORIGIN}/demo/approval?token={paypal_order_id}&return_to=shelfswipe-buyer"

    # Register in PayTrace unified payment ledger
    payment = Payment(
        id=payment_id,
        paypal_order_id=paypal_order_id,
        customer_ref=req.buyer_ref,
        session_id=req.session_id,
        amount=total_amount,
        currency=prod.currency,
        status="CREATED",
        actor="human",
        source_mode="SIMULATED" if is_mock else f"PAYPAL_{settings.paypal_mode.upper()}",
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
        metadata={"product_name": prod.name, "quantity": req.quantity, "seller_id": getattr(prod, "seller_id", None), "shop_id": getattr(prod, "shop_id", None), "legacy_product": legacy_product},
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
        "is_mock": is_mock,
        "checkout_token": create_checkout_token(paypal_order_id),
    }

import os
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from pydantic import ValidationError

from app.core.time import utc_now
from app.db.models.shelfswipe import (
    SSSeller,
    SSShop,
    SSProduct,
    SSExtractionJob,
)
from app.schemas.shelfswipe import McpShopCatalogSchema, McpProductSchema
from app.services.shelfswipe import mcp_client
from app.services.shelfswipe.catalog_provider import CatalogProvider
from app.services.shelfswipe.fixture_provider import FixtureCatalogProvider

logger = logging.getLogger("paytrace.shelfswipe.importer")

# Default demo center (San Francisco Market St corridor)
DEFAULT_CENTER_LAT = 37.7749
DEFAULT_CENTER_LNG = -122.4194

# Fixture descriptions mention other cities (e.g. Vermont, Portland, Austin),
# so these coordinates are made-up demo locations clustered near the demo center
# (within ~1 to 15 km) for local pickup and discovery.
DEMO_OFFSETS = {
    "artisan-pottery-001": (0.012, 0.015),       # ~1.8 km
    "morning-crust-bakery-002": (-0.018, 0.022), # ~2.6 km
    "green-haven-home-003": (0.035, -0.025),     # ~4.6 km
    "tinker-lab-tech-004": (-0.045, -0.040),     # ~6.3 km
    "bloom-bath-body-005": (0.060, 0.050),       # ~8.7 km
}


class ConsentRequiredError(Exception):
    """Raised when onboarding is attempted without explicit seller consent."""
    pass


@dataclass
class ImportResult:
    seller_id: str
    shop_id: str
    job_id: str
    products_created: int
    products_skipped: int


def get_demo_center() -> tuple[float, float]:
    """Reads configured demo center latitude & longitude, with sensible defaults."""
    try:
        lat = float(os.getenv("SHELFSWIPE_DEMO_CENTER_LAT", str(DEFAULT_CENTER_LAT)))
    except (ValueError, TypeError):
        lat = DEFAULT_CENTER_LAT

    try:
        lng = float(os.getenv("SHELFSWIPE_DEMO_CENTER_LNG", str(DEFAULT_CENTER_LNG)))
    except (ValueError, TypeError):
        lng = DEFAULT_CENTER_LNG

    return lat, lng


def get_demo_location_for_shop(shop_id: Optional[str]) -> tuple[float, float]:
    """Calculates demo coordinates within ~1 to 15km of the configured demo center."""
    center_lat, center_lng = get_demo_center()
    offset_lat, offset_lng = DEMO_OFFSETS.get(shop_id or "", (0.010, 0.010))
    return round(center_lat + offset_lat, 6), round(center_lng + offset_lng, 6)


def compute_product_review_flags(product: McpProductSchema) -> List[str]:
    """
    Computes quality/readiness review flags for an imported product:
    - 'missing_image': no image URL or empty string
    - 'missing_description': no description or whitespace only
    - 'no_tags': empty tag list
    - 'invalid_price': price <= 0
    - 'confirm_stock': always added, requiring seller to confirm stock before going live
    - 'stock_unknown': added if product source is channel3
    """
    flags: List[str] = []

    if not product.image_url or not str(product.image_url).strip():
        flags.append("missing_image")

    if not product.description or not str(product.description).strip():
        flags.append("missing_description")

    if not product.tags or len(product.tags) == 0:
        flags.append("no_tags")

    if product.price <= Decimal("0.00"):
        flags.append("invalid_price")

    # Sellers must always verify stock availability at onboarding approval
    flags.append("confirm_stock")

    if product.source == "channel3":
        flags.append("stock_unknown")

    return flags


def recompute_ss_product_review_flags(product: SSProduct) -> List[str]:
    """
    Recomputes review flags for an SSProduct upon merchant edits:
    - Clears missing_image if image_url is populated.
    - Clears missing_description if description is populated.
    - Clears no_tags if tags are present.
    - Clears invalid_price if price > 0.
    - Retains confirm_stock until explicitly approved.
    - Retains stock_unknown if from channel3.
    """
    flags = list(product.review_flags or [])

    # missing_image
    if not product.image_url or not str(product.image_url).strip():
        if "missing_image" not in flags:
            flags.append("missing_image")
    else:
        flags = [f for f in flags if f != "missing_image"]

    # missing_description
    if not product.description or not str(product.description).strip():
        if "missing_description" not in flags:
            flags.append("missing_description")
    else:
        flags = [f for f in flags if f != "missing_description"]

    # no_tags
    if not product.tags or len(product.tags) == 0:
        if "no_tags" not in flags:
            flags.append("no_tags")
    else:
        flags = [f for f in flags if f != "no_tags"]

    # invalid_price
    if product.price <= Decimal("0.00"):
        if "invalid_price" not in flags:
            flags.append("invalid_price")
    else:
        flags = [f for f in flags if f != "invalid_price"]

    # confirm_stock is retained while in draft
    if product.status == "draft" and "confirm_stock" not in flags:
        flags.append("confirm_stock")

    return flags


def import_shop(
    db: Session,
    shop_url: str,
    consent: bool,
    seller_name: Optional[str] = None,
    provider: Optional[CatalogProvider] = None,
    product_urls: Optional[List[str]] = None,
) -> ImportResult:
    """
    Imports a seller and their product catalog via a CatalogProvider.
    - Raises ConsentRequiredError if consent is False.
    - Idempotently creates or updates seller and shop.
    - Records an extraction job with status tracking.
    - Skips existing products to preserve merchant edits.
    """
    if not consent:
        raise ConsentRequiredError("Seller consent is required to import and onboard this shop catalog.")

    if provider is None:
        provider = FixtureCatalogProvider()

    # 1. Get or create seller
    seller = db.query(SSSeller).filter(SSSeller.source_url == shop_url).first()
    if not seller:
        seller = SSSeller(
            name=seller_name or "ShelfSwipe Merchant",
            contact_email=None,
            source_url=shop_url,
            consent_given_at=utc_now(),
        )
        db.add(seller)
        db.flush()
    else:
        seller.consent_given_at = utc_now()
        if seller_name:
            seller.name = seller_name
        db.flush()

    # 2. Create extraction job in "running" status
    job = SSExtractionJob(
        seller_id=seller.id,
        url=shop_url,
        status="running",
        raw_result=None,
        review_flags=None,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        # 3. Fetch normalized catalog via provider
        catalog = provider.fetch_catalog(shop_url=shop_url, product_urls=product_urls)

        # Update seller contact email if present in catalog and not yet set
        if catalog.contact_email and not seller.contact_email:
            seller.contact_email = catalog.contact_email
            db.flush()

        # Update seller name if was default
        if seller.name == "ShelfSwipe Merchant" and catalog.shop_name:
            seller.name = catalog.shop_name
            db.flush()

        # 4. Create or update shop
        ext_shop_id = catalog.shop_id or f"shop-{seller.id[:8]}"
        shop = db.query(SSShop).filter(
            (SSShop.seller_id == seller.id) | (SSShop.external_shop_id == ext_shop_id)
        ).first()

        is_demo = (catalog.source == "demo")
        if is_demo:
            lat, lng = get_demo_location_for_shop(catalog.shop_id)
            pickup_notes = "Demo pickup location"
        else:
            lat, lng = None, None
            pickup_notes = "Pending seller pickup notes"

        if not shop:
            shop = SSShop(
                seller_id=seller.id,
                external_shop_id=ext_shop_id,
                name=catalog.shop_name,
                description=catalog.description or "",
                latitude=lat,
                longitude=lng,
                pickup_notes=pickup_notes,
                source_domain=catalog.source_domain,
                is_demo=is_demo,
            )
            db.add(shop)
            db.flush()
        else:
            shop.name = catalog.shop_name
            shop.description = catalog.description or ""
            if is_demo:
                shop.latitude = lat
                shop.longitude = lng
                shop.pickup_notes = pickup_notes
            if catalog.source_domain:
                shop.source_domain = catalog.source_domain
            shop.is_demo = is_demo
            db.flush()

        # 5. Idempotently insert products (skip already imported products)
        products_created = 0
        products_skipped = 0
        all_job_review_flags: List[str] = []

        for p in catalog.products:
            existing = (
                db.query(SSProduct)
                .filter(
                    SSProduct.shop_id == shop.id,
                    SSProduct.external_id == p.id,
                )
                .first()
            )

            if existing:
                products_skipped += 1
                continue

            review_flags = compute_product_review_flags(p)
            for rf in review_flags:
                if rf not in all_job_review_flags:
                    all_job_review_flags.append(rf)

            product_record = SSProduct(
                shop_id=shop.id,
                external_id=p.id,
                name=p.name,
                price=p.price,
                currency=p.currency,
                image_url=p.image_url,
                description=p.description,
                category=p.category,
                tags=p.tags,
                stock=p.stock or 0,
                status="draft",
                source=p.source or ("demo" if is_demo else "channel3"),
                source_url=p.source_url,
                provider_ref=p.provider_ref,
                review_flags=review_flags,
            )
            db.add(product_record)
            products_created += 1

        # Add provider-level skipped variants/products
        products_skipped += getattr(catalog, "skipped_count", 0)

        # 6. Mark extraction job succeeded
        job.status = "succeeded"
        if getattr(catalog, "source", "") == "channel3":
            job.raw_result = {
                "total_products_extracted": len(catalog.products),
                "products_created": products_created,
                "products_skipped": products_skipped,
                "provider_refs": [p.provider_ref for p in catalog.products if p.provider_ref],
            }
        else:
            job.raw_result = catalog.model_dump(mode="json")
        job.review_flags = all_job_review_flags
        db.commit()

        return ImportResult(
            seller_id=seller.id,
            shop_id=shop.id,
            job_id=job.id,
            products_created=products_created,
            products_skipped=products_skipped,
        )

    except Exception as exc:
        sanitized_error = f"{type(exc).__name__}: {str(exc)}"
        try:
            job.status = "failed"
            job.raw_result = {"error": sanitized_error}
            db.commit()
        except Exception as inner_exc:
            logger.error(f"Failed to record failed status on extraction job: {inner_exc}")
            db.rollback()

        raise exc

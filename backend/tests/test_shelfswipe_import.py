import uuid
from decimal import Decimal
from unittest.mock import patch
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.models.shelfswipe import (
    SSSeller,
    SSShop,
    SSProduct,
    SSExtractionJob,
)
from app.api.dependencies import get_db, get_current_user
from app.db.models.user import User
from app.main import app
from app.services.shelfswipe.mcp_client import McpClientError


MOCK_2_PRODUCT_CATALOG = {
    "shop_id": "test-pottery-shop",
    "shop_name": "Test Clay Studio",
    "shop_url": "shelfswipe://fixtures/artisan_pottery",
    "contact_email": "hello@testpottery.dev",
    "description": "Handcrafted pottery for testing.",
    "products": [
        {
            "id": "prod-001",
            "name": "Artisan Stoneware Mug",
            "price": 28.50,
            "currency": "USD",
            "category": "Pottery & Kitchen",
            "description": "A wonderful handmade mug.",
            "image_url": "https://images.unsplash.com/photo-mug",
            "stock": 10,
            "tags": ["mug", "coffee", "ceramic"],
            "why_matches": "Canned static text ignored",
        },
        {
            "id": "prod-002",
            "name": "Broken Free Planter",
            "price": 0.0,
            "currency": "USD",
            "category": "Garden",
            "description": "",
            "image_url": None,
            "stock": 0,
            "tags": [],
            "why_matches": "Canned static text ignored",
        },
    ],
}


def test_onboard_consent_required(client):
    """Calling onboard with consent=False must return 400 and create nothing."""
    res = client.post(
        "/api/v1/shelfswipe/sellers/onboard",
        json={
            "shop_url": "shelfswipe://fixtures/artisan_pottery",
            "consent": False,
        },
    )
    assert res.status_code == 400
    assert "consent is required" in res.json()["detail"].lower()


@patch("app.services.shelfswipe.importer.mcp_client.fetch_catalog")
def test_successful_onboard_creates_draft_and_flags(mock_fetch, client, db_session):
    """Successful onboarding imports draft products and calculates quality review flags."""
    mock_fetch.return_value = MOCK_2_PRODUCT_CATALOG

    res = client.post(
        "/api/v1/shelfswipe/sellers/onboard",
        json={
            "shop_url": "shelfswipe://fixtures/artisan_pottery",
            "consent": True,
            "seller_name": "Clay Master",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["products_created"] == 2
    assert data["products_skipped"] == 0

    seller_id = data["seller_id"]
    shop_id = data["shop_id"]
    job_id = data["job_id"]

    # Verify job in DB
    job = db_session.query(SSExtractionJob).filter(SSExtractionJob.id == job_id).first()
    assert job is not None
    assert job.status == "succeeded"
    assert job.raw_result is not None

    # Verify products in DB
    products = (
        db_session.query(SSProduct)
        .filter(SSProduct.shop_id == shop_id)
        .order_by(SSProduct.external_id.asc())
        .all()
    )
    assert len(products) == 2

    p1, p2 = products[0], products[1]
    assert p1.status == "draft"
    assert p1.source == "demo"
    # p1 has full fields; only requires confirm_stock
    assert p1.review_flags == ["confirm_stock"]

    assert p2.status == "draft"
    # p2 has no image, empty description, empty tags, and price <= 0
    assert "missing_image" in p2.review_flags
    assert "missing_description" in p2.review_flags
    assert "no_tags" in p2.review_flags
    assert "invalid_price" in p2.review_flags
    assert "confirm_stock" in p2.review_flags


@patch("app.services.shelfswipe.importer.mcp_client.fetch_catalog")
def test_reimport_is_idempotent_and_does_not_overwrite_edited_product(
    mock_fetch, client, db_session
):
    """Re-importing the same shop must be idempotent and preserve existing products."""
    mock_fetch.return_value = MOCK_2_PRODUCT_CATALOG

    # Initial import
    res1 = client.post(
        "/api/v1/shelfswipe/sellers/onboard",
        json={"shop_url": "shelfswipe://fixtures/artisan_pottery", "consent": True},
    )
    assert res1.status_code == 201
    assert res1.json()["products_created"] == 2

    # Seller manually customizes a product in the database
    prod = (
        db_session.query(SSProduct)
        .filter(SSProduct.external_id == "prod-001")
        .first()
    )
    assert prod is not None
    prod.name = "Customized Artisanal Mug By Merchant"
    prod.price = Decimal("45.00")
    db_session.commit()

    # Re-import identical catalog
    res2 = client.post(
        "/api/v1/shelfswipe/sellers/onboard",
        json={"shop_url": "shelfswipe://fixtures/artisan_pottery", "consent": True},
    )
    assert res2.status_code == 201
    data2 = res2.json()
    assert data2["products_created"] == 0
    assert data2["products_skipped"] == 2

    # Verify customized product was untouched
    refreshed_prod = (
        db_session.query(SSProduct)
        .filter(SSProduct.external_id == "prod-001")
        .first()
    )
    assert refreshed_prod.name == "Customized Artisanal Mug By Merchant"
    assert refreshed_prod.price == Decimal("45.00")


@patch("app.services.shelfswipe.importer.mcp_client.fetch_catalog")
def test_malformed_catalog_marks_job_failed(mock_fetch, client, db_session):
    """If catalog validation fails, the job must be persisted with status 'failed'."""
    # Price is negative which violates ge=0 in McpProductSchema
    mock_fetch.return_value = {
        "shop_name": "Invalid Shop",
        "shop_url": "shelfswipe://fixtures/invalid",
        "products": [
            {
                "id": "bad-01",
                "name": "Negative Price Item",
                "price": -15.00,  # Fails Pydantic validation
            }
        ],
    }

    res = client.post(
        "/api/v1/shelfswipe/sellers/onboard",
        json={"shop_url": "shelfswipe://fixtures/invalid", "consent": True},
    )
    assert res.status_code == 422

    # Verify extraction job failed in DB
    job = (
        db_session.query(SSExtractionJob)
        .filter(SSExtractionJob.url == "shelfswipe://fixtures/invalid")
        .first()
    )
    assert job is not None
    assert job.status == "failed"
    assert job.raw_result is not None
    assert "error" in job.raw_result


@patch("app.services.shelfswipe.importer.mcp_client.fetch_catalog")
def test_draft_endpoint_returns_expected_shape(mock_fetch, client):
    """GET /sellers/{seller_id}/draft returns expected draft shop and product payloads."""
    mock_fetch.return_value = MOCK_2_PRODUCT_CATALOG

    onboard_res = client.post(
        "/api/v1/shelfswipe/sellers/onboard",
        json={"shop_url": "shelfswipe://fixtures/artisan_pottery", "consent": True},
    )
    assert onboard_res.status_code == 201
    seller_id = onboard_res.json()["seller_id"]

    draft_res = client.get(f"/api/v1/shelfswipe/sellers/{seller_id}/draft")
    assert draft_res.status_code == 200
    draft_data = draft_res.json()

    assert draft_data["seller_id"] == seller_id
    assert draft_data["is_demo"] is True
    assert isinstance(draft_data["latitude"], float)
    assert isinstance(draft_data["longitude"], float)
    assert draft_data["pickup_notes"] == "Demo pickup location"
    assert len(draft_data["products"]) == 2

    p1 = draft_data["products"][0]
    assert p1["external_id"] == "prod-001"
    assert isinstance(p1["price"], float)
    assert p1["price"] == 28.50
    assert p1["status"] == "draft"
    assert isinstance(p1["review_flags"], list)
    assert "confirm_stock" in p1["review_flags"]

    # 404 for nonexistent seller
    missing_id = str(uuid.uuid4())
    err_res = client.get(f"/api/v1/shelfswipe/sellers/{missing_id}/draft")
    assert err_res.status_code == 404


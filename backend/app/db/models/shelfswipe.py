import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    String,
    Numeric,
    DateTime,
    Integer,
    Text,
    Float,
    Boolean,
    ForeignKey,
    Index,
    JSON,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base
from app.core.time import utc_now


# ---------------------------------------------------------
# New ShelfSwipe Models (prefix: ss_)
# ---------------------------------------------------------

class SSSeller(Base):
    __tablename__ = "ss_sellers"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(128))
    contact_email: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    source_url: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    consent_given_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    shops: Mapped[List["SSShop"]] = relationship(
        "SSShop", back_populates="seller", cascade="all, delete-orphan"
    )
    extraction_jobs: Mapped[List["SSExtractionJob"]] = relationship(
        "SSExtractionJob", back_populates="seller", cascade="all, delete-orphan"
    )


class SSShop(Base):
    __tablename__ = "ss_shops"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    seller_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("ss_sellers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_shop_id: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, unique=True, index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pickup_notes: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    seller: Mapped["SSSeller"] = relationship("SSSeller", back_populates="shops")
    products: Mapped[List["SSProduct"]] = relationship(
        "SSProduct", back_populates="shop", cascade="all, delete-orphan"
    )


class SSProduct(Base):
    __tablename__ = "ss_products"
    __table_args__ = (
        UniqueConstraint("shop_id", "external_id", name="uq_ss_products_shop_external_id"),
        Index("ix_ss_products_shop_status", "shop_id", "status"),
    )

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    shop_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("ss_shops.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_id: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(256), index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    image_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(128), index=True)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    stock: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="draft")  # draft, live
    source: Mapped[str] = mapped_column(String(32), default="demo")   # scraped, manual, demo
    review_flags: Mapped[List[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    shop: Mapped["SSShop"] = relationship("SSShop", back_populates="products")


class SSExtractionJob(Base):
    __tablename__ = "ss_extraction_jobs"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    seller_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("ss_sellers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    url: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32), default="running")  # running, succeeded, failed
    raw_result: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    review_flags: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    seller: Mapped["SSSeller"] = relationship("SSSeller", back_populates="extraction_jobs")


class SSBuyerProfile(Base):
    __tablename__ = "ss_buyer_profiles"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    preference_vector: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    budget_hint: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class SSSwipe(Base):
    __tablename__ = "ss_swipes"
    __table_args__ = (
        Index("ix_ss_swipes_buyer_created_at", "buyer_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    buyer_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("ss_buyer_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("ss_products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    direction: Mapped[str] = mapped_column(String(16))  # "left", "right"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class SSOrder(Base):
    __tablename__ = "ss_orders"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    buyer_id: Mapped[Optional[str]] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("ss_buyer_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    product_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("ss_products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    paypal_order_id: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, unique=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="created")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


# ---------------------------------------------------------
# Legacy Prototype Models (retained so Alembic autogenerate
# doesn't attempt to drop them and breaks existing teammate tests)
# ---------------------------------------------------------

class Seller(Base):
    __tablename__ = "shelfswipe_sellers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(128))
    contact_email: Mapped[str] = mapped_column(String(128))
    source_url: Mapped[str] = mapped_column(String(512))
    consent_given_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    products: Mapped[List["ShelfProduct"]] = relationship(
        "ShelfProduct", back_populates="seller", cascade="all, delete-orphan"
    )


class ShelfProduct(Base):
    __tablename__ = "shelfswipe_products"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    seller_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("shelfswipe_sellers.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(256), index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    image_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(64), index=True)
    stock: Mapped[int] = mapped_column(Integer, default=10)
    status: Mapped[str] = mapped_column(String(32), default="live")
    source: Mapped[str] = mapped_column(String(32), default="scraped")
    why_matches: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    seller: Mapped["Seller"] = relationship("Seller", back_populates="products")


class SwipeAction(Base):
    __tablename__ = "shelfswipe_swipes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    buyer_ref: Mapped[str] = mapped_column(String(64), index=True)
    product_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("shelfswipe_products.id", ondelete="CASCADE"), index=True
    )
    direction: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ShelfCartItem(Base):
    """A buyer's in-progress cart, built up conversationally via the shopping assistant."""
    __tablename__ = "shelfswipe_cart_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    buyer_ref: Mapped[str] = mapped_column(String(64), index=True)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("shelfswipe_products.id", ondelete="CASCADE"), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    product: Mapped["ShelfProduct"] = relationship("ShelfProduct")

    __table_args__ = (
        Index("ix_shelfswipe_cart_buyer_product", "buyer_ref", "product_id", unique=True),
    )


class ShelfOrderItem(Base):
    """Line-item snapshot of a multi-product ShelfSwipe order, linked to the unified Payment ledger."""
    __tablename__ = "shelfswipe_order_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    payment_id: Mapped[str] = mapped_column(String(36), ForeignKey("payments.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("shelfswipe_products.id", ondelete="CASCADE"), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    name_snapshot: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

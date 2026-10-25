import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Numeric, DateTime, Integer, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, List
from app.db.base import Base
from app.core.time import utc_now

class Seller(Base):
    __tablename__ = "shelfswipe_sellers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(128))
    contact_email: Mapped[str] = mapped_column(String(128))
    source_url: Mapped[str] = mapped_column(String(512))
    consent_given_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    products: Mapped[List["ShelfProduct"]] = relationship("ShelfProduct", back_populates="seller", cascade="all, delete-orphan")


class ShelfProduct(Base):
    __tablename__ = "shelfswipe_products"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    seller_id: Mapped[str] = mapped_column(String(36), ForeignKey("shelfswipe_sellers.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(256), index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    image_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(64), index=True)
    stock: Mapped[int] = mapped_column(Integer, default=10)
    status: Mapped[str] = mapped_column(String(32), default="live") # draft, live
    source: Mapped[str] = mapped_column(String(32), default="scraped") # scraped, manual, demo
    why_matches: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    seller: Mapped["Seller"] = relationship("Seller", back_populates="products")


class SwipeAction(Base):
    __tablename__ = "shelfswipe_swipes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    buyer_ref: Mapped[str] = mapped_column(String(64), index=True)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("shelfswipe_products.id", ondelete="CASCADE"), index=True)
    direction: Mapped[str] = mapped_column(String(16)) # right (liked), left (disliked)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

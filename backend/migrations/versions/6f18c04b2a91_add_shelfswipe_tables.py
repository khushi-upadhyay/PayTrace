"""Add ShelfSwipe seller, product, and swipe tables.

Revision ID: 6f18c04b2a91
Revises: c5d7fa7ab7f9
Create Date: 2026-10-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6f18c04b2a91"
down_revision: Union[str, None] = "c5d7fa7ab7f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shelfswipe_sellers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("contact_email", sa.String(length=128), nullable=False),
        sa.Column("source_url", sa.String(length=512), nullable=False),
        sa.Column("consent_given_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "shelfswipe_products",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("seller_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("image_url", sa.String(length=1024), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("stock", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("why_matches", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["seller_id"], ["shelfswipe_sellers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shelfswipe_products_seller_id", "shelfswipe_products", ["seller_id"])
    op.create_index("ix_shelfswipe_products_name", "shelfswipe_products", ["name"])
    op.create_index("ix_shelfswipe_products_category", "shelfswipe_products", ["category"])
    op.create_table(
        "shelfswipe_swipes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("buyer_ref", sa.String(length=64), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["shelfswipe_products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shelfswipe_swipes_buyer_ref", "shelfswipe_swipes", ["buyer_ref"])
    op.create_index("ix_shelfswipe_swipes_product_id", "shelfswipe_swipes", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_shelfswipe_swipes_product_id", table_name="shelfswipe_swipes")
    op.drop_index("ix_shelfswipe_swipes_buyer_ref", table_name="shelfswipe_swipes")
    op.drop_table("shelfswipe_swipes")
    op.drop_index("ix_shelfswipe_products_category", table_name="shelfswipe_products")
    op.drop_index("ix_shelfswipe_products_name", table_name="shelfswipe_products")
    op.drop_index("ix_shelfswipe_products_seller_id", table_name="shelfswipe_products")
    op.drop_table("shelfswipe_products")
    op.drop_table("shelfswipe_sellers")

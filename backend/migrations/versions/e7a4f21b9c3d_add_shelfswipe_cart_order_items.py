"""Add ShelfSwipe cart items and multi-item order line tables.

Revision ID: e7a4f21b9c3d
Revises: d2f9a4b1c6e3
Create Date: 2026-11-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e7a4f21b9c3d"
down_revision: Union[str, None] = "d2f9a4b1c6e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shelfswipe_cart_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("buyer_ref", sa.String(length=64), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("added_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["shelfswipe_products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shelfswipe_cart_items_buyer_ref", "shelfswipe_cart_items", ["buyer_ref"])
    op.create_index("ix_shelfswipe_cart_items_product_id", "shelfswipe_cart_items", ["product_id"])
    op.create_index(
        "ix_shelfswipe_cart_buyer_product",
        "shelfswipe_cart_items",
        ["buyer_ref", "product_id"],
        unique=True,
    )

    op.create_table(
        "shelfswipe_order_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("payment_id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("name_snapshot", sa.String(length=256), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["shelfswipe_products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shelfswipe_order_items_payment_id", "shelfswipe_order_items", ["payment_id"])
    op.create_index("ix_shelfswipe_order_items_product_id", "shelfswipe_order_items", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_shelfswipe_order_items_product_id", table_name="shelfswipe_order_items")
    op.drop_index("ix_shelfswipe_order_items_payment_id", table_name="shelfswipe_order_items")
    op.drop_table("shelfswipe_order_items")

    op.drop_index("ix_shelfswipe_cart_buyer_product", table_name="shelfswipe_cart_items")
    op.drop_index("ix_shelfswipe_cart_items_product_id", table_name="shelfswipe_cart_items")
    op.drop_index("ix_shelfswipe_cart_items_buyer_ref", table_name="shelfswipe_cart_items")
    op.drop_table("shelfswipe_cart_items")

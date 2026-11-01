"""Add disputes table.

Revision ID: d2f9a4b1c6e3
Revises: a1b2c3d4e5f6
Create Date: 2026-11-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d2f9a4b1c6e3"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "disputes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("payment_id", sa.String(length=36), nullable=False),
        sa.Column("paypal_dispute_id", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("buyer_statement", sa.String(length=1024), nullable=True),
        sa.Column("seller_response", sa.String(length=1024), nullable=True),
        sa.Column("outcome_note", sa.String(length=1024), nullable=True),
        sa.Column("is_simulated", sa.Boolean(), nullable=False),
        sa.Column("opened_at", sa.DateTime(), nullable=False),
        sa.Column("response_due_by", sa.DateTime(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("paypal_dispute_id"),
    )
    op.create_index("ix_disputes_payment_id", "disputes", ["payment_id"])
    op.create_index("ix_disputes_paypal_dispute_id", "disputes", ["paypal_dispute_id"])
    op.create_index("ix_disputes_status", "disputes", ["status"])
    op.create_index("ix_disputes_status_opened_at", "disputes", ["status", "opened_at"])


def downgrade() -> None:
    op.drop_index("ix_disputes_status_opened_at", table_name="disputes")
    op.drop_index("ix_disputes_status", table_name="disputes")
    op.drop_index("ix_disputes_paypal_dispute_id", table_name="disputes")
    op.drop_index("ix_disputes_payment_id", table_name="disputes")
    op.drop_table("disputes")

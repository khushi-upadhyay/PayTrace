"""Extend session events for tab-aware observability and UTC ingestion metadata.

Revision ID: ba72f44c2e91
Revises: 6f18c04b2a91
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "ba72f44c2e91"
down_revision: Union[str, None] = "6f18c04b2a91"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("last_activity_at", sa.DateTime(), nullable=True))
    op.execute("UPDATE sessions SET last_activity_at = started_at WHERE last_activity_at IS NULL")
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.alter_column("last_activity_at", nullable=False)
        batch_op.create_index("ix_sessions_last_activity_at", ["last_activity_at"])

    op.add_column("session_events", sa.Column("category", sa.String(length=32), nullable=True))
    op.add_column("session_events", sa.Column("source", sa.String(length=16), nullable=True))
    op.add_column("session_events", sa.Column("tab_id", sa.String(length=64), nullable=True))
    op.add_column("session_events", sa.Column("segment_id", sa.String(length=64), nullable=True))
    op.add_column("session_events", sa.Column("session_offset_ms", sa.Integer(), nullable=True))
    op.add_column("session_events", sa.Column("route", sa.String(length=512), nullable=True))
    op.add_column("session_events", sa.Column("payment_id", sa.String(length=36), nullable=True))
    op.add_column("session_events", sa.Column("order_id", sa.String(length=64), nullable=True))
    op.add_column("session_events", sa.Column("severity", sa.String(length=16), nullable=True))
    op.add_column("session_events", sa.Column("trace_id", sa.String(length=64), nullable=True))
    op.add_column("session_events", sa.Column("received_at", sa.DateTime(), nullable=True))
    op.execute("UPDATE session_events SET received_at = occurred_at WHERE received_at IS NULL")
    op.execute("UPDATE session_events SET category = CASE WHEN event_type = 'rrweb' THEN 'replay' WHEN event_type IN ('network', 'console') THEN event_type WHEN event_type LIKE 'session_%' OR event_type LIKE 'tab_%' OR event_type LIKE 'route_%' THEN 'lifecycle' ELSE 'application' END WHERE category IS NULL")
    op.execute("UPDATE session_events SET source = 'browser' WHERE source IS NULL")
    with op.batch_alter_table("session_events") as batch_op:
        batch_op.alter_column("category", nullable=False, server_default="application")
        batch_op.alter_column("source", nullable=False, server_default="browser")
        batch_op.alter_column("received_at", nullable=False)
        batch_op.create_index("ix_session_events_category", ["category"])
        batch_op.create_index("ix_session_events_tab_id", ["tab_id"])
        batch_op.create_index("ix_session_events_segment_id", ["segment_id"])
        batch_op.create_index("ix_session_events_payment_id", ["payment_id"])
        batch_op.create_index("ix_session_events_trace_id", ["trace_id"])
        batch_op.create_index("ix_session_events_session_tab_occurred", ["session_id", "tab_id", "occurred_at"])
        batch_op.create_index("ix_session_events_session_category_occurred", ["session_id", "category", "occurred_at"])


def downgrade() -> None:
    with op.batch_alter_table("session_events") as batch_op:
        batch_op.drop_index("ix_session_events_session_category_occurred")
        batch_op.drop_index("ix_session_events_session_tab_occurred")
        batch_op.drop_index("ix_session_events_trace_id")
        batch_op.drop_index("ix_session_events_payment_id")
        batch_op.drop_index("ix_session_events_tab_id")
        batch_op.drop_index("ix_session_events_segment_id")
        batch_op.drop_index("ix_session_events_category")
        for column in ("received_at", "trace_id", "severity", "order_id", "payment_id", "route", "session_offset_ms", "segment_id", "tab_id", "source", "category"):
            batch_op.drop_column(column)
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.drop_index("ix_sessions_last_activity_at")
        batch_op.drop_column("last_activity_at")

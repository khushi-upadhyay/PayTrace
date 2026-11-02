"""shelfswipe provider fields

Revision ID: 3238f488c39d
Revises: 82c4670141a6
Create Date: 2026-11-03 01:12:16.955803

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3238f488c39d'
down_revision: Union[str, None] = '82c4670141a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('ss_products', sa.Column('source_url', sa.String(length=512), nullable=True))
    op.add_column('ss_products', sa.Column('provider_ref', sa.String(length=128), nullable=True))
    op.add_column('ss_shops', sa.Column('source_domain', sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column('ss_shops', 'source_domain')
    op.drop_column('ss_products', 'provider_ref')
    op.drop_column('ss_products', 'source_url')

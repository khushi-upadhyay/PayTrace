"""Merge cart/order and ShelfSwipe provider migration histories."""

from typing import Sequence, Union


revision: str = "c1b5d8e2a904"
down_revision: Union[str, Sequence[str], None] = (
    "e7a4f21b9c3d",
    "3238f488c39d",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

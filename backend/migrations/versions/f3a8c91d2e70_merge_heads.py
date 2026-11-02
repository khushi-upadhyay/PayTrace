"""Merge ShelfSwipe and disputes migration heads."""

from typing import Sequence, Union

revision: str = "f3a8c91d2e70"
down_revision: Union[str, Sequence[str], None] = (
    "adcfa4b047f5",
    "d2f9a4b1c6e3",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

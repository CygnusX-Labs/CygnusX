"""merge_cookie_adjust_heads

Revision ID: i6j7k8l9m0n1
Revises: g3h4i5j6k7l8, h4i5j6k7l8m9
Create Date: 2026-07-02 22:50:00

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = 'i6j7k8l9m0n1'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = ('g3h4i5j6k7l8', 'h4i5j6k7l8m9')


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

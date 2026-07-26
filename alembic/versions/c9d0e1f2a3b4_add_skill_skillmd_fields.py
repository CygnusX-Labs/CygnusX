"""add skill skillmd fields

技能表对齐 SKILL.md 开放格式：版本 / 作者 / 来源类型与引用 /
commit 快照 / 是否含脚本 / frontmatter 留档。

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-07-26 00:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('skills', sa.Column('version', sa.String(length=50), nullable=True))
    op.add_column('skills', sa.Column('author', sa.String(length=100), nullable=True))
    op.add_column(
        'skills',
        sa.Column(
            'source_type',
            sa.String(length=20),
            nullable=False,
            server_default='json',
        ),
    )
    op.add_column('skills', sa.Column('source_ref', sa.String(length=500), nullable=True))
    op.add_column('skills', sa.Column('source_commit', sa.String(length=64), nullable=True))
    op.add_column(
        'skills',
        sa.Column(
            'has_scripts',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),
        ),
    )
    op.add_column('skills', sa.Column('frontmatter', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('skills', 'frontmatter')
    op.drop_column('skills', 'has_scripts')
    op.drop_column('skills', 'source_commit')
    op.drop_column('skills', 'source_ref')
    op.drop_column('skills', 'source_type')
    op.drop_column('skills', 'author')
    op.drop_column('skills', 'version')

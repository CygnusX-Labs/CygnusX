"""merge mcp contract_digest and project delivery heads

合并两条并行分支头：
- projectdelivery01（项目交付导出，主干）
- c1d2e3f4b5a6（mcp_versions 契约指纹，自 a5b6c7d8e9f0 拉出）

c1d2e3f4b5a6 原 revision ID 与主干 a6b7c8d9e0f1（projects.customer）
冲突，已重命名（该迁移从未在任何环境应用过）。

Revision ID: mcpdigestmerge01
Revises: projectdelivery01, c1d2e3f4b5a6
Create Date: 2026-10-16
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "mcpdigestmerge01"
down_revision: str | Sequence[str] | None = ("projectdelivery01", "c1d2e3f4b5a6")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

"""add contract_digest to mcp_versions

架构审查 §7.3：版本契约指纹（工具 schema/描述 + 语义配置的规范化 SHA-256，
格式 "v1:<hex>"），供版本详情/差异比较/回退兼容性校验使用。

背景见 ARCHITECTURE_DESIGN/CygnusX_mcp_architecture.md §12（2026-10-16 审查响应）。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f4b5a6"
down_revision: str | None = "h6i7j8k9l1m3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "mcp_versions",
        sa.Column(
            "contract_digest",
            sa.String(80),
            nullable=False,
            server_default="",
        ),
    )


def downgrade() -> None:
    op.drop_column("mcp_versions", "contract_digest")

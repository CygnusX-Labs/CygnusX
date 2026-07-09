"""站点设置 ORM 模型 — 单行配置（id 恒为 1）"""

from typing import Any

from sqlalchemy import JSON, Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from omichub.infrastructure.database.base import Base, TimestampMixin


class SiteSettingModel(Base, TimestampMixin):
    """站点级全局设置（单行表，id 固定为 1）"""

    __tablename__ = "site_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    registration_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    totp_policy: Mapped[str] = mapped_column(String(16), default="optional", nullable=False)
    home_quick_entries: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )

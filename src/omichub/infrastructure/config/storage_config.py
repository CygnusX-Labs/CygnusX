"""存储目录配置 —— 统一从 data/OmicHub.yaml 的 storage 段读取 data_root。

设计目标：避免在代码中硬编码数据路径。所有需要数据根目录的后端逻辑都应调用
`get_storage_config()`，而不是直接读 `settings.storage_path` 或写死字符串。

解析优先级（逐级降级，文件缺失/解析失败/字段为空时静默回退，绝不抛异常）：
  1) YAML storage.data_root          ← 本文件 storage 段
  2) settings.storage_path           ← .env 的 STORAGE_PATH（默认 /data/omichub）
  3) 内置兜底 /data/omichub

复用 settings.site_content_yaml 指向的同一份 OmicHub.yaml，与 SiteContentService
保持单一配置源，不引入额外的 yaml 文件。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from omichub.core.config import get_settings

# 内置兜底：YAML 与 env 都缺失时的最终默认值
_DEFAULT_DATA_ROOT = "/data/omichub"
# 用户数据子目录名（与 FileService.user_raw_dir 等落盘约定一致）
_DEFAULT_USERS_SUBDIR = "users"


@dataclass(frozen=True)
class StorageConfig:
    """存储目录配置"""

    data_root: str
    users_subdir: str


def _load_yaml_dict(path: Path) -> dict[str, Any]:
    """读盘；文件不存在 / 解析失败 / 非字典时返回空 dict（由降级逻辑兜底）。"""
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except (yaml.YAMLError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def get_storage_config(yaml_path: str | Path | None = None) -> StorageConfig:
    """解析存储配置。

    YAML storage 段优先；data_root 缺失时回退到 settings.storage_path，
    再缺失回退到内置默认。users_subdir 缺失时回退到内置默认。
    """
    settings = get_settings()
    path = Path(yaml_path) if yaml_path else Path(settings.site_content_yaml)
    data = _load_yaml_dict(path)

    raw_storage = data.get("storage")
    storage: dict[str, Any] = raw_storage if isinstance(raw_storage, dict) else {}

    data_root = (
        str(storage.get("data_root") or "").strip()
        or str(settings.storage_path or "").strip()
        or _DEFAULT_DATA_ROOT
    )
    users_subdir = str(storage.get("users_subdir") or "").strip() or _DEFAULT_USERS_SUBDIR
    return StorageConfig(data_root=data_root, users_subdir=users_subdir)

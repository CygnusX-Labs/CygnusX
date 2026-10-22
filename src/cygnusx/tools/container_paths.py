"""分析工具共享数据卷的宿主、Worker 与容器路径契约。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from cygnusx.core.exceptions import ValidationError

CONTAINER_DATA_ROOT = Path("/data/cygnusx")  # 容器内固定为 /data/cygnusx


@dataclass(frozen=True)
class ToolDataMount:
    """source 是 Docker daemon 的路径，storage_root 是 Worker 中的同一数据根。"""

    source: str
    storage_root: str

    @property
    def volume(self) -> str:
        return f"{self.source}:{CONTAINER_DATA_ROOT}"

    def container_path(self, path: str) -> str:
        """转换共享卷内的绝对路径，兼容已有容器路径，拒绝越界或相对路径。"""
        normalized = Path(os.path.normpath(path))
        roots = (self.storage_root, self.source, str(CONTAINER_DATA_ROOT))
        for value in roots:
            root = Path(os.path.normpath(value))
            if root.is_absolute() and normalized.is_relative_to(root):
                return str(CONTAINER_DATA_ROOT / normalized.relative_to(root))
        raise ValidationError(f"文件路径不在共享数据挂载内: {path}")

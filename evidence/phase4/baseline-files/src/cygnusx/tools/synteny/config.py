"""基因组共线性分析工具外置 YAML 配置加载器。

配置文件路径由 settings.synteny_config_yaml 决定（默认 tool_configs/synteny/synteny_config.yaml）。

热重载策略（与 deg/enrichments/jbrowse/gsea 一致）：
- SyntenyConfigManager 单例缓存解析后的 SyntenyConfig，按文件 mtime 判定是否重解析；
- 文件不存在 / 解析失败 / 字段缺失时回退内置默认配置，绝不抛异常；
- 改文件后由加载器 mtime 自动热重载，无需重启。

镜像契约见 deploy/docker/Dockerfile.synteny（构建上下文为 tool_configs/synteny/），
本文件只管输入扩展名、输出文件名与 dot plot 渲染边界。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from cygnusx.core.config import get_settings


class SyntenyInputConfig(BaseModel):
    """上传输入的扩展名契约（仅前端选择器过滤用，解析按内容判断）。"""

    model_config = ConfigDict(extra="ignore")

    gff3_extensions: list[str] = Field(default=[".gff3", ".gff"])
    blast_extensions: list[str] = Field(default=[".tsv", ".txt", ".outfmt6"])


class SyntenyOutputConfig(BaseModel):
    """容器产物的输出文件约定（tasks.py 解析 output/synteny.json）。"""

    model_config = ConfigDict(extra="ignore")

    block_table: str = Field(default="synteny_blocks.tsv")
    pair_table: str = Field(default="synteny_pairs.json")


class SyntenyVisualizationConfig(BaseModel):
    """dot plot 前端渲染边界。"""

    model_config = ConfigDict(extra="ignore")

    scattergl_point_limit: int = Field(default=50_000, ge=1_000)
    require_chromosome_filter_above_limit: bool = Field(default=True)


class SyntenyConfig(BaseModel):
    """根配置模型。"""

    model_config = ConfigDict(extra="ignore")

    input: SyntenyInputConfig = Field(default_factory=SyntenyInputConfig)
    output: SyntenyOutputConfig = Field(default_factory=SyntenyOutputConfig)
    visualization: SyntenyVisualizationConfig = Field(default_factory=SyntenyVisualizationConfig)


class SyntenyConfigManager:
    """配置管理器，支持 mtime 热重载。"""

    def __init__(self, config_path: str | Path | None = None) -> None:
        self.config_path = (
            str(config_path) if config_path else get_settings().synteny_config_yaml
        )
        self._config: SyntenyConfig | None = None
        self._mtime: float = 0.0

    def _load_yaml(self) -> dict[str, Any]:
        """读盘；文件不存在 / 解析失败时返回空 dict（由默认值兜底）。"""
        path = Path(self.config_path)
        if not path.exists():
            return {}
        try:
            with path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except (yaml.YAMLError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    def get_config(self) -> SyntenyConfig:
        """获取配置，自动检测文件变更并热重载；文件缺失返回默认配置。"""
        path = Path(self.config_path)
        if not path.exists():
            self._config = SyntenyConfig()
            return self._config

        try:
            current_mtime = path.stat().st_mtime
        except OSError:
            return self._config or SyntenyConfig()

        if self._config is None or current_mtime > self._mtime:
            raw = self._load_yaml()
            try:
                self._config = SyntenyConfig(**raw)
            except Exception:
                # 字段不合法时回退默认，避免拖垮整个 API
                self._config = SyntenyConfig()
            self._mtime = current_mtime

        return self._config

    def reload(self) -> SyntenyConfig:
        """强制重载配置。"""
        self._config = None
        return self.get_config()


# 全局单例
config_manager = SyntenyConfigManager()


def get_synteny_config() -> SyntenyConfig:
    """快捷函数；service/tasks 直接调用。"""
    return config_manager.get_config()

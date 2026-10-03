"""GSEA 富集分析工具外置 YAML 配置加载器。

配置文件路径由 settings.gsea_config_yaml 决定（默认 tool_configs/gsea/gsea_config.yaml）。

热重载策略（与 deg/enrichments/jbrowse 一致）：
- GseaConfigManager 单例缓存解析后的 GseaConfig，按文件 mtime 判定是否重解析；
- 文件不存在 / 解析失败 / 字段缺失时回退内置默认配置，绝不抛异常；
- 改文件后由加载器 mtime 自动热重载，无需重启。

物种与运行时镜像复用 enrichments 的资源声明（tool_configs/gsea/resources.yaml
指向 species_config 与 cygnusx-r-enrichment:v1），本文件只管 GSEA 自身的
输入契约、计算默认值与输出列。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from cygnusx.core.config import get_settings


class GseaInputConfig(BaseModel):
    """排序基因列表的输入契约。"""

    model_config = ConfigDict(extra="ignore")

    supported_extensions: list[str] = Field(default=[".csv", ".tsv"])
    required_columns: list[str] = Field(default=["gene_id", "score"])
    min_genes: int = Field(default=10, ge=1)


class GseaAnalysisConfig(BaseModel):
    """计算默认值；页面/Agent 未显式传参时生效。"""

    model_config = ConfigDict(extra="ignore")

    gene_sets: list[str] = Field(
        default=["GO_BP", "GO_MF", "GO_CC", "KEGG"],
        description="单任务可选的 gene-set 来源枚举",
    )
    default_p_value_cutoff: float = Field(default=0.05, gt=0, le=1)
    default_q_value_cutoff: float = Field(default=0.1, gt=0, le=1)


class GseaOutputConfig(BaseModel):
    """容器产物的输出列与曲线文件约定（前端结果表按此渲染）。"""

    model_config = ConfigDict(extra="ignore")

    result_columns: list[str] = Field(
        default=["ID", "Description", "NES", "pvalue", "p.adjust", "qvalue", "setSize", "leading_edge_count"]
    )
    curve_file: str = Field(default="running_scores.json")


class GseaConfig(BaseModel):
    """根配置模型。"""

    model_config = ConfigDict(extra="ignore")

    input: GseaInputConfig = Field(default_factory=GseaInputConfig)
    analysis: GseaAnalysisConfig = Field(default_factory=GseaAnalysisConfig)
    output: GseaOutputConfig = Field(default_factory=GseaOutputConfig)


class GseaConfigManager:
    """配置管理器，支持 mtime 热重载。"""

    def __init__(self, config_path: str | Path | None = None) -> None:
        self.config_path = (
            str(config_path) if config_path else get_settings().gsea_config_yaml
        )
        self._config: GseaConfig | None = None
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

    def get_config(self) -> GseaConfig:
        """获取配置，自动检测文件变更并热重载；文件缺失返回默认配置。"""
        path = Path(self.config_path)
        if not path.exists():
            self._config = GseaConfig()
            return self._config

        try:
            current_mtime = path.stat().st_mtime
        except OSError:
            return self._config or GseaConfig()

        if self._config is None or current_mtime > self._mtime:
            raw = self._load_yaml()
            try:
                self._config = GseaConfig(**raw)
            except Exception:
                # 字段不合法时回退默认，避免拖垮整个 API
                self._config = GseaConfig()
            self._mtime = current_mtime

        return self._config

    def reload(self) -> GseaConfig:
        """强制重载配置。"""
        self._config = None
        return self.get_config()


# 全局单例
config_manager = GseaConfigManager()


def get_gsea_config() -> GseaConfig:
    """快捷函数；service/tasks 直接调用。"""
    return config_manager.get_config()

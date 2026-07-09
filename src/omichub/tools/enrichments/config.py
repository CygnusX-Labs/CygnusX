"""富集分析物种外置 YAML 配置加载器。

配置文件路径由 settings.enrichment_config_yaml 决定（默认
tool_configs/enrichments/species_config.yaml，仓库内源码管控，仿 flows/）。

热重载策略（与 jbrowse_config 一致）：
- EnrichmentConfigManager 单例缓存解析后的 EnrichmentConfig，按文件 mtime 判定是否重解析；
- 文件不存在 / 解析失败 / 字段缺失时回退到内置默认空配置，绝不抛异常
 （前端物种下拉降级为空，不影响平台其它功能）；
- 改文件后由加载器 mtime 自动热重载，无需重启。

前向兼容字段 kegg_rdata / kegg_supported 当前不在 DTO 暴露，留给后续
「离线 fallback」「物种 KEGG 可用性灰度」迭代启用（见方案文档建议 1/4）。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from omichub.core.config import get_settings


class SpeciesConfig(BaseModel):
    """单个物种的富集分析配置。"""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(..., description="物种唯一标识，前端下拉 value")
    display_name: str = Field(..., description="展示名称；DTO 序列化为 label")
    enabled: bool = Field(default=True, description="是否在前端下拉可见")
    kegg_code: str = Field(..., description="KEGG API 物种三字码，如 hsa / ath")
    org_db: str = Field(..., description="R OrgDb 包名，如 org.Hs.eg.db")
    id_type: str = Field(..., description="基因 ID 类型，如 SYMBOL / TAIR")
    # 前向兼容：离线 KEGG.RData 路径（在线失败时 enricher fallback 用）
    kegg_rdata: str | None = Field(default=None, description="离线 KEGG 数据路径（预留）")
    # 前向兼容：物种是否被 KEGG 注释覆盖（前端灰度用）
    kegg_supported: bool = Field(default=True, description="该物种是否支持 KEGG 注释")


class EnrichmentConfig(BaseModel):
    """根配置模型。"""

    model_config = ConfigDict(extra="ignore")

    species_list: list[SpeciesConfig] = Field(default_factory=list)


class EnrichmentConfigManager:
    """配置管理器，支持 mtime 热重载。"""

    def __init__(self, config_path: str | Path | None = None) -> None:
        self.config_path = (
            str(config_path) if config_path else get_settings().enrichment_config_yaml
        )
        self._config: EnrichmentConfig | None = None
        self._mtime: float = 0.0

    def _load_yaml(self) -> dict[str, Any]:
        """读盘；文件不存在 / 解析失败时返回空 dict（由降级逻辑兜底）。"""
        path = Path(self.config_path)
        if not path.exists():
            return {}
        try:
            with path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except (yaml.YAMLError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    def get_config(self) -> EnrichmentConfig:
        """获取配置，自动检测文件变更并热重载；文件缺失返回默认空配置。"""
        path = Path(self.config_path)
        if not path.exists():
            self._config = EnrichmentConfig()
            return self._config

        try:
            current_mtime = path.stat().st_mtime
        except OSError:
            return self._config or EnrichmentConfig()

        if self._config is None or current_mtime > self._mtime:
            raw = self._load_yaml()
            try:
                self._config = EnrichmentConfig(**raw)
            except Exception:
                # 字段不合法时回退默认，避免拖垮整个 API
                self._config = EnrichmentConfig()
            self._mtime = current_mtime

        return self._config

    def reload(self) -> EnrichmentConfig:
        """强制重载配置。"""
        self._config = None
        return self.get_config()

    def list_enabled_species(self) -> list[SpeciesConfig]:
        """返回 enabled=True 的物种列表（顺序同 YAML）。"""
        return [s for s in self.get_config().species_list if s.enabled]

    def get_species(self, species_id: str) -> SpeciesConfig | None:
        """根据 id 取物种配置（含 enabled=False，供内部诊断）。"""
        for s in self.get_config().species_list:
            if s.id == species_id:
                return s
        return None


# 全局单例
config_manager = EnrichmentConfigManager()


@lru_cache
def _enrichment_data_root() -> Path:
    """富集分析数据根目录（宿主侧，挂载进容器的源路径）。"""
    return Path(get_settings().enrichment_data_mount)


def get_enrichment_config() -> EnrichmentConfig:
    """FastAPI 依赖用快捷函数。"""
    return config_manager.get_config()

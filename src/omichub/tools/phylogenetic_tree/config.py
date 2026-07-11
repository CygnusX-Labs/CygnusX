"""系统发育树工具外置 YAML 配置加载器。

配置文件：
- tool_configs/phylogenetic-tree/config.yaml   工具能力/资源/输出/支持的方法矩阵
- tool_configs/phylogenetic-tree/defaults.yaml 默认参数预设

热重载策略：
- 按文件 mtime 判定是否重新解析；
- 文件不存在/解析失败时回退到内置默认配置，不阻塞 API。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from omichub.core.config import get_settings


class InputLimits(BaseModel):
    model_config = ConfigDict(extra="ignore")

    max_file_size_mb: int = 50
    max_sequences: int = 5000
    max_sequence_length: int = 50000


class ToolBinary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    binary: str = ""
    version: str = ""


class OutputFormat(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str
    ext: str
    mime: str


class PhyloConfig(BaseModel):
    """系统发育树工具完整配置。"""

    model_config = ConfigDict(extra="ignore")

    meta: dict[str, Any] = Field(default_factory=dict)
    features: dict[str, bool] = Field(default_factory=dict)
    input_limits: InputLimits = Field(default_factory=InputLimits)
    execution: dict[str, Any] = Field(default_factory=dict)
    tools: dict[str, ToolBinary] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    supported_methods: dict[str, Any] = Field(default_factory=dict)

    def binary_path(self, tool_name: str) -> str | None:
        """返回工具二进制名（优先配置中的 binary，否则回退工具名本身）。"""
        cfg = self.tools.get(tool_name)
        return cfg.binary if cfg else tool_name


class PhyloDefaults(BaseModel):
    """默认参数预设。"""

    model_config = ConfigDict(extra="ignore")

    defaults: dict[str, dict[str, Any]] = Field(default_factory=dict)


class PhyloConfigManager:
    """配置管理器，支持 mtime 热重载。"""

    def __init__(
        self,
        config_path: str | Path | None = None,
        defaults_path: str | Path | None = None,
    ) -> None:
        settings = get_settings()
        self.config_path = (
            str(config_path) if config_path else settings.phylogenetic_tree_config_yaml
        )
        self.defaults_path = (
            str(defaults_path) if defaults_path else settings.phylogenetic_tree_defaults_yaml
        )
        self._config: PhyloConfig | None = None
        self._defaults: PhyloDefaults | None = None
        self._config_mtime: float = 0.0
        self._defaults_mtime: float = 0.0

    @staticmethod
    def _load_yaml(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            with path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except (yaml.YAMLError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    def _maybe_reload(self) -> None:
        config_path = Path(self.config_path)
        defaults_path = Path(self.defaults_path)

        try:
            config_mtime = config_path.stat().st_mtime if config_path.exists() else 0.0
        except OSError:
            config_mtime = 0.0
        try:
            defaults_mtime = defaults_path.stat().st_mtime if defaults_path.exists() else 0.0
        except OSError:
            defaults_mtime = 0.0

        if self._config is None or config_mtime > self._config_mtime:
            raw = self._load_yaml(config_path)
            try:
                self._config = PhyloConfig(**raw)
            except Exception:
                self._config = PhyloConfig()
            self._config_mtime = config_mtime

        if self._defaults is None or defaults_mtime > self._defaults_mtime:
            raw = self._load_yaml(defaults_path)
            try:
                self._defaults = PhyloDefaults(**raw)
            except Exception:
                self._defaults = PhyloDefaults()
            self._defaults_mtime = defaults_mtime

    def get_config(self) -> PhyloConfig:
        self._maybe_reload()
        return self._config or PhyloConfig()

    def get_defaults(self) -> PhyloDefaults:
        self._maybe_reload()
        return self._defaults or PhyloDefaults()


# 全局单例
config_manager = PhyloConfigManager()

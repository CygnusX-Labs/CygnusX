"""统一下载器 YAML 配置加载器。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from cygnusx.core.config import Settings, get_settings
from cygnusx.core.exceptions import ValidationError
from cygnusx.domain.download_contract import DIRECT_SCHEMES


class DownloadFeaturesConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ebi: bool = False
    cloud_storage: bool = False
    direct_link: bool = False


class DownloadBinariesConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # 二进制路径；空值时由 storage_path 派生，显式配置（download_config.yaml）
    # 优先——换根部署只改 .env 的 STORAGE_PATH 即可。
    ebi: str = ""
    ebi_config: str = ""
    aria2c: str = "/usr/bin/aria2c"
    ossutil: str = ""
    tosutil: str = ""
    obsutil: str = ""

    @model_validator(mode="after")
    def _derive_binaries(self) -> DownloadBinariesConfig:
        if not self.ebi:
            self.ebi = f"{get_settings().storage_path}/bin/EBIDownload"
        if not self.ebi_config:
            self.ebi_config = f"{get_settings().storage_path}/bin/EBIDownload.yaml"
        if not self.ossutil:
            self.ossutil = f"{get_settings().storage_path}/bin/ossutil"
        if not self.tosutil:
            self.tosutil = f"{get_settings().storage_path}/bin/tosutil"
        if not self.obsutil:
            self.obsutil = f"{get_settings().storage_path}/bin/obsutil"
        return self


class Aria2Config(BaseModel):
    model_config = ConfigDict(extra="ignore")

    default_threads: int = Field(default=4, ge=1, le=16)
    max_threads: int = Field(default=16, ge=1, le=64)
    max_concurrent_downloads: int = Field(default=4, ge=1, le=64)
    max_tries: int = Field(default=5, ge=1, le=20)
    retry_wait: int = Field(default=5, ge=0, le=300)
    connect_timeout: int = Field(default=30, ge=1, le=600)
    timeout: int = Field(default=60, ge=1, le=3600)
    file_allocation: str = "none"
    check_integrity: bool = True
    ftp_reuse_connection: bool = True


class DownloadValidationConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # Post-transfer registration bounds; these do not replace Worker transfer budgets.
    max_registration_entries: int = Field(default=20000, ge=1)
    max_registration_files: int = Field(default=10000, ge=1)
    max_registration_bytes: int = Field(default=1024**4, ge=1)
    max_links_per_task: int = Field(default=100, ge=1, le=1000)
    allowed_schemes: list[str] = Field(default_factory=lambda: sorted(DIRECT_SCHEMES))

    @model_validator(mode="after")
    def supported_protocol_subset(self) -> DownloadValidationConfig:
        if not set(self.allowed_schemes) <= DIRECT_SCHEMES:
            raise ValueError("allowed_schemes只能收紧已实现的http/https/ftp协议")
        return self


class DownloadConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    features: DownloadFeaturesConfig = Field(default_factory=DownloadFeaturesConfig)
    binaries: DownloadBinariesConfig = Field(default_factory=DownloadBinariesConfig)
    aria2: Aria2Config = Field(default_factory=Aria2Config)
    validation: DownloadValidationConfig = Field(default_factory=DownloadValidationConfig)


class DownloadConfigManager:
    """按文件 mtime 缓存配置，解析失败时保留上一份有效配置。"""

    def __init__(self, config_path: str | Path | None = None) -> None:
        self.config_path = str(config_path) if config_path else get_settings().download_config_yaml
        self._config: DownloadConfig | None = None
        self._mtime = 0.0

    def get_config(self) -> DownloadConfig:
        path = Path(self.config_path)
        if not path.exists():
            return self._config or DownloadConfig()
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return self._config or DownloadConfig()
        if self._config is None or mtime > self._mtime:
            try:
                with path.open(encoding="utf-8") as stream:
                    raw = yaml.safe_load(stream) or {}
                self._config = DownloadConfig.model_validate(raw)
                self._mtime = mtime
            except (OSError, yaml.YAMLError, ValueError):
                return self._config or DownloadConfig()
        return self._config

    def reload(self) -> DownloadConfig:
        self._config = None
        self._mtime = 0.0
        return self.get_config()


@lru_cache
def get_download_config_manager() -> DownloadConfigManager:
    return DownloadConfigManager()


def get_download_config() -> DownloadConfig:
    return get_download_config_manager().get_config()


def ensure_download_available(
    source: str, link_count: int, config: DownloadConfig, settings: Settings
) -> None:
    """One effective switch policy for REST, Service and the queued Worker (YAML OR env)."""
    enabled = {
        "sra": config.features.ebi or settings.enable_ebi_download,
        "direct_link": config.features.direct_link or settings.enable_direct_download,
        "cloud_storage": config.features.cloud_storage or settings.enable_cloud_storage_download,
    }
    if source not in enabled:
        raise ValidationError("下载来源未实现", code="DOWNLOAD_SOURCE_UNSUPPORTED")
    if not enabled[source]:
        raise ValidationError("下载来源未启用", code="DOWNLOAD_SOURCE_DISABLED")
    if source == "direct_link" and link_count > config.validation.max_links_per_task:
        raise ValidationError("下载链接数量超过服务端限制", code="DOWNLOAD_LINK_LIMIT")

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
    # 优先于各 Settings 二进制变量，其次才从 storage_path 派生。
    ebi: str = ""
    ebi_config: str = ""
    aria2c: str = ""
    ossutil: str = ""
    tosutil: str = ""
    obsutil: str = ""

    @model_validator(mode="after")
    def _derive_binaries(self) -> DownloadBinariesConfig:
        settings = get_settings()
        if not self.ebi:
            self.ebi = settings.ebi_download_binary or f"{settings.storage_path}/bin/EBIDownload"
        if not self.ebi_config:
            self.ebi_config = (
                settings.ebi_download_yaml or f"{settings.storage_path}/bin/EBIDownload.yaml"
            )
        if not self.aria2c:
            self.aria2c = settings.direct_download_binary or "/usr/bin/aria2c"
        if not self.ossutil:
            self.ossutil = settings.cloud_ossutil_binary or f"{settings.storage_path}/bin/ossutil"
        if not self.tosutil:
            self.tosutil = settings.cloud_tosutil_binary or f"{settings.storage_path}/bin/tosutil"
        if not self.obsutil:
            self.obsutil = settings.cloud_obsutil_binary or f"{settings.storage_path}/bin/obsutil"
        for value in self.model_dump().values():
            if not Path(value).is_absolute() or any(
                c in value for c in ("://", "?", "#", "\n", "\r")
            ):
                raise ValueError("下载二进制和配置路径必须是绝对文件路径")
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
    max_ftp_depth: int = Field(default=8, ge=0, le=32)
    max_ftp_files: int = Field(default=1000, ge=1, le=10000)
    ftp_timeout_seconds: int = Field(default=30, ge=1, le=120)
    max_links_per_task: int = Field(default=100, ge=1, le=1000)
    allowed_schemes: list[str] = Field(default_factory=lambda: sorted(DIRECT_SCHEMES))

    @model_validator(mode="after")
    def supported_protocol_subset(self) -> DownloadValidationConfig:
        if not set(self.allowed_schemes) <= DIRECT_SCHEMES:
            raise ValueError("allowed_schemes只能收紧已实现的http/https/ftp协议")
        return self


class DownloadReliabilityConfig(BaseModel):
    max_request_keys: int = Field(default=64, ge=1, le=1024)


class DownloadConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    features: DownloadFeaturesConfig = Field(default_factory=DownloadFeaturesConfig)
    binaries: DownloadBinariesConfig = Field(default_factory=DownloadBinariesConfig)
    aria2: Aria2Config = Field(default_factory=Aria2Config)
    validation: DownloadValidationConfig = Field(default_factory=DownloadValidationConfig)
    reliability: DownloadReliabilityConfig = Field(default_factory=DownloadReliabilityConfig)


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


def describe_download_capabilities() -> dict[str, object]:
    """Same safe capability document for REST and all Gateway callers; no CLI probe."""
    from cygnusx.application.schemas.download_capability import (
        DownloadCapabilities,
        DownloadMethodParameter,
        DownloadSourceCapability,
    )
    from cygnusx.domain.download_contract import SRA_METHODS
    from cygnusx.infrastructure.download.policy import describe_transport_admission

    config, settings = get_download_config(), get_settings()
    limitation = (
        "final_dns_redirect_egress_not_runtime_accepted",
        "transfer_time_hard_budget_not_runtime_accepted",
        "binary_version_not_verified_on_worker",
    )
    sources = (
        DownloadSourceCapability(
            source_type="sra",
            supported_methods=tuple(sorted(SRA_METHODS)),
            method_parameters=(
                DownloadMethodParameter(name="multithreads", minimum=1, maximum=32),
                DownloadMethodParameter(name="aws_threads", minimum=1, maximum=64),
            ),
            input_accession_types=(
                "SRR",
                "ERR",
                "DRR",
                "SRP",
                "ERP",
                "DRP",
                "PRJNA",
                "PRJEB",
                "PRJDB",
            ),
            protocols=("https", "ftp"),
            binary_name=Path(config.binaries.ebi).name,
            enabled_by_configuration=config.features.ebi or settings.enable_ebi_download,
            limitations=(
                *limitation,
                "GSE/GSM require metadata resolution",
                "Dataset raw import selects resolved SRR only",
            ),
        ),
        DownloadSourceCapability(
            source_type="direct_link",
            supported_methods=tuple(sorted(config.validation.allowed_schemes)),
            protocols=tuple(sorted(config.validation.allowed_schemes)),
            method_parameters=(
                DownloadMethodParameter(
                    name="download_threads", minimum=1, maximum=config.aria2.max_threads
                ),
            ),
            binary_name="aria2c",
            enabled_by_configuration=config.features.direct_link or settings.enable_direct_download,
            limitations=(*limitation, "GEO supplementary requires authoritative source selection"),
        ),
        DownloadSourceCapability(
            source_type="cloud_storage",
            supported_methods=("aliyun", "volc", "huawei"),
            protocols=("oss", "tos", "obs"),
            binary_name="ossutil/tosutil/obsutil",
            enabled_by_configuration=config.features.cloud_storage
            or settings.enable_cloud_storage_download,
            limitations=limitation,
        ),
        DownloadSourceCapability(
            source_type="existing_project_file",
            supported_methods=("attach_file_record",),
            limitations=(
                "authorized FileRecord only; no transport",
                "Dataset validation and human review remain required",
            ),
        ),
    )
    metadata_enabled = settings.dataset_discovery_readonly
    entries: list[DownloadSourceCapability] = []
    for name, protocol, source_index in (
        ("ncbi_sra", "sra.aws", 0),
        ("ena_fastq", "sra.ftp", 0),
        ("geo_supplementary", "https", 1),
        ("http_direct_link", "http", 1),
        ("https_direct_link", "https", 1),
        ("ftp", "ftp", 1),
        ("oss", "oss", 2),
        ("tos", "tos", 2),
        ("obs", "obs", 2),
    ):
        source = sources[source_index]
        reasons = describe_transport_admission(protocol, "agent").reason_codes
        enabled = source.enabled_by_configuration
        if source_index == 1:
            enabled = enabled and protocol in config.validation.allowed_schemes
        if name == "geo_supplementary":
            enabled = enabled and metadata_enabled
        entries.append(
            DownloadSourceCapability(
                source_type=name,
                supported_methods=(protocol,),
                protocols=(protocol,),
                binary_name=source.binary_name,
                enabled_by_configuration=enabled,
                limitations=(
                    *source.limitations,
                    *reasons,
                    *(("DOWNLOAD_SOURCE_DISABLED",) if not enabled else ()),
                ),
                query_tools=("dataset.discover",)
                if name in {"ncbi_sra", "ena_fastq", "geo_supplementary"}
                else (),
            )
        )
    entries.insert(
        0,
        DownloadSourceCapability(
            source_type="geo_metadata",
            supported_methods=("geo_soft", "ena_filereport"),
            protocols=("https",),
            enabled_by_configuration=metadata_enabled,
            transport_required=False,
            required_scope="read:datasets",
            query_tools=("dataset.discover",),
            limitations=(
                "bounded_metadata_only_not_scientific_file_download",
                *(("DATASET_READ_DISABLED",) if not metadata_enabled else ()),
            ),
        ),
    )
    entries.extend(
        (
            DownloadSourceCapability(
                source_type="cloud_drive",
                supported_methods=(),
                code_available=False,
                verification_status="NOT_IMPLEMENTED",
                limitations=("PROTOCOL_UNSUPPORTED", "UI_PLACEHOLDER_ONLY"),
            ),
            DownloadSourceCapability(
                source_type="existing_dataset_assets",
                supported_methods=("file_record",),
                transport_required=False,
                enabled_by_configuration=metadata_enabled,
                required_scope="read:datasets",
                requires_project=True,
                query_tools=(
                    "dataset.list_project_assets",
                    "dataset.inspect",
                    "dataset.list_files",
                ),
                limitations=(
                    "owned_project_only",
                    "scientific_review_is_independent",
                    *(("DATASET_READ_DISABLED",) if not metadata_enabled else ()),
                ),
            ),
        )
    )
    return DownloadCapabilities(
        sources=sources,
        capabilities=tuple(entries),
        limits={
            "max_links": config.validation.max_links_per_task,
            "max_ftp_depth": config.validation.max_ftp_depth,
            "max_ftp_files": config.validation.max_ftp_files,
            "ftp_timeout_seconds": config.validation.ftp_timeout_seconds,
            "registration_max_files": config.validation.max_registration_files,
            "registration_max_bytes": config.validation.max_registration_bytes,
            "transfer_max_bytes": None,
            "transfer_budget_enforced": False,
        },
    ).model_dump(mode="json")

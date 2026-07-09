"""数据下载相关 DTO"""

import ipaddress
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, model_validator

from omichub.application.schemas.base import OmicsHubBaseSchema

DownloadSource = Literal["sra", "cloud_storage"]
CloudStorageProvider = Literal["aliyun", "volc", "volcengine", "huawei", "huaweicloud"]

# 各云商对象存储允许的 endpoint 后缀（大小写不敏感）
_CLOUD_ALLOWED_HOST_SUFFIXES = {
    "aliyun": [".aliyuncs.com"],
    "volc": [".volces.com"],
    "huawei": [".myhuaweicloud.com"],
}


def _validate_cloud_host(provider: str, object_uri: str) -> None:
    """校验云存储对象 URI 的主机名，防止 SSRF。

    - 禁止直接使用 IP 地址（含 metadata 地址）。
    - 裸 bucket 名（如 `oss://bucket/path`）保留兼容性，允许通过。
    - 显式 endpoint 必须匹配对应云商域名后缀。
    """
    parsed = urlparse(object_uri)
    host = parsed.hostname
    if not host:
        raise ValueError("对象 URI 缺少主机名")
    # 禁止直接使用 IP 地址
    try:
        ipaddress.ip_address(host)
        raise ValueError("对象 URI 禁止直接使用 IP 地址")
    except ValueError:
        pass
    # 裸 bucket（无点号）是 ossutil 等工具的合法简写，予以保留
    if "." not in host:
        return
    allowed_suffixes = _CLOUD_ALLOWED_HOST_SUFFIXES.get(provider, [])
    host_lower = host.lower()
    if not any(host_lower.endswith(suffix.lower()) for suffix in allowed_suffixes):
        raise ValueError(f"{provider} 对象 URI 主机名不合法: {host}")


class DownloadRequest(OmicsHubBaseSchema):
    """数据下载请求

    source="sra" 走 EBIDownload；source="cloud_storage" 走云商对象存储 CLI
    （ossutil / tosutil / obsutil）。两类任务都复用通用 Task 聚合根。
    """

    source: DownloadSource = Field(default="sra", description="下载来源：sra 或 cloud_storage")

    # 公共数据库 / SRA 下载参数
    accession: str = Field(default="", description="EBI/NCBI 登录号，如 PRJNA1251654 或 SRRxxxxxx")
    download_method: Literal["aws", "aspera", "ftp"] = Field(default="aws", description="下载方式")
    multithreads: int = Field(default=4, ge=1, le=32, description="并发下载数")
    aws_threads: int = Field(default=8, ge=1, le=64, description="单文件 AWS 并发线程数")

    # 云存储下载参数
    cloud_provider: CloudStorageProvider | None = Field(default=None, description="云存储提供商")
    object_uri: str = Field(default="", description="对象 URI，如 oss://bucket/path")
    recursive: bool = Field(default=True, description="云存储目录是否递归下载")

    # 下载目标目录（相对 users/{uid}/raw_data/ 的子路径，空串=根；不存在则自动创建）
    target_directory: str = Field(
        default="", max_length=500, description="下载到用户目录下的指定子目录"
    )
    dry_run: bool = Field(
        default=False, description="模拟下载，不实际下载文件（测试用，仅 SRA 下载支持）"
    )

    @model_validator(mode="after")
    def validate_source_payload(self) -> "DownloadRequest":
        if self.source == "sra":
            if not self.accession or not self.accession.strip():
                raise ValueError("登录号 (accession) 不能为空")
            return self

        provider = self.cloud_provider
        object_uri = (self.object_uri or "").strip()
        if provider is None:
            raise ValueError("云存储提供商不能为空")
        if not object_uri:
            raise ValueError("对象 URI 不能为空")

        normalized_provider = {
            "volcengine": "volc",
            "huaweicloud": "huawei",
        }.get(provider, provider)
        expected_scheme = {
            "aliyun": "oss://",
            "volc": "tos://",
            "huawei": "obs://",
        }[normalized_provider]
        if not object_uri.startswith(expected_scheme):
            raise ValueError(f"{provider} 对象 URI 必须以 {expected_scheme} 开头")
        _validate_cloud_host(normalized_provider, object_uri)
        return self

"""Declared platform transport support, independent of deployment or Agent authorization."""

from __future__ import annotations

import re
from collections.abc import Collection, Sequence
from typing import Literal
from urllib.parse import urlsplit

from cygnusx.core.exceptions import ValidationError

DownloadSource = Literal["sra", "cloud_storage", "direct_link"]
SraDownloadMethod = Literal["aws", "ftp"]
DOWNLOAD_SOURCES = frozenset({"sra", "cloud_storage", "direct_link"})
SRA_METHODS = frozenset({"aws", "ftp"})
DIRECT_SCHEMES = frozenset({"http", "https", "ftp"})
CLOUD_SCHEMES = {"aliyun": "oss", "volc": "tos", "huawei": "obs"}
CLOUD_ALIASES = {"volcengine": "volc", "huaweicloud": "huawei"}
ENA_ACCESSION = re.compile(r"^(?:[SED]R[PRXS]|PRJ(?:NA|EB|DB))\d+$")


def validate_transport(
    source: str,
    *,
    method: str = "aws",
    accession: str = "",
    links: Sequence[str] = (),
    cloud_provider: str = "",
    object_uri: str = "",
    allowed_schemes: Collection[str] = DIRECT_SCHEMES,
) -> None:
    """Reject unsupported selections. This is not URL/DNS/egress or runtime attestation."""
    if source not in DOWNLOAD_SOURCES:
        raise ValidationError("该下载来源尚未接入", code="DOWNLOAD_SOURCE_UNSUPPORTED")
    if method not in SRA_METHODS:
        raise ValidationError("平台下载方式仅支持 aws/ftp", code="DOWNLOAD_METHOD_UNSUPPORTED")
    if source == "sra":
        if accession.upper().startswith(("GSE", "GSM", "GPL")):
            raise ValidationError(
                "GEO 登录号需先解析为权威 Run 或附件", code="DOWNLOAD_METADATA_RESOLUTION_REQUIRED"
            )
        if accession and not ENA_ACCESSION.fullmatch(accession):
            raise ValidationError(
                "请提交单个 ENA/SRA 登录号", code="DOWNLOAD_ACCESSION_UNSUPPORTED"
            )
    elif source == "direct_link":
        for link in links:
            scheme = urlsplit(link.strip()).scheme.lower()
            if scheme not in DIRECT_SCHEMES:
                raise ValidationError("该直链协议未实现", code="DOWNLOAD_PROTOCOL_UNSUPPORTED")
            if scheme not in allowed_schemes:
                raise ValidationError("该直链协议已被配置禁用", code="DOWNLOAD_PROTOCOL_DISABLED")
    else:
        provider = CLOUD_ALIASES.get(cloud_provider, cloud_provider)
        if provider not in CLOUD_SCHEMES:
            raise ValidationError("该云存储提供商未实现", code="DOWNLOAD_PROVIDER_UNSUPPORTED")
        if urlsplit(object_uri).scheme != CLOUD_SCHEMES[provider]:
            raise ValidationError("云存储 URI 与提供商不一致", code="DOWNLOAD_PROTOCOL_UNSUPPORTED")

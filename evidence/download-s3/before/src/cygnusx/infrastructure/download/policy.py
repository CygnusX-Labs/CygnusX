"""Fail-closed execution admission for existing external download programs.

No CLI here proves pinned DNS, redirect/egress policy or transfer-time quota limits.
Only a separately accepted runtime change can replace this source-level gate.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from typing import Final
from urllib.parse import urlsplit

from cygnusx.core.exceptions import ValidationError
from cygnusx.domain.download_security import public_host, validate_download_url

DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED: Final = False


def require_download_runtime(source: str) -> None:
    if not DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED:
        raise ValidationError(
            "下载最终目的地与传输硬预算尚未通过运行验收",
            code="DOWNLOAD_TRANSPORT_UNVERIFIED",
        )


def verify_resolved_addresses(host: str, addresses: Iterable[str]) -> tuple[str, ...]:
    """Validate an observation; this does NOT pin a CLI connection or enable execution."""
    public_host(host)
    observed = tuple(
        sorted({public_host(str(ipaddress.ip_address(address))) for address in addresses})
    )
    if not observed:
        raise ValueError("DNS 未返回可信公网地址")
    return observed


def verify_redirect(original: str, target: str) -> None:
    """Until redirect/connection enforcement is accepted, no redirect is authorized."""
    validate_download_url(original)
    validate_download_url(target)
    if urlsplit(original) != urlsplit(target):
        raise ValueError("下载重定向未获得运行认证")

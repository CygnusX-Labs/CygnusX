"""Download target syntax policy. Syntax checks are not a transport egress guarantee."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import unquote, urlsplit


def public_host(host: str, *, allow_ip: bool = True) -> str:
    """Reject noncanonical/special hosts, including mapped IPv6 and legacy IPv4 notation."""
    if not host or "%" in host or "\\" in host or any(ord(c) <= 32 for c in host):
        raise ValueError("下载主机名非法")
    host = host.rstrip(".").lower()
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None:
        mapped = getattr(address, "ipv4_mapped", None)
        if (
            not allow_ip
            or not address.is_global
            or address.is_multicast
            or address.is_reserved
            or (mapped is not None and not mapped.is_global)
        ):
            raise ValueError("下载主机禁止使用非公网或未经许可的 IP")
        return address.compressed
    if re.fullmatch(r"(?:0x[0-9a-f]+|[0-9]+)(?:\.(?:0x[0-9a-f]+|[0-9]+))*", host):
        raise ValueError("下载主机禁止非标准 IP 表示")
    host = host.encode("idna").decode("ascii")
    if (
        host in {"localhost", "localhost.localdomain", "metadata.google.internal"}
        or host.endswith((".localhost", ".local", ".internal"))
        or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host)
        or ".." in host
    ):
        raise ValueError("下载主机不允许本地名称或非法标签")
    return host


def validate_download_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme.lower() not in {"http", "https", "ftp"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or "\\" in value
        or any(ord(c) <= 32 for c in value)
    ):
        raise ValueError("下载链接必须为不带凭据的 HTTP/HTTPS/FTP 地址")
    public_host(parsed.hostname or "")
    if parsed.port not in {None, {"http": 80, "https": 443, "ftp": 21}[parsed.scheme.lower()]}:
        raise ValueError("下载链接不允许非标准端口")
    if unquote(parsed.netloc) != parsed.netloc:
        raise ValueError("下载链接主机不允许编码别名")
    return value

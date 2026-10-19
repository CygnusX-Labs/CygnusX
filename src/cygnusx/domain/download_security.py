"""Download target syntax policy. Syntax checks are not a transport egress guarantee."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import parse_qsl, unquote, urlsplit


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
        len(host) > 253
        or any(
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
            for label in host.split(".")
        )
        or re.fullmatch(r"(?:0x[0-9a-f]+|[0-9]+)(?:\.(?:0x[0-9a-f]+|[0-9]+))*", host)
    ):
        raise ValueError("下载主机标签或数字表示非法")
    if (
        host in {"localhost", "localhost.localdomain", "metadata.google.internal"}
        or host.endswith((".localhost", ".local", ".internal"))
        or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host)
        or ".." in host
    ):
        raise ValueError("下载主机不允许本地名称或非法标签")
    return host


def validate_download_url(value: str) -> str:
    if len(value) > 4096:
        raise ValueError("下载链接过长")
    parsed = urlsplit(value)
    host = public_host(parsed.hostname or "")
    if "." not in host and ":" not in host:
        raise ValueError("HTTP/FTP下载主机必须为公网IP或完整域名")
    if any(
        _SECRET_KEY.fullmatch(key)
        for key, _ in parse_qsl(parsed.query, keep_blank_values=True, max_num_fields=64)
    ):
        raise ValueError("签名或凭据链接需要尚未认证的安全凭据通道")
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


# URLs may carry credentials in either query or path. Logs keep neither.
_DOWNLOAD_URL = re.compile(r"\b(?:https?|ftps?|oss|tos|obs|s3|cos)://[^\s<>\"']+", re.IGNORECASE)
_SECRET_KEY = re.compile(
    r"^(?:token|access[-_]?token|refresh[-_]?token|api[-_]?key|access[-_]?key(?:[-_]?(?:id|secret))?|"
    r"secret|password|passwd|signature|sig|credential|authorization|cookie|"
    r"awsaccesskeyid|x[-_]amz[-_].+|x[-_]goog[-_].+|_*download[-_]execution[-_]binding)$",
    re.IGNORECASE,
)
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(token|access[-_]?token|refresh[-_]?token|api[-_]?key|access[-_]?key(?:[-_]?(?:id|secret))?|"
    r"secret|password|passwd|signature|credential|awsaccesskeyid)"
    r"([\"']?\s*[:=]\s*[\"']?)([^\s,;\"'&}]+)"
)
_AUTHORIZATION = re.compile(
    r"(?i)\b(?:proxy-)?authorization\s*[:=]\s*(?:bearer|basic)\s+[^\s,;\"']+"
)
_COOKIE = re.compile(r"(?i)\bcookie\s*[:=]\s*[^\r\n]+")


def redact_download_text(value: str) -> str:
    """Pure presentation filter; never returns original URL paths, queries or auth values."""
    value = value.replace(r"\/", "/")
    value = _DOWNLOAD_URL.sub("[download-url]", value)
    value = _AUTHORIZATION.sub("authorization=[redacted]", value)
    value = _COOKIE.sub("cookie=[redacted]", value)
    return _SECRET_ASSIGNMENT.sub(lambda m: m[1] + m[2] + "[redacted]", value)


def redact_download_parameters(value: object) -> object:
    """Redact a response copy; do not rewrite legacy stored execution parameters or hashes."""
    if isinstance(value, dict):
        return {
            key: "[redacted]"
            if _SECRET_KEY.fullmatch(str(key))
            else redact_download_parameters(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_download_parameters(item) for item in value]
    if isinstance(value, str):
        # Public, non-query source links remain useful in an owner's Task view.
        try:
            parsed = urlsplit(value)
            if parsed.scheme.lower() in {
                "http",
                "https",
                "ftp",
                "ftps",
                "oss",
                "tos",
                "obs",
                "s3",
                "cos",
            }:
                return redact_download_text(value) if parsed.query or parsed.username else value
        except ValueError:
            return "[redacted-download-value]"
        return redact_download_text(value)
    return value


def download_validation_errors(
    errors: list[dict[str, object]], fields: set[str]
) -> list[dict[str, object]]:
    """Remove attacker-controlled input/context/messages before API logging or rendering."""
    result: list[dict[str, object]] = []
    for error in errors:
        location = error.get("loc", ())
        safe_location = (
            [
                item
                if isinstance(item, int)
                or item == "body"
                or (isinstance(item, str) and item in fields)
                else "[field]"
                for item in location
            ]
            if isinstance(location, (list, tuple))
            else ["body"]
        )
        result.append(
            {
                "type": error.get("type", "value_error"),
                "loc": safe_location,
                "msg": "下载参数不符合安全或协议约束",
            }
        )
    return result


_DOWNLOAD_TOOL_NAMES = frozenset(
    {
        "platform_submit_download",
        "cygnusx_submit_download",
        "downloads.prepare",
        "downloads.submit",
    }
)


def is_download_tool_name(value: object) -> bool:
    """Known download labels for presentation filtering, never for authorization."""
    return isinstance(value, str) and value in _DOWNLOAD_TOOL_NAMES


def redact_download_tool_history(value: object, *, download_context: bool = False) -> object:
    """Copy known download tool envelopes for display; preserve stored hashes and execution data.

    This does not scrub free-form conversation text or authorize execution. Unknown tools
    keep their presentation contract; download envelopes are recognized structurally.
    """
    if isinstance(value, dict):
        scoped = download_context or any(
            is_download_tool_name(value.get(key)) for key in ("tool_name", "name", "capability_id")
        )
        return {
            key: "[redacted-path]"
            if scoped and key in {"work_dir", "target_directory", "binary", "result_path"}
            else "[redacted]"
            if scoped and _SECRET_KEY.fullmatch(str(key))
            else redact_download_tool_history(item, download_context=scoped)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [
            redact_download_tool_history(item, download_context=download_context) for item in value
        ]
    if download_context and isinstance(value, str):
        return redact_download_text(value)
    return value

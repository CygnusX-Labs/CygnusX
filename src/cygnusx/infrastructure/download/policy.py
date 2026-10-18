"""Fail-closed execution admission for existing external download programs.

No CLI here proves pinned DNS, redirect/egress policy or transfer-time quota limits.
Only a separately accepted runtime change can replace this source-level gate.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final
from urllib.parse import urlsplit

from cygnusx.core.exceptions import ValidationError
from cygnusx.domain.download_security import public_host, validate_download_url

DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED: Final = False


@dataclass(frozen=True)
class TransportAdmission:
    """Safe policy projection, never an identity credential or runtime attestation."""

    protocol: str
    caller_kind: str
    execute_allowed: bool
    reason_codes: tuple[str, ...]
    authorization_requirement: str


def describe_transport_admission(protocol: str, caller_kind: str) -> TransportAdmission:
    """Separate caller authorization from transport certification without enabling either.

    Arguments are descriptive labels only. Neither a model-provided caller label nor a
    future change of the global switch constitutes JWT/delegation/certification evidence.
    No accepted runtime certificate exists in this implementation.
    """
    supported = {"http", "https", "ftp", "sra.aws", "sra.ftp", "oss", "tos", "obs"}
    reasons = ["TRANSPORT_RUNTIME_UNVERIFIED" if protocol in supported else "PROTOCOL_UNSUPPORTED"]
    requirements = {
        "manual": "HUMAN_JWT_AND_MODULE_SCOPE",
        "agent": "TRUSTED_DELEGATION_SCOPE_AND_HUMAN_CONFIRMATION",
        "worker": "PERSISTED_TASK_OWNER_AND_APPROVED_ORIGIN",
    }
    if caller_kind not in requirements:
        reasons.append("CALLER_IDENTITY_UNVERIFIED")
    if not DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED:
        reasons.append("TRANSPORT_RELEASE_GATE_CLOSED")
    return TransportAdmission(
        protocol=protocol,
        caller_kind=caller_kind,
        execute_allowed=False,
        reason_codes=tuple(reasons),
        authorization_requirement=requirements.get(caller_kind, "TRUSTED_IDENTITY_REQUIRED"),
    )


def require_download_runtime(source: str) -> None:
    # A release switch is not a per-protocol runtime certificate. Keep every current
    # backend closed until trusted certification and identity consumption is implemented.
    protocols = {
        "sra": ("sra.aws", "sra.ftp"),
        "direct_link": ("http", "https", "ftp"),
        "cloud_storage": ("oss", "tos", "obs"),
    }.get(source, ())
    if not protocols or any(
        not describe_transport_admission(protocol, "worker").execute_allowed
        for protocol in protocols
    ):
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

"""S3 incremental boundaries; no network, queue, DB or actual downloader."""

from unittest.mock import AsyncMock

import pytest

from cygnusx.application.schemas.download import DownloadRequest
from cygnusx.application.services.download_service import DownloadService
from cygnusx.core.exceptions import ValidationError

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
@pytest.mark.parametrize("link", ["http://127.0.0.1/a", "https://example.org/a?token=CANARY"])
async def test_mutated_internal_request_is_rejected_before_runtime_gate(monkeypatch, link):
    from cygnusx.infrastructure.download import policy

    request = DownloadRequest(source="direct_link", links=["https://example.org/a"])
    request.links = [link]
    gate = AsyncMock()
    monkeypatch.setattr(policy, "require_download_runtime", gate)
    # The validation boundary must run before any service dependency can be used.
    service = object.__new__(DownloadService)
    with pytest.raises(ValidationError) as error:
        await service.submit("fixture-user", request)
    assert error.value.code == "DOWNLOAD_ARGUMENTS_INVALID"
    assert "CANARY" not in str(error.value)
    gate.assert_not_called()


@pytest.mark.parametrize("caller", ["manual", "agent", "worker", "unknown"])
@pytest.mark.parametrize(
    "protocol", ["http", "https", "ftp", "sra.aws", "sra.ftp", "oss", "tos", "obs", "ftps", "s3"]
)
def test_admission_is_protocol_and_caller_specific_but_never_self_certifies(caller, protocol):
    from cygnusx.infrastructure.download.policy import describe_transport_admission

    decision = describe_transport_admission(protocol, caller)
    assert decision.execute_allowed is False
    assert decision.protocol == protocol
    assert decision.caller_kind == caller
    assert decision.reason_codes
    assert (
        "TRANSPORT_RUNTIME_UNVERIFIED" in decision.reason_codes
        or "PROTOCOL_UNSUPPORTED" in decision.reason_codes
    )


@pytest.mark.parametrize("source", ["sra", "direct_link", "cloud_storage"])
def test_global_switch_alone_never_certifies_transport(monkeypatch, source):
    from cygnusx.infrastructure.download import policy

    monkeypatch.setattr(policy, "DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED", True)
    with pytest.raises(ValidationError) as error:
        policy.require_download_runtime(source)
    assert error.value.code == "DOWNLOAD_TRANSPORT_UNVERIFIED"

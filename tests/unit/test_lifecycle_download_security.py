"""RI02/RI03 offline boundaries. No external network or CLI is used."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError as SchemaError

from cygnusx.application.schemas.download import DownloadRequest
from cygnusx.application.services import download_service
from cygnusx.core.exceptions import ValidationError
from cygnusx.domain.download_security import public_host, validate_download_url
from cygnusx.infrastructure.download.policy import (
    require_download_runtime,
    verify_redirect,
    verify_resolved_addresses,
)
from cygnusx.tools.download.config import describe_download_capabilities

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "::1",
        "0.0.0.0",
        "::",
        "10.0.0.1",
        "169.254.169.254",
        "224.0.0.1",
        "ff02::1",
        "::ffff:127.0.0.1",
        "2130706433",
        "127.1",
        "0177.0.0.1",
        "0x7f000001",
        "localhost.",
        "a.local",
        "x.localhost",
        "host%2ecom",
    ],
)
def test_ri03_01_special_hosts(address):
    with pytest.raises(ValueError):
        public_host(address)


@pytest.mark.parametrize(
    "uri",
    [
        "oss://[::1]/x",
        "oss://user:secret@bucket/x",
        "oss://[::ffff:127.0.0.1]/x",
        "oss://127.0.0.1/x",
        "oss://bucket:88/x",
        "oss://localhost/x",
    ],
)
def test_ri03_02_cloud_uris(uri):
    with pytest.raises(SchemaError):
        DownloadRequest(source="cloud_storage", cloud_provider="aliyun", object_uri=uri)


@pytest.mark.parametrize(
    "url",
    [
        "https://a:b@ncbi.nlm.nih.gov/x",
        "https://%6cocalhost/x",
        "https://example.org:999/x",
        "https://example.org\\@127.0.0.1/x",
        "ftp://127.1/x",
    ],
)
def test_ri03_03_url_alias_credentials(url):
    with pytest.raises(ValueError):
        validate_download_url(url)


def test_ri03_04_dns_changes_require_public_observations():
    assert verify_resolved_addresses("www.ncbi.nlm.nih.gov", ["8.8.8.8"]) == ("8.8.8.8",)
    with pytest.raises(ValueError):
        verify_resolved_addresses("www.ncbi.nlm.nih.gov", ["8.8.8.8", "127.0.0.1"])
    with pytest.raises(ValueError):
        verify_resolved_addresses("www.ncbi.nlm.nih.gov", [])


@pytest.mark.parametrize(
    "target", ["http://www.ncbi.nlm.nih.gov/x", "https://cdn.example.org/x", "https://127.0.0.1/x"]
)
def test_ri03_05_redirects_never_authorize_unpinned_cli(target):
    with pytest.raises(ValueError):
        verify_redirect("https://www.ncbi.nlm.nih.gov/x", target)


@pytest.mark.parametrize("source", ["sra", "direct_link", "cloud_storage"])
def test_ri03_06_unaccepted_transports_stay_blocked(source):
    with pytest.raises(ValidationError) as error:
        require_download_runtime(source)
    assert error.value.code == "DOWNLOAD_TRANSPORT_UNVERIFIED"


@pytest.mark.asyncio
async def test_ri03_07_execution_block_precedes_directory_task_and_queue(monkeypatch):
    service = download_service.DownloadService(MagicMock(), backend=AsyncMock())
    service._make_work_dir = AsyncMock()
    service._domain = AsyncMock()
    monkeypatch.setattr(download_service, "ensure_download_available", lambda *args: None)
    with pytest.raises(ValidationError):
        await service.submit("unused", DownloadRequest(accession="SRR1"))
    service._make_work_dir.assert_not_called()
    service._domain.submit.assert_not_called()


@pytest.mark.parametrize("field", ["task_id", "owner_id", "project_id", "binary", "binary_args"])
def test_ri02_03_no_client_execution_identity(field):
    with pytest.raises(SchemaError):
        DownloadRequest(accession="SRR1", **{field: "forged"})


@pytest.mark.parametrize("method", ["aspera", "auto", "prefetch"])
def test_ri02_02_legacy_unsupported_is_never_remapped(method):
    with pytest.raises(SchemaError) as error:
        DownloadRequest(accession="SRR1", download_method=method)
    assert error.value.errors()[0]["type"] == "DOWNLOAD_METHOD_UNSUPPORTED"


def test_ri02_01_capability_contract_code_not_runtime():
    result = describe_download_capabilities()
    sources = {s["source_type"]: s for s in result["sources"]}
    assert set(sources) == {"sra", "direct_link", "cloud_storage", "existing_project_file"}
    assert sources["sra"]["supported_methods"] == ["aws", "ftp"]
    assert all(
        s["binary_version"] is None and s["runtime_readiness"] == "BLOCKED"
        for s in sources.values()
    )
    assert result["write_enabled"] is False
    assert result["limits"]["transfer_max_bytes"] is None
    assert result["limits"]["transfer_budget_enforced"] is False


@pytest.mark.asyncio
async def test_ri02_05_rest_uses_shared_contract():
    from cygnusx.api.v1.downloads import download_capabilities

    assert await download_capabilities("owner") == describe_download_capabilities()


@pytest.mark.parametrize("method", ["aws", "ftp"])
def test_ri02_04_declared_methods_accepted_in_schema(method):
    assert DownloadRequest(accession=" srr1 ", download_method=method).accession == "SRR1"


@pytest.mark.parametrize("case", ["depth", "files", "cycle", "timeout"])
def test_ri03_08_09_ftp_is_bounded_without_network(monkeypatch, case):
    from cygnusx.infrastructure.celery_app.tasks import download as worker
    from cygnusx.infrastructure.download import policy

    config = worker.get_download_config().model_copy(deep=True)
    config.validation.max_ftp_depth = 1
    config.validation.max_ftp_files = 2
    monkeypatch.setattr(worker, "get_download_config", lambda: config)
    monkeypatch.setattr(policy, "require_download_runtime", lambda source: None)

    class FakeFTP:
        current = "/"

        def __init__(self, *args, **kwargs):
            pass

        def login(self):
            pass

        def cwd(self, path):
            if path.rsplit("/", 1)[-1].startswith("file"):
                raise OSError("not a directory")
            self.current = "/" if case == "cycle" else path

        def pwd(self):
            return self.current

        def nlst(self):
            if case == "files":
                return ["file1", "file2", "file3"]
            return ["child"]

        def quit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(worker, "FTP", FakeFTP)
    if case == "timeout":
        clock = iter([0, 1000])
        from types import SimpleNamespace
        monkeypatch.setattr(worker, "time", SimpleNamespace(monotonic=lambda: next(clock, 1000)))
    with pytest.raises(ValidationError):
        worker._expand_ftp_directories(["ftp://ftp.ncbi.nlm.nih.gov/"], True)



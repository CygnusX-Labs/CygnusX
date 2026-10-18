"""Static/isolated transport contracts; no CLI, sockets or queue invocation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cygnusx.application.schemas.download import DownloadRequest

pytestmark = pytest.mark.unit


def test_aspera_is_rejected_instead_of_silently_mapped() -> None:
    with pytest.raises(ValidationError) as error:
        DownloadRequest(accession="SRR1", download_method="aspera")
    assert error.value.errors()[0]["type"] == "DOWNLOAD_METHOD_UNSUPPORTED"


@pytest.mark.parametrize(
    "payload",
    [
        {"accession": "SRR1", "download_method": "aws"},
        {"accession": " srx42 ", "download_method": "ftp"},
        {"accession": "PRJNA1"},
        {"source": "direct_link", "links": ["https://example.org/a", "ftp://example.org/b"]},
        {"source": "cloud_storage", "cloud_provider": "aliyun", "object_uri": "oss://bucket/a"},
        {"source": "cloud_storage", "cloud_provider": "volcengine", "object_uri": "tos://bucket/a"},
        {
            "source": "cloud_storage",
            "cloud_provider": "huaweicloud",
            "object_uri": "obs://bucket/a",
        },
    ],
)
def test_declared_source_method_matrix(payload):
    request = DownloadRequest.model_validate(payload)
    if request.source == "sra":
        assert request.accession == str(payload["accession"]).strip().upper()
        assert request.download_method in {"aws", "ftp"}


@pytest.mark.parametrize(
    "payload,code",
    [
        ({"source": "cloud_drive"}, "DOWNLOAD_SOURCE_UNSUPPORTED"),
        ({"accession": "SRR1", "download_method": "prefetch"}, "DOWNLOAD_METHOD_UNSUPPORTED"),
        ({"accession": "SRR1", "download_method": "auto"}, "DOWNLOAD_METHOD_UNSUPPORTED"),
        ({"accession": "GSE123"}, "DOWNLOAD_METADATA_RESOLUTION_REQUIRED"),
        ({"accession": "GSM123"}, "DOWNLOAD_METADATA_RESOLUTION_REQUIRED"),
        ({"accession": "SRR1,SRR2"}, "DOWNLOAD_ACCESSION_UNSUPPORTED"),
        (
            {"source": "direct_link", "links": ["ftps://example.org/a"]},
            "DOWNLOAD_PROTOCOL_UNSUPPORTED",
        ),
        (
            {"source": "direct_link", "links": ["file:///tmp/private"]},
            "DOWNLOAD_PROTOCOL_UNSUPPORTED",
        ),
        (
            {"source": "cloud_storage", "cloud_provider": "s3", "object_uri": "s3://bucket/a"},
            "DOWNLOAD_PROVIDER_UNSUPPORTED",
        ),
        (
            {"source": "cloud_storage", "cloud_provider": "cos", "object_uri": "cos://bucket/a"},
            "DOWNLOAD_PROVIDER_UNSUPPORTED",
        ),
        (
            {"source": "cloud_storage", "cloud_provider": "aliyun", "object_uri": "s3://bucket/a"},
            "DOWNLOAD_PROTOCOL_UNSUPPORTED",
        ),
        ({"accession": "SRR1", "advanced": {}}, "DOWNLOAD_FILTERS_UNSUPPORTED"),
        ({"accession": "SRR1", "filter_run": ["SRR.*"]}, "DOWNLOAD_FILTERS_UNSUPPORTED"),
    ],
)
def test_unsupported_inputs_have_stable_reason_codes(payload, code):
    with pytest.raises(ValidationError) as error:
        DownloadRequest.model_validate(payload)
    assert error.value.errors()[0]["type"] == code


def test_config_can_restrict_protocols_but_cannot_add_a_transport(monkeypatch):
    from cygnusx.application.schemas import download as schema
    from cygnusx.tools.download.config import DownloadConfig, DownloadValidationConfig

    config = DownloadConfig(validation=DownloadValidationConfig(allowed_schemes=["https"]))
    monkeypatch.setattr(schema, "get_download_config", lambda: config)
    assert DownloadRequest(source="direct_link", links=["https://example.org/a"])
    with pytest.raises(ValidationError) as error:
        DownloadRequest(source="direct_link", links=["ftp://example.org/a"])
    assert error.value.errors()[0]["type"] == "DOWNLOAD_PROTOCOL_DISABLED"
    with pytest.raises(ValidationError):
        DownloadValidationConfig(allowed_schemes=["https", "ftps"])


@pytest.mark.parametrize("links", [[1], [None], "https://example.org/a"])
def test_malformed_links_are_schema_errors_not_unhandled_exceptions(links):
    with pytest.raises(ValidationError):
        DownloadRequest(source="direct_link", links=links)


def test_binary_paths_are_configuration_only_and_absolute():
    from cygnusx.tools.download.config import DownloadBinariesConfig

    with pytest.raises(ValidationError):
        DownloadBinariesConfig(ebi="relative/EBIDownload")
    with pytest.raises(ValidationError):
        DownloadBinariesConfig(ebi="https://example.org/EBIDownload?token=secret")


@pytest.mark.asyncio
async def test_service_rechecks_protocol_changes_before_task_directory_or_queue(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock

    from cygnusx.application.services import download_service as module
    from cygnusx.core.exceptions import ValidationError as PolicyError
    from cygnusx.tools.download.config import DownloadConfig

    request = DownloadRequest(source="direct_link", links=["ftp://example.org/a"])
    config = DownloadConfig()
    config.validation.allowed_schemes = ["https"]
    monkeypatch.setattr(module, "get_download_config", lambda: config)
    backend = SimpleNamespace(ensure_dir=AsyncMock())
    service = module.DownloadService(MagicMock(), backend=backend)
    service._domain = SimpleNamespace(submit=AsyncMock())
    with pytest.raises(PolicyError) as error:
        await service.submit("unused-owner", request)
    assert error.value.code == "DOWNLOAD_PROTOCOL_DISABLED"
    backend.ensure_dir.assert_not_called()
    service._domain.submit.assert_not_called()


def test_feature_switch_policy_is_same_for_all_sources():
    from types import SimpleNamespace

    from cygnusx.core.exceptions import ValidationError as PolicyError
    from cygnusx.tools.download.config import DownloadConfig, ensure_download_available

    settings = SimpleNamespace(
        enable_ebi_download=False, enable_direct_download=False, enable_cloud_storage_download=False
    )
    for source, feature in [
        ("sra", "ebi"),
        ("direct_link", "direct_link"),
        ("cloud_storage", "cloud_storage"),
    ]:
        config = DownloadConfig()
        with pytest.raises(PolicyError) as error:
            ensure_download_available(source, 0, config, settings)
        assert error.value.code == "DOWNLOAD_SOURCE_DISABLED"
        setattr(config.features, feature, True)
        ensure_download_available(source, 0, config, settings)
    config = DownloadConfig()
    settings.enable_direct_download = True
    with pytest.raises(PolicyError) as error:
        ensure_download_available("direct_link", 101, config, settings)
    assert error.value.code == "DOWNLOAD_LINK_LIMIT"


def test_platform_methods_remain_a_subset_of_checked_in_cli():
    import re
    from pathlib import Path

    from cygnusx.domain.download_contract import SRA_METHODS
    from cygnusx.infrastructure.celery_app.tasks.download import _build_direct_link_args

    source = Path("pipelines/EBIDownload/crates/ebidownload-core/src/lib.rs").read_text()
    methods = re.search(r"pub enum DownloadMethod \{([^}]+)\}", source).group(1)
    assert {word.lower() for word in re.findall(r"\b[A-Z][A-Za-z]+\b", methods)} >= SRA_METHODS
    args = _build_direct_link_args(["https://example.org/a"], "/tmp/output", 4, "skip")
    assert args[-1] == "https://example.org/a" and "--continue=true" in args


@pytest.mark.asyncio
async def test_rest_rejects_unsupported_method_with_reason_before_submission():
    from unittest.mock import AsyncMock

    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from cygnusx.api.deps import get_current_user_id
    from cygnusx.api.v1 import downloads

    app = FastAPI()
    service = AsyncMock()
    app.include_router(downloads.router, prefix="/api/v1/downloads")

    async def current_user():
        return "isolated-owner"

    async def current_service():
        return service

    app.dependency_overrides[get_current_user_id] = current_user
    app.dependency_overrides[downloads.get_download_service] = current_service
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://isolated") as client:
        response = await client.post(
            "/api/v1/downloads", json={"accession": "SRR1", "download_method": "aspera"}
        )
    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "DOWNLOAD_METHOD_UNSUPPORTED"
    service.submit.assert_not_called()

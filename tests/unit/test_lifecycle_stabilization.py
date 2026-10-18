"""Read-contract and manifest compatibility stabilization; no transport or queue."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cygnusx.application.schemas.report_delivery import EvidenceManifest
from tests.unit.test_agent_tools_phase2 import ctx
from tests.unit.test_agent_tools_phase2 import env as env

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def test_rest_gateway_share_server_capabilities(env):
    from cygnusx.api.v1.downloads import download_capabilities
    from cygnusx.tools.download.config import describe_download_capabilities

    result = await env.gateway.invoke(await ctx(env), "downloads.describe_capabilities", {})
    assert (
        result["result"]
        == await download_capabilities(env.owner)
        == describe_download_capabilities()
    )
    assert result["result"]["write_enabled"] is False
    env.download.assert_not_called()
    env.analysis.assert_not_called()


@pytest.mark.parametrize("version", ["v1", "v1.1"])
async def test_manifest_old_snapshot_is_still_valid_and_partial_is_explicit(version):
    payload = dict(
        manifest_schema_version=f"cygnusx.evidence_manifest.{version}",
        package_id=uuid4(),
        task_id=uuid4(),
        snapshot_id=uuid4(),
        snapshot_digest="a" * 64,
        package_version="v1",
        renderer_version="test",
        template_version="test",
        files=(),
        evidence_status="partial",
        generated_at=datetime.now(UTC),
        validation_status="validated",
    )
    manifest = EvidenceManifest.model_validate(payload)
    assert manifest.evidence_status == "partial"
    payload.update(snapshot_id=None, snapshot_digest=None)
    if version == "v1":
        with pytest.raises(ValidationError):
            EvidenceManifest.model_validate(payload)
    else:
        assert EvidenceManifest.model_validate(payload).snapshot_id is None
        payload["evidence_status"] = "complete"
        with pytest.raises(ValidationError):
            EvidenceManifest.model_validate(payload)

"""通过实际 HTTP 路由验证参考配置的完整 tracks URI；不连接生产 DB 或 Docker。"""

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from cygnusx.api.deps import get_current_user_id
from cygnusx.tools.jbrowse import api, config
from cygnusx.tools.jbrowse.service import JBrowseService

pytestmark = pytest.mark.integration


@pytest.fixture
def jbrowse_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[FastAPI, Path]]:
    root = tmp_path / "shared-data"
    reference = root / "reference-store/reference"
    for name in ("genome.fa", "genome.fa.fai", "signal.bw"):
        path = reference / "fixture" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture", encoding="utf-8")
    yaml_path = tmp_path / "jbrowse.yaml"
    yaml_path.write_text(
        "assemblies:\n  - id: fixture\n    name: Fixture\n"
        "    fasta: fixture/genome.fa\n    fai: fixture/genome.fa.fai\n"
        "preset_tracks:\n  fixture:\n    - name: Signal\n"
        "      file: fixture/signal.bw\n      type: bw\n",
        encoding="utf-8",
    )
    settings = SimpleNamespace(
        storage_path=str(root), reference_genomes_yaml=str(reference / "registry.yaml")
    )
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    monkeypatch.setattr(config, "_data_root", lambda: root)
    service = JBrowseService(config.ConfigManager(yaml_path))
    app = FastAPI()
    app.include_router(api.router, prefix="/api/v1/jbrowse")

    async def user() -> str:
        return "fixture-user"

    async def get_service() -> JBrowseService:
        return service

    app.dependency_overrides[get_current_user_id] = user
    app.dependency_overrides[api.get_jbrowse_service] = get_service
    yield app, root
    app.dependency_overrides.clear()


async def test_browser_config_preserves_reference_directories(
    jbrowse_app: tuple[FastAPI, Path],
) -> None:
    app, _root = jbrowse_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/jbrowse/config", params={"assembly": "fixture"})
    assert response.status_code == 200
    result = response.json()
    adapter = result["assemblies"][0]["sequence"]["adapter"]
    prefix = "/tracks/reference-store/reference/fixture/"
    assert adapter["fastaLocation"]["uri"] == prefix + "genome.fa"
    assert adapter["faiLocation"]["uri"] == prefix + "genome.fa.fai"
    assert result["tracks"][0]["adapter"]["bigWigLocation"]["uri"] == prefix + "signal.bw"

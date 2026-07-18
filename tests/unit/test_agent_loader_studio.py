"""Agent YAML studio 段解析单元测试（agent_loader._load_single_agent）"""

from pathlib import Path

import pytest

from omichub.infrastructure.config.agent_loader import _load_single_agent


def _write_yaml(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "agent.yaml"
    path.write_text(body, encoding="utf-8")
    return path


@pytest.mark.unit
def test_studio_section_parsed(tmp_path: Path):
    """studio: {enabled, image} 原样解析并规整类型"""
    path = _write_yaml(
        tmp_path,
        "agent_id: a1\nname: 测试\nstudio:\n  enabled: true\n  image: omichub-sandbox:bio\n",
    )
    data = _load_single_agent(path)
    assert data is not None
    assert data["studio"] == {"enabled": True, "image": "omichub-sandbox:bio"}


@pytest.mark.unit
def test_studio_section_non_dict_dropped(tmp_path: Path):
    """studio 段结构非法时剔除，不影响 Agent 加载"""
    path = _write_yaml(tmp_path, "agent_id: a1\nstudio: oops\n")
    data = _load_single_agent(path)
    assert data is not None
    assert "studio" not in data


@pytest.mark.unit
def test_studio_section_partial_fields(tmp_path: Path):
    """只写 image 时保留 image；enabled 缺省不补"""
    path = _write_yaml(tmp_path, "agent_id: a1\nstudio:\n  image: omichub-sandbox:base\n")
    data = _load_single_agent(path)
    assert data is not None
    assert data["studio"] == {"image": "omichub-sandbox:base"}


@pytest.mark.unit
def test_studio_section_extra_keys_ignored(tmp_path: Path):
    """P0 只识别 enabled/image，其余键（如 sandbox 资源覆盖）忽略"""
    path = _write_yaml(
        tmp_path,
        "agent_id: a1\nstudio:\n  enabled: false\n  sandbox:\n    cpu: 4\n",
    )
    data = _load_single_agent(path)
    assert data is not None
    assert data["studio"] == {"enabled": False}


@pytest.mark.unit
def test_no_studio_section_untouched(tmp_path: Path):
    """无 studio 段的 YAML 行为不变"""
    path = _write_yaml(tmp_path, "agent_id: a1\nname: 普通助手\n")
    data = _load_single_agent(path)
    assert data is not None
    assert "studio" not in data
    assert data["agent_id"] == "a1"


@pytest.mark.asyncio
async def test_existing_builtin_agent_resyncs_studio_features(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    from omichub.application.services.agent_service import AgentService
    from omichub.infrastructure.database.models.agent import AgentTemplateModel

    existing = AgentTemplateModel(
        agent_id="a1",
        name="既有内置 Agent",
        is_builtin=True,
        features={"enable_web_search": True, "studio": {"enabled": False}},
    )
    db = AsyncMock()
    provider_result = MagicMock()
    provider_result.scalars.return_value.all.return_value = []
    db.execute.return_value = provider_result
    service = AgentService(db)
    service.get_agent = AsyncMock(return_value=existing)
    monkeypatch.setattr(
        "omichub.application.services.agent_service.load_agent_configs",
        lambda: [
            {
                "agent_id": "a1",
                "features": {"enable_file_upload": True},
                "studio": {"enabled": True, "image": "omichub-sandbox:bio"},
            }
        ],
    )

    await service.ensure_builtin_agents()

    assert existing.features == {
        "enable_web_search": True,
        "enable_file_upload": True,
        "studio": {"enabled": True, "image": "omichub-sandbox:bio"},
    }
    db.add.assert_not_called()
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_existing_custom_agent_is_not_overwritten(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    from omichub.application.services.agent_service import AgentService
    from omichub.infrastructure.database.models.agent import AgentTemplateModel

    existing = AgentTemplateModel(
        agent_id="a1",
        name="用户 Agent",
        is_builtin=False,
        features={"studio": {"enabled": False}},
    )
    db = AsyncMock()
    provider_result = MagicMock()
    provider_result.scalars.return_value.all.return_value = []
    db.execute.return_value = provider_result
    service = AgentService(db)
    service.get_agent = AsyncMock(return_value=existing)
    monkeypatch.setattr(
        "omichub.application.services.agent_service.load_agent_configs",
        lambda: [{"agent_id": "a1", "studio": {"enabled": True}}],
    )

    await service.ensure_builtin_agents()

    assert existing.features == {"studio": {"enabled": False}}
    db.add.assert_not_called()

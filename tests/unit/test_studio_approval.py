"""Studio 工具审批服务（HITL，§3）状态机与归属校验测试：redis 用内存替身。"""

from __future__ import annotations

import json
from typing import Any

import pytest

from omichub.application.services import studio_approval_service as approval_module
from omichub.application.services.studio_approval_service import (
    APPROVAL_REQUIRED_TOOLS,
    StudioApprovalService,
)
from omichub.application.services.studio_tools import STUDIO_TOOL_NAMES, STUDIO_TOOL_SCHEMAS


class _FakeRedis:
    """最小 redis.asyncio 替身：字符串 KV + list，供 BLPOP 立即返回。"""

    def __init__(self) -> None:
        self.kv: dict[str, str] = {}
        self.lists: dict[str, list[str]] = {}
        self.expirations: dict[str, int] = {}

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.kv[key] = value
        self.expirations[key] = ttl

    async def get(self, key: str) -> str | None:
        return self.kv.get(key)

    async def rpush(self, key: str, value: str) -> int:
        self.lists.setdefault(key, []).append(value)
        return len(self.lists[key])

    async def expire(self, key: str, ttl: int) -> None:
        self.expirations[key] = ttl

    async def blpop(
        self,
        keys: list[str],
        timeout: int = 0,  # noqa: ASYNC109 - 与 redis.asyncio.blpop 签名保持一致
    ) -> tuple[str, str] | None:
        for key in keys:
            if self.lists.get(key):
                return key, self.lists[key].pop(0)
        return None


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> _FakeRedis:
    redis = _FakeRedis()
    monkeypatch.setattr(approval_module, "get_redis", lambda: redis)
    return redis


def _create_kwargs() -> dict[str, Any]:
    return {
        "user_id": "u-1",
        "session_id": "sess-1",
        "tool_call_id": "tc-1",
        "tool_name": "sandbox_execute",
        "arguments": {"language": "python", "code": "print(1)"},
        "risk_hint": "将在沙盒中执行 python 代码",
    }


@pytest.mark.unit
async def test_create_persists_pending_record_with_ttl(fake_redis: _FakeRedis) -> None:
    service = StudioApprovalService()
    record = await service.create(**_create_kwargs())

    assert record["status"] == "pending"
    assert len(record["approval_id"]) == 32  # uuid4 hex
    stored = fake_redis.kv[f"studio:approval:{record['approval_id']}"]
    assert json.loads(stored)["tool_name"] == "sandbox_execute"
    assert fake_redis.expirations[f"studio:approval:{record['approval_id']}"] == 1800

    fetched = await service.get(record["approval_id"])
    assert fetched is not None and fetched["user_id"] == "u-1"


@pytest.mark.unit
async def test_get_returns_none_for_unknown_id(fake_redis: _FakeRedis) -> None:
    assert await StudioApprovalService().get("nonexistent") is None


@pytest.mark.unit
async def test_resolve_approved_writes_result_and_updates_status(
    fake_redis: _FakeRedis,
) -> None:
    service = StudioApprovalService()
    record = await service.create(**_create_kwargs())

    resolved = await service.resolve(record["approval_id"], "u-1", "approved")
    assert resolved is not None and resolved["status"] == "approved"

    result_key = f"studio:approval:result:{record['approval_id']}"
    resolution = json.loads(fake_redis.lists[result_key][0])
    assert resolution == {"action": "approved"}

    stored = json.loads(fake_redis.kv[f"studio:approval:{record['approval_id']}"])
    assert stored["status"] == "approved"


@pytest.mark.unit
async def test_resolve_edited_carries_modified_args(fake_redis: _FakeRedis) -> None:
    service = StudioApprovalService()
    record = await service.create(**_create_kwargs())
    modified = {"language": "python", "code": "print(2)"}

    await service.resolve(record["approval_id"], "u-1", "edited", modified_args=modified)

    resolution = json.loads(fake_redis.lists[f"studio:approval:result:{record['approval_id']}"][0])
    assert resolution["action"] == "edited"
    assert resolution["modified_args"] == modified


@pytest.mark.unit
async def test_resolve_rejected_with_reason(fake_redis: _FakeRedis) -> None:
    service = StudioApprovalService()
    record = await service.create(**_create_kwargs())

    await service.resolve(record["approval_id"], "u-1", "rejected", reason="路径不对")

    resolution = json.loads(fake_redis.lists[f"studio:approval:result:{record['approval_id']}"][0])
    assert resolution == {"action": "rejected", "reason": "路径不对"}


@pytest.mark.unit
async def test_resolve_rejects_wrong_user(fake_redis: _FakeRedis) -> None:
    service = StudioApprovalService()
    record = await service.create(**_create_kwargs())

    assert await service.resolve(record["approval_id"], "u-2", "approved") is None
    # 记录仍为 pending，且结果队列未写入
    assert (await service.get(record["approval_id"]))["status"] == "pending"  # type: ignore[index]
    assert f"studio:approval:result:{record['approval_id']}" not in fake_redis.lists


@pytest.mark.unit
async def test_resolve_rejects_consumed_record(fake_redis: _FakeRedis) -> None:
    service = StudioApprovalService()
    record = await service.create(**_create_kwargs())

    assert await service.resolve(record["approval_id"], "u-1", "rejected") is not None
    assert await service.resolve(record["approval_id"], "u-1", "approved") is None


@pytest.mark.unit
async def test_resolve_unknown_id_returns_none(fake_redis: _FakeRedis) -> None:
    assert await StudioApprovalService().resolve("nonexistent", "u-1", "approved") is None


@pytest.mark.unit
async def test_wait_resolution_returns_pushed_resolution(fake_redis: _FakeRedis) -> None:
    service = StudioApprovalService()
    record = await service.create(**_create_kwargs())
    await service.resolve(record["approval_id"], "u-1", "approved")

    resolution = await service.wait_resolution(record["approval_id"], timeout=1)
    assert resolution["action"] == "approved"


@pytest.mark.unit
async def test_wait_resolution_times_out(fake_redis: _FakeRedis) -> None:
    service = StudioApprovalService()
    record = await service.create(**_create_kwargs())

    resolution = await service.wait_resolution(record["approval_id"], timeout=1)
    assert resolution == {"action": "timeout"}


@pytest.mark.unit
def test_approval_required_tools_cover_write_and_execute() -> None:
    assert {
        "sandbox_execute",
        "workspace_write",
        "workspace_edit",
        "artifact_register",
    } == APPROVAL_REQUIRED_TOOLS
    # 只读工具不在受控集合内
    assert "workspace_read" not in APPROVAL_REQUIRED_TOOLS
    assert "update_plan" not in APPROVAL_REQUIRED_TOOLS
    assert "ask_user" not in APPROVAL_REQUIRED_TOOLS


@pytest.mark.unit
def test_studio_tool_schemas_include_ask_user() -> None:
    assert "ask_user" in STUDIO_TOOL_NAMES
    schema = next(
        item for item in STUDIO_TOOL_SCHEMAS if item["function"]["name"] == "ask_user"
    )
    params = schema["function"]["parameters"]
    assert params["required"] == ["question"]
    assert params["properties"]["options"]["type"] == "array"

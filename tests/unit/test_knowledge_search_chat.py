"""普通聊天挂载 knowledge_search 知识库检索的单元测试"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from omichub.application.services.chat_service import (
    KNOWLEDGE_SEARCH_SYSTEM_PROMPT_SUFFIX,
    KNOWLEDGE_SEARCH_TOOL,
    ChatService,
)


@pytest.mark.unit
def test_knowledge_search_tool_schema():
    """schema 与 Studio 侧参数契约一致（query 必填，limit 1-8）"""
    fn = KNOWLEDGE_SEARCH_TOOL["function"]
    assert fn["name"] == "knowledge_search"
    assert fn["parameters"]["required"] == ["query"]
    assert set(fn["parameters"]["properties"]) == {"query", "limit"}
    assert "再调用 web_search" in fn["description"]


@pytest.mark.unit
def test_knowledge_search_prompt_requires_kb_then_web_then_model_synthesis():
    prompt = KNOWLEDGE_SEARCH_SYSTEM_PROMPT_SUFFIX

    assert "即使用户只是学习原理、暂时没有数据" in prompt
    assert prompt.index("`knowledge_search`") < prompt.index("`web_search`")
    assert "结果为空" in prompt
    assert "模型自身的通用知识" in prompt
    assert "只声明实际执行过的检索" in prompt


@pytest.mark.unit
async def test_knowledge_search_chat_delegates_to_studio_impl(monkeypatch):
    """辅助方法复用 Studio 的 _knowledge_search 实现并透传 db"""
    called: dict[str, Any] = {}

    async def fake_search(
        args: dict[str, Any], db: Any, *, project_id: str | None = None
    ) -> dict[str, Any]:
        called["args"] = args
        called["db"] = db
        called["project_id"] = project_id
        return {"success": True, "result": {"results": []}}

    monkeypatch.setattr(
        "omichub.application.services.studio_tools._knowledge_search", fake_search
    )
    service = ChatService(db=AsyncMock())
    result = await service._knowledge_search_chat({"query": "双细胞", "limit": 3})

    assert result["success"] is True
    assert called["args"] == {"query": "双细胞", "limit": 3}
    assert called["db"] is service._db
    assert called["project_id"] is None


@pytest.mark.unit
async def test_knowledge_search_chat_failure_returns_error_envelope(monkeypatch):
    """实现抛异常时返回失败信封，不中断对话"""

    async def boom(
        args: dict[str, Any], db: Any, *, project_id: str | None = None
    ) -> dict[str, Any]:
        raise RuntimeError("db down")

    monkeypatch.setattr(
        "omichub.application.services.studio_tools._knowledge_search", boom
    )
    service = ChatService(db=AsyncMock())
    result = await service._knowledge_search_chat({"query": "x"})

    assert result["success"] is False
    assert "知识库检索失败" in result["error"]

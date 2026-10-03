"""Skill-First 路由的元数据筛选与正文适配审查。"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from cygnusx.application.services.skill_route_service import SkillRouteService
from cygnusx.application.services.skill_route_tool_service import SkillRouteToolService


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _Scalars(self._rows)


class _Db:
    def __init__(self, rows):
        self.rows = rows

    async def execute(self, _query):
        return _Result(self.rows)


def _skill(skill_id: str, description: str, prompt: str):
    return SimpleNamespace(
        id=uuid.uuid4(),
        skill_id=skill_id,
        name=skill_id,
        description=description,
        category="bioinformatics",
        frontmatter={"task_tags": ["rna-seq", "differential-expression"]},
        prompt=prompt,
        version="1.0.0",
        source_type="builtin",
        is_active=True,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_prepare_candidates_reads_candidate_body(monkeypatch):
    candidate = _skill(
        "rnaseq-de",
        "bulk RNA-seq differential expression",
        "输入 count matrix，使用 DESeq2，输出差异基因结果和火山图。",
    )
    monkeypatch.setattr(
        "cygnusx.application.services.skill_route_service.skill_store.read_skill_body",
        lambda skill_id: candidate.prompt if skill_id == candidate.skill_id else None,
    )
    monkeypatch.setattr(
        "cygnusx.application.services.skill_route_service.skill_store.list_skill_metadata",
        lambda: [],
    )

    result = await SkillRouteService().prepare_candidates(
        db=_Db([candidate]), query="请用 count matrix 做 RNA-seq 差异表达并输出结果"
    )

    assert result[0]["skill_id"] == "rnaseq-de"
    assert result[0]["body_loaded"] is True
    assert "DESeq2" in result[0]["skill_body"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_prepare_candidates_keeps_full_candidate_for_scout(monkeypatch):
    unrelated = SimpleNamespace(
        id=uuid.uuid4(),
        skill_id="unrelated",
        name="unrelated",
        description="微生物群落多样性统计",
        category="bioinformatics",
        frontmatter={"task_tags": ["microbiome", "diversity"]},
        prompt="这里只介绍历史背景，不包含执行步骤。",
        version="1.0.0",
        source_type="builtin",
        is_active=True,
    )
    monkeypatch.setattr(
        "cygnusx.application.services.skill_route_service.skill_store.read_skill_body",
        lambda _skill_id: unrelated.prompt,
    )
    monkeypatch.setattr(
        "cygnusx.application.services.skill_route_service.skill_store.list_skill_metadata",
        lambda: [],
    )

    result = await SkillRouteService().prepare_candidates(
        db=_Db([unrelated]), query="做 ChIP-seq peak calling"
    )

    assert result == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tool_delegates_body_review_to_subagent(monkeypatch):
    candidate = _skill("rnaseq-de", "bulk RNA-seq differential expression", "使用 DESeq2。")
    monkeypatch.setattr(
        "cygnusx.application.services.skill_route_tool_service.SkillRouteService.prepare_candidates",
        lambda _self, **_kwargs: _async_value(
            [
                {
                    "skill_id": candidate.skill_id,
                    "name": candidate.name,
                    "description": candidate.description,
                    "skill_body": candidate.prompt,
                    "body_loaded": True,
                }
            ]
        ),
    )

    class _Scout:
        async def run(self, **kwargs):
            assert kwargs["safe_only"] is True
            assert kwargs["runtime_authorized"] is True
            assert "使用 DESeq2" in kwargs["tasks"][0]["task"]
            return {
                "llm_payload": {
                    "results": [
                        {"answer": '{"matched": true, "skill_id": "rnaseq-de", "confidence": 0.95}'}
                    ]
                }
            }

    monkeypatch.setattr(
        "cygnusx.application.services.skill_route_tool_service.ParallelSubAgentService",
        _Scout,
    )
    context = SimpleNamespace(user_id="u1", session_id="s1", agent_id="agent-general", db=object())

    result = await SkillRouteToolService().route(query="做 RNA-seq 差异表达", context=context)

    assert result["matched"] is True
    assert result["skill_id"] == "rnaseq-de"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_prepare_candidates_includes_disk_skill_metadata(monkeypatch):
    monkeypatch.setattr(
        "cygnusx.application.services.skill_route_service.skill_store.list_skill_metadata",
        lambda: [
            {
                "skill_id": "bio-chipseq-peak-calling",
                "name": "bio-chipseq-peak-calling",
                "description": "ChIP-seq peak calling",
                "category": "bioinformatics",
                "frontmatter": {"task_tags": ["chip-seq", "peak calling"]},
            }
        ],
    )
    monkeypatch.setattr(
        "cygnusx.application.services.skill_route_service.skill_store.read_skill_body",
        lambda skill_id: "先做 peak calling" if skill_id == "bio-chipseq-peak-calling" else None,
    )

    result = await SkillRouteService().prepare_candidates(
        db=_Db([]), query="做 ChIP-seq peak calling"
    )

    assert result[0]["skill_id"] == "bio-chipseq-peak-calling"
    assert result[0]["body_loaded"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_prepare_candidates_hyphenated_skill_id_matches_keywords(monkeypatch):
    """skill_id 按连字符拆分后可被查询关键词命中（回归：bio-chip-seq-peak-calling 被挤出审查名单）。"""
    monkeypatch.setattr(
        "cygnusx.application.services.skill_route_service.skill_store.list_skill_metadata",
        lambda: [
            {
                "skill_id": "bio-chip-seq-peak-calling",
                "name": "bio-chip-seq-peak-calling",
                "description": "",
                "category": "bioinformatics",
                "frontmatter": {},
            },
            {
                "skill_id": "bio-epitranscriptomics-m6a-peak-calling",
                "name": "bio-epitranscriptomics-m6a-peak-calling",
                "description": "",
                "category": "bioinformatics",
                "frontmatter": {},
            },
        ],
    )
    monkeypatch.setattr(
        "cygnusx.application.services.skill_route_service.skill_store.read_skill_body",
        lambda skill_id: f"{skill_id} 正文" if skill_id == "bio-chip-seq-peak-calling" else None,
    )

    result = await SkillRouteService().prepare_candidates(
        db=_Db([]), query="用 ChIP-seq 数据进行 peak calling"
    )

    assert result, "连字符拆分的 skill_id 应能被关键词命中"
    assert result[0]["skill_id"] == "bio-chip-seq-peak-calling"
    assert result[0]["metadata_score"] >= 3
    assert result[0]["body_loaded"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tokens_stem_plural_and_ing_forms():
    """轻量词形归一：peaks/calls 与 peak/calling 双向匹配。"""
    from cygnusx.application.services.skill_route_service import _tokens

    query_tokens = _tokens("ChIP-seq peak calling")
    doc_tokens = _tokens("Calls ChIP-seq peaks with MACS3")
    assert query_tokens & doc_tokens


@pytest.mark.unit
@pytest.mark.asyncio
async def test_prepare_candidates_truncates_oversized_body(monkeypatch):
    monkeypatch.setattr(
        "cygnusx.application.services.skill_route_service.skill_store.list_skill_metadata",
        lambda: [
            {
                "skill_id": "bio-chip-seq-peak-calling",
                "name": "bio-chip-seq-peak-calling",
                "description": "ChIP-seq peak calling",
                "category": "bioinformatics",
                "frontmatter": {},
            }
        ],
    )
    monkeypatch.setattr(
        "cygnusx.application.services.skill_route_service.skill_store.read_skill_body",
        lambda _skill_id: "x" * 10000,
    )

    result = await SkillRouteService().prepare_candidates(db=_Db([]), query="ChIP-seq peak calling")

    assert result[0]["body_truncated"] is True
    assert len(result[0]["skill_body"]) < 7000


@pytest.mark.unit
def test_finalize_compacts_candidates_and_builds_summary():
    from cygnusx.application.services.skill_route_tool_service import _finalize

    result = _finalize(
        {
            "matched": False,
            "skill_id": None,
            "confidence": 0.0,
            "reason": "x" * 300,
            "candidates": [
                {
                    "skill_id": "bio-a",
                    "name": "bio-a",
                    "description": "d" * 200,
                    "metadata_score": 2,
                    "skill_body": "不应外泄给主 Agent 的正文",
                }
            ],
        }
    )

    candidate = result["candidates"][0]
    assert candidate["description"] == "d" * 80
    assert "skill_body" not in candidate
    assert len(result["reason"]) <= 210
    assert result["summary"].startswith("未命中合适 Skill")


async def _async_value(value):
    return value

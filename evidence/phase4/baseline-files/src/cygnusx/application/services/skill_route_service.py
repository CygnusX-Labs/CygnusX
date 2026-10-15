"""Skill-First 路由：先筛元数据，再读取候选正文做适配审查。"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cygnusx.infrastructure.database.models.skill import SkillModel
from cygnusx.infrastructure.skills import skill_store

# 连字符作为分隔符：skill_id（如 bio-chip-seq-peak-calling）才能拆出可匹配的关键词
_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)
_STOPWORDS = frozenset({"的", "了", "和", "与", "做", "帮我", "请", "一下", "一个", "进行"})
_MAX_METADATA_CANDIDATES = 20
_MAX_BODY_REVIEWS = 5
# 候选正文字符上限：完整 SKILL.md 可能上万字，直接塞进 scout 任务会触发结果截断
_MAX_BODY_CHARS = 6000


def _expand_token(token: str) -> set[str]:
    """英文轻量词形归一：复数 s / 进行时 ing 截断，查询与索引两侧对称扩展。"""
    variants = {token}
    if token.isascii() and token.isalpha():
        if len(token) >= 4 and token.endswith("s"):
            variants.add(token[:-1])
        if len(token) >= 5 and token.endswith("ing"):
            variants.add(token[:-3])
    return variants


def _tokens(value: str) -> set[str]:
    tokens: set[str] = set()
    for raw in _TOKEN_RE.findall(value.lower()):
        if len(raw) < 2 or raw in _STOPWORDS:
            continue
        tokens |= _expand_token(raw)
    return tokens


def _metadata_text(skill: SkillModel) -> str:
    frontmatter = skill.frontmatter or {}
    tags = frontmatter.get("task_tags") or frontmatter.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    entrypoints = frontmatter.get("entrypoints") or []
    if isinstance(entrypoints, str):
        entrypoints = [entrypoints]
    return " ".join(
        [skill.skill_id, skill.name, skill.description, skill.category]
        + [str(item) for item in tags]
        + [str(item) for item in entrypoints]
    )


def _disk_metadata_text(skill: dict[str, Any]) -> str:
    frontmatter = skill.get("frontmatter") or {}
    tags = frontmatter.get("task_tags") or frontmatter.get("tags") or []
    entrypoints = frontmatter.get("entrypoints") or []
    return " ".join(
        [
            str(skill.get("skill_id") or ""),
            str(skill.get("name") or ""),
            str(skill.get("description") or ""),
            str(skill.get("category") or ""),
            *[str(item) for item in (tags if isinstance(tags, list) else [tags])],
            *[
                str(item)
                for item in (entrypoints if isinstance(entrypoints, list) else [entrypoints])
            ],
        ]
    )


def _score(query_tokens: set[str], text_tokens: set[str]) -> int:
    return len(query_tokens & text_tokens)


class SkillRouteService:
    """只读 Skill 路由服务，供 `skill_route` 工具和受限子 Agent 使用。"""

    async def prepare_candidates(
        self, *, db: AsyncSession, query: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        """只做确定性 L1 预筛并读取 L2 正文，不在此处替代 scout 审查。"""
        query = query.strip()
        if not query:
            return []

        rows = (
            (
                await db.execute(
                    select(SkillModel)
                    .where(SkillModel.is_active == True)  # noqa: E712
                    .order_by(SkillModel.created_at)
                )
            )
            .scalars()
            .all()
        )
        disk_rows = skill_store.list_skill_metadata()
        db_ids = {skill.skill_id for skill in rows}
        metadata_rows: list[tuple[dict[str, Any], int]] = [
            (
                {
                    "skill_id": skill.skill_id,
                    "name": skill.name,
                    "description": skill.description,
                    "category": skill.category,
                    "frontmatter": skill.frontmatter or {},
                    "version": skill.version,
                    "source": skill.source_type,
                    "model": skill,
                },
                0,
            )
            for skill in rows
        ]
        metadata_rows.extend(
            (skill, 0) for skill in disk_rows if str(skill.get("skill_id")) not in db_ids
        )
        query_tokens = _tokens(query)
        scored_rows: list[tuple[dict[str, Any], set[str]]] = [
            (
                skill,
                _tokens(_metadata_text(skill["model"]))
                if skill.get("model")
                else _tokens(_disk_metadata_text(skill)),
            )
            for skill, _ in metadata_rows
        ]
        if query_tokens and scored_rows:
            # 类 IDF 过滤：在超过 30% Skill 元数据中出现的通用 token（如 seq/data）
            # 不参与打分，避免所有组学 Skill 都被打成候选
            generic_cut = max(1, int(0.3 * len(scored_rows)))
            generic = {
                token
                for token in query_tokens
                # 覆盖超过 30% 且至少 5 个 Skill 的 token 才视为泛词，小语料不误伤
                if (
                    sum(1 for _, text_tokens in scored_rows if token in text_tokens) > generic_cut
                    and sum(1 for _, text_tokens in scored_rows if token in text_tokens) > 5
                )
            }
            distinctive = query_tokens - generic
            if distinctive:
                query_tokens = distinctive
        metadata = [
            (skill, _score(query_tokens, text_tokens)) for skill, text_tokens in scored_rows
        ]
        metadata = sorted(
            [(skill, score) for skill, score in metadata if score > 0],
            key=lambda item: item[1],
            reverse=True,
        )[:_MAX_METADATA_CANDIDATES]

        candidates: list[dict[str, Any]] = []
        for skill, score in metadata[: max(1, min(limit, _MAX_BODY_REVIEWS))]:
            skill_id = str(skill["skill_id"])
            body = skill_store.read_skill_body(skill_id) or str(skill.get("prompt") or "")
            body_truncated = len(body) > _MAX_BODY_CHARS
            if body_truncated:
                body = (
                    body[:_MAX_BODY_CHARS]
                    + "\n\n……（正文过长已截断，完整内容以磁盘 SKILL.md 为准）"
                )
            candidates.append(
                {
                    "skill_id": skill_id,
                    "name": str(skill.get("name") or skill_id),
                    "metadata_score": score,
                    "description": str(skill.get("description") or ""),
                    "version": skill.get("version"),
                    "source": str(skill.get("source") or ""),
                    "body_loaded": bool(body.strip()),
                    "body_truncated": body_truncated,
                    "skill_body": body,
                }
            )
        return candidates

    async def route(self, *, db: AsyncSession, query: str, limit: int = 5) -> dict[str, Any]:
        """兼容内部调用：返回候选正文，最终适配判断交给 scout。"""
        candidates = await self.prepare_candidates(db=db, query=query, limit=limit)
        return {
            "matched": False,
            "skill_id": None,
            "reason": "候选已准备，需交由 Skill scout 做全文适配审查",
            "candidates": [
                {key: value for key, value in item.items() if key != "skill_body"}
                for item in candidates
            ],
        }


async def route_skills(*, query: str, db: AsyncSession, limit: int = 5) -> dict[str, Any]:
    return await SkillRouteService().route(db=db, query=query, limit=limit)

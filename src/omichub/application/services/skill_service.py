"""Skill 应用服务 — 技能管理 + prompt 注入"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from omichub.application.schemas.skill import (
    CreateSkillDTO,
    SkillDTO,
    SkillVersionDTO,
    UpdateSkillDTO,
)
from omichub.core.exceptions import BusinessError, NotFoundError
from omichub.domain.skill.entities import Skill
from omichub.domain.skill.services import SkillDomainService
from omichub.infrastructure.database.models.skill import SkillModel, SkillVersionModel
from omichub.infrastructure.skills.skill_store import rewrite_skill_md
from omichub.infrastructure.skills.skillmd import ParsedSkill

MAX_ACTIVE_SKILLS = 10

# 内容字段：出现在更新里时视为内容变更，需要同步磁盘 SKILL.md
_CONTENT_FIELDS = {"name", "description", "prompt", "icon", "category"}


async def _snapshot_skill(
    db: AsyncSession,
    skill: SkillModel,
    *,
    source: str,
    changelog: str = "",
    created_by: uuid.UUID | None = None,
) -> SkillVersionModel:
    """把 skill 当前内容字段全量留档为下一个 revision（首版=1）。"""
    result = await db.execute(
        select(func.max(SkillVersionModel.revision)).where(
            SkillVersionModel.skill_id == skill.skill_id
        )
    )
    max_revision = result.scalar() or 0
    snapshot = SkillVersionModel(
        id=uuid.uuid4(),
        skill_id=skill.skill_id,
        revision=max_revision + 1,
        version=skill.version,
        name=skill.name,
        description=skill.description,
        prompt=skill.prompt,
        tool_definition=skill.tool_definition,
        icon=skill.icon,
        category=skill.category,
        frontmatter=skill.frontmatter,
        source=source,
        changelog=changelog,
        created_by=created_by,
    )
    db.add(snapshot)
    return snapshot


def _rewrite_disk_skill_md(skill: SkillModel) -> None:
    """DB 内容变更后同步重写磁盘 SKILL.md（文件夹存在时；不动 L3 资源）。"""
    parsed = ParsedSkill(
        skill_id=skill.skill_id,
        name=skill.name,
        description=skill.description,
        body=skill.prompt,
        frontmatter=skill.frontmatter or {},
        icon=skill.icon,
        category=skill.category,
        version=skill.version or "",
        author=skill.author or "",
    )
    rewrite_skill_md(parsed)


class SkillService:
    """技能应用服务"""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_skills(self, active_only: bool = False) -> list[SkillDTO]:
        query = select(SkillModel).order_by(SkillModel.created_at)
        if active_only:
            query = query.where(SkillModel.is_active == True)  # noqa: E712
        result = await self._db.execute(query)
        return [self._to_dto(m) for m in result.scalars().all()]

    async def get_skill(self, skill_id: str) -> SkillDTO:
        result = await self._db.execute(select(SkillModel).where(SkillModel.skill_id == skill_id))
        m = result.scalar_one_or_none()
        if not m:
            raise NotFoundError(f"技能 '{skill_id}' 不存在")
        return self._to_dto(m)

    async def create_skill(self, req: CreateSkillDTO, actor_id: uuid.UUID | None = None) -> SkillDTO:
        existing = await self.get_by_skill_id(req.skill_id)
        if existing:
            raise BusinessError(f"技能 ID '{req.skill_id}' 已存在")
        model = SkillModel(
            id=uuid.uuid4(),
            skill_id=req.skill_id,
            name=req.name,
            description=req.description,
            prompt=req.prompt,
            tool_definition=req.tool_definition,
            icon=req.icon,
            category=req.category,
            is_active=req.is_active,
            is_builtin=False,
        )
        self._db.add(model)
        await self._db.flush()
        await _snapshot_skill(
            self._db, model, source="admin", changelog="创建技能", created_by=actor_id
        )
        await self._db.flush()
        return self._to_dto(model)

    async def update_skill(
        self, skill_id: str, req: UpdateSkillDTO, actor_id: uuid.UUID | None = None
    ) -> SkillDTO:
        result = await self._db.execute(select(SkillModel).where(SkillModel.skill_id == skill_id))
        model = result.scalar_one_or_none()
        if not model:
            raise NotFoundError(f"技能 '{skill_id}' 不存在")
        data = req.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(model, key, value)
        await self._db.flush()
        if data:
            # 内容字段变更时同步重写磁盘 SKILL.md（use_skill 磁盘优先）
            if _CONTENT_FIELDS & data.keys():
                _rewrite_disk_skill_md(model)
            await _snapshot_skill(
                self._db,
                model,
                source="admin",
                changelog=f"更新技能：{', '.join(data.keys())}",
                created_by=actor_id,
            )
            await self._db.flush()
        return self._to_dto(model)

    async def delete_skill(self, skill_id: str) -> bool:
        result = await self._db.execute(select(SkillModel).where(SkillModel.skill_id == skill_id))
        model = result.scalar_one_or_none()
        if not model:
            raise NotFoundError(f"技能 '{skill_id}' 不存在")
        if model.is_builtin:
            raise BusinessError("内置技能不可删除，可停用")
        await self._db.delete(model)
        await self._db.flush()
        # 同步清理磁盘上的 SKILL.md 标准文件夹
        from omichub.infrastructure.skills.skill_store import remove_skill_folder

        remove_skill_folder(skill_id)
        return True

    async def toggle_skill(self, skill_id: str) -> SkillDTO:
        result = await self._db.execute(select(SkillModel).where(SkillModel.skill_id == skill_id))
        model = result.scalar_one_or_none()
        if not model:
            raise NotFoundError(f"技能 '{skill_id}' 不存在")
        model.is_active = not model.is_active
        await self._db.flush()
        return self._to_dto(model)

    async def list_skill_versions(self, skill_id: str) -> list[SkillVersionDTO]:
        """版本历史，按 revision 倒序"""
        if not await self.get_by_skill_id(skill_id):
            raise NotFoundError(f"技能 '{skill_id}' 不存在")
        result = await self._db.execute(
            select(SkillVersionModel)
            .where(SkillVersionModel.skill_id == skill_id)
            .order_by(SkillVersionModel.revision.desc())
        )
        return [self._to_version_dto(v) for v in result.scalars().all()]

    async def rollback_skill(
        self, skill_id: str, revision: int, actor_id: uuid.UUID | None = None
    ) -> SkillDTO:
        """还原到指定 revision 的内容快照，并留一行 rollback 快照。"""
        result = await self._db.execute(select(SkillModel).where(SkillModel.skill_id == skill_id))
        model = result.scalar_one_or_none()
        if not model:
            raise NotFoundError(f"技能 '{skill_id}' 不存在")
        result = await self._db.execute(
            select(SkillVersionModel).where(
                SkillVersionModel.skill_id == skill_id,
                SkillVersionModel.revision == revision,
            )
        )
        snapshot = result.scalar_one_or_none()
        if not snapshot:
            raise NotFoundError(f"技能 '{skill_id}' 不存在 revision {revision} 的版本快照")
        model.name = snapshot.name
        model.description = snapshot.description
        model.prompt = snapshot.prompt
        model.tool_definition = snapshot.tool_definition
        model.icon = snapshot.icon
        model.category = snapshot.category
        model.frontmatter = snapshot.frontmatter
        model.version = snapshot.version
        await self._db.flush()
        # 磁盘文件夹存在时同步重写 SKILL.md 正文（use_skill 磁盘优先）
        _rewrite_disk_skill_md(model)
        await _snapshot_skill(
            self._db,
            model,
            source="rollback",
            changelog=f"回滚到 revision {revision}",
            created_by=actor_id,
        )
        await self._db.flush()
        return self._to_dto(model)

    async def get_active_skills(self) -> list[Skill]:
        """获取所有启用的技能（实体列表，供 prompt 注入）"""
        result = await self._db.execute(
            select(SkillModel)
            .where(SkillModel.is_active == True)  # noqa: E712
            .order_by(SkillModel.created_at)
            .limit(MAX_ACTIVE_SKILLS)
        )
        return [self._to_entity(m) for m in result.scalars().all()]

    @staticmethod
    def build_skills_prompt(skills: list[Skill]) -> str:
        """组装技能 prompt 注入文本"""
        return SkillDomainService.build_prompt(skills)

    @staticmethod
    def build_skills_index(skills: list[Skill]) -> str:
        """L1：仅注入 name + description 索引（渐进式披露，正文经 use_skill 按需加载）"""
        return SkillDomainService.build_index(skills)

    async def get_by_skill_id(self, skill_id: str) -> SkillModel | None:
        result = await self._db.execute(select(SkillModel).where(SkillModel.skill_id == skill_id))
        return result.scalar_one_or_none()

    @staticmethod
    def _to_version_dto(v: SkillVersionModel) -> SkillVersionDTO:
        return SkillVersionDTO(
            revision=v.revision,
            version=v.version,
            name=v.name,
            source=v.source,
            changelog=v.changelog,
            created_by=v.created_by,
            created_at=v.created_at,
        )

    @staticmethod
    def _to_entity(m: SkillModel) -> Skill:
        return Skill(
            id=m.id,
            skill_id=m.skill_id,
            name=m.name,
            description=m.description,
            prompt=m.prompt,
            tool_definition=m.tool_definition,
            icon=m.icon,
            category=m.category,
            is_active=m.is_active,
            is_builtin=m.is_builtin,
            version=m.version,
            author=m.author,
            source_type=m.source_type,
            source_ref=m.source_ref,
            source_commit=m.source_commit,
            has_scripts=m.has_scripts,
            frontmatter=m.frontmatter,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )

    @staticmethod
    def _to_dto(m: SkillModel) -> SkillDTO:
        return SkillDTO(
            id=m.id,
            skill_id=m.skill_id,
            name=m.name,
            description=m.description,
            prompt=m.prompt,
            tool_definition=m.tool_definition,
            icon=m.icon,
            category=m.category,
            is_active=m.is_active,
            is_builtin=m.is_builtin,
            version=m.version,
            author=m.author,
            source_type=m.source_type,
            source_ref=m.source_ref,
            source_commit=m.source_commit,
            has_scripts=m.has_scripts,
            frontmatter=m.frontmatter,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )

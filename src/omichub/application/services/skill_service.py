"""Skill 应用服务 — 技能管理 + prompt 注入"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omichub.application.schemas.skill import (
    CreateSkillDTO,
    SkillDTO,
    UpdateSkillDTO,
)
from omichub.core.exceptions import BusinessError, NotFoundError
from omichub.domain.skill.entities import Skill
from omichub.domain.skill.services import SkillDomainService
from omichub.infrastructure.database.models.skill import SkillModel

MAX_ACTIVE_SKILLS = 10


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

    async def create_skill(self, req: CreateSkillDTO) -> SkillDTO:
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
        return self._to_dto(model)

    async def update_skill(self, skill_id: str, req: UpdateSkillDTO) -> SkillDTO:
        result = await self._db.execute(select(SkillModel).where(SkillModel.skill_id == skill_id))
        model = result.scalar_one_or_none()
        if not model:
            raise NotFoundError(f"技能 '{skill_id}' 不存在")
        data = req.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(model, key, value)
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

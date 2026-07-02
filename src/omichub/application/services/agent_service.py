"""Agent 应用服务 — 模板 CRUD、内置 Agent 初始化、调度上下文组装

调度中枢调用 ``assemble_context(agent_id)`` 拿到一次 LLM 请求所需的全部拼装件：
绑定的模型配置、系统提示词（含技能 prompt 后缀）、OpenAI tools、MCP server 实体。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omichub.application.schemas.agent import (
    AgentTemplateDTO,
    CreateAgentRequest,
    UpdateAgentRequest,
)
from omichub.core.exceptions import BusinessError, NotFoundError
from omichub.domain.mcp.entities import MCPServer
from omichub.domain.skill.entities import Skill
from omichub.infrastructure.config.agent_loader import load_agent_configs
from omichub.infrastructure.database.models.agent import AgentTemplateModel
from omichub.infrastructure.database.models.ai_provider import AIProviderConfigModel
from omichub.infrastructure.database.models.skill import SkillModel
from omichub.infrastructure.database.repositories.mcp_repository import (
    SqlAlchemyMCPServerRepository,
)


@dataclass
class AgentContext:
    """调度中枢组装出的一次请求上下文"""

    agent: AgentTemplateModel
    model_config: AIProviderConfigModel | None
    system_prompt: str
    tools: list[dict[str, Any]] = field(default_factory=list)
    mcp_servers: list[MCPServer] = field(default_factory=list)
    temperature: float = 0.7
    max_tokens: int = 4096


class AgentService:
    """Agent 模板应用服务"""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._mcp_repo = SqlAlchemyMCPServerRepository(db)

    # --- 内置 Agent 初始化 ---

    async def ensure_builtin_agents(self) -> None:
        """从 YAML 加载内置 Agent 配置，幂等落库"""
        yaml_configs = load_agent_configs()
        if not yaml_configs:
            return

        # 预加载所有启用的模型配置，按 name 建索引
        model_result = await self._db.execute(
            select(AIProviderConfigModel).where(
                AIProviderConfigModel.is_active == True  # noqa: E712
            )
        )
        models_by_name = {m.name: m for m in model_result.scalars().all()}

        for cfg in yaml_configs:
            existing = await self.get_agent(cfg["agent_id"])
            if existing is not None:
                continue

            # 按 model name 解析 model_id
            model_name = cfg.get("model", "")
            model_id = None
            model_engine = ""
            if model_name and model_name in models_by_name:
                provider = models_by_name[model_name]
                model_id = provider.id
                model_engine = provider.model  # 真实模型名

            # 构建落库字段
            agent_data = {
                "agent_id": cfg["agent_id"],
                "name": cfg.get("name", ""),
                "description": cfg.get("description", ""),
                "avatar": cfg.get("avatar", "\U0001F916"),
                "color": cfg.get("color", "#4f8ef7"),
                "category": cfg.get("category", "general"),
                "model_id": model_id,
                "model_name": model_name,
                "model_engine": model_engine,
                "system_prompt": cfg.get("system_prompt", ""),
                "welcome_message": cfg.get("welcome_message", ""),
                "mcp_ids": cfg.get("mcp_ids", []),
                "skill_ids": cfg.get("skill_ids", []),
                "temperature": cfg.get("temperature", 0.7),
                "max_tokens": cfg.get("max_tokens", 4096),
                "is_builtin": True,
                "is_active": True,
            }
            self._db.add(AgentTemplateModel(**agent_data))
        await self._db.flush()

    # --- 查询 ---

    async def list_agents(self, active_only: bool = False) -> list[AgentTemplateDTO]:
        await self.ensure_builtin_agents()
        query = select(AgentTemplateModel)
        if active_only:
            query = query.where(AgentTemplateModel.is_active == True)  # noqa: E712
        query = query.order_by(
            AgentTemplateModel.is_default.desc(), AgentTemplateModel.created_at
        )
        result = await self._db.execute(query)
        return [self._to_dto(a) for a in result.scalars().all()]

    async def get_agent(self, agent_id: str) -> AgentTemplateModel | None:
        result = await self._db.execute(
            select(AgentTemplateModel).where(AgentTemplateModel.agent_id == agent_id)
        )
        return result.scalar_one_or_none()

    async def get_agent_dto(self, agent_id: str) -> AgentTemplateDTO:
        agent = await self.get_agent(agent_id)
        if not agent:
            raise NotFoundError("Agent 不存在")
        return self._to_dto(agent)

    # --- CRUD ---

    async def create_agent(self, req: CreateAgentRequest) -> AgentTemplateDTO:
        if await self.get_agent(req.agent_id) is not None:
            raise BusinessError(f"Agent ID '{req.agent_id}' 已存在")
        agent = AgentTemplateModel(is_builtin=False, is_active=True, **req.model_dump())
        self._db.add(agent)
        await self._db.flush()
        return self._to_dto(agent)

    async def update_agent(self, agent_id: str, req: UpdateAgentRequest) -> AgentTemplateDTO:
        agent = await self.get_agent(agent_id)
        if not agent:
            raise NotFoundError("Agent 不存在")
        data = req.model_dump(exclude_unset=True)
        if data.get("is_default"):
            await self._clear_other_defaults()
        for key, value in data.items():
            setattr(agent, key, value)
        await self._db.flush()
        return self._to_dto(agent)

    async def delete_agent(self, agent_id: str) -> bool:
        agent = await self.get_agent(agent_id)
        if not agent:
            raise NotFoundError("Agent 不存在")
        if agent.is_builtin:
            agent.is_active = False
            await self._db.flush()
            return True
        await self._db.delete(agent)
        await self._db.flush()
        return True

    async def toggle_agent(self, agent_id: str) -> AgentTemplateDTO:
        agent = await self.get_agent(agent_id)
        if not agent:
            raise NotFoundError("Agent 不存在")
        agent.is_active = not agent.is_active
        await self._db.flush()
        return self._to_dto(agent)

    async def set_default_agent(self, agent_id: str) -> None:
        agent = await self.get_agent(agent_id)
        if not agent:
            raise NotFoundError("Agent 不存在")
        await self._clear_other_defaults()
        agent.is_default = True
        await self._db.flush()

    async def _clear_other_defaults(self) -> None:
        result = await self._db.execute(
            select(AgentTemplateModel).where(AgentTemplateModel.is_default == True)  # noqa: E712
        )
        for existing in result.scalars().all():
            existing.is_default = False

    # --- 调度上下文组装 ---

    async def assemble_context(self, agent_id: str) -> AgentContext | None:
        """供调度中枢调用：组装一次 LLM 请求所需的全部拼装件。

        Agent 自身不存在时返回 None；模型缺失/未启用通过 ChatChunk.error 在调用方处理。
        """
        agent = await self.get_agent(agent_id)
        if agent is None or not agent.is_active:
            return None

        # 1. 解析绑定模型：优先 agent.model_id，否则回落到默认/首个启用模型
        model_config = await self._resolve_model(agent.model_id)
        if model_config is None:
            return AgentContext(
                agent=agent, model_config=None,
                system_prompt=agent.system_prompt,
            )

        # 2. 收集绑定的 MCP server 及其工具，转成 OpenAI tools
        mcp_servers: list[MCPServer] = []
        tools: list[dict[str, Any]] = []
        mcp_uuids = [self._parse_uuid(mid) for mid in (agent.mcp_ids or [])]
        mcp_uuids = [u for u in mcp_uuids if u is not None]
        if mcp_uuids:
            mcp_servers = await self._mcp_repo.get_by_ids(mcp_uuids)
            for server in mcp_servers:
                for t in server.tools:
                    tools.append({
                        "type": "function",
                        "function": {
                            "name": t.tool_name,
                            "description": t.description or "",
                            "parameters": t.input_schema or {"type": "object", "properties": {}},
                        },
                    })

        # 3. 系统提示词 = Agent 设定 + 绑定技能 prompt 后缀
        system_prompt = agent.system_prompt
        skill_suffix = await self._build_skill_prompt(agent.skill_ids or [])
        if skill_suffix:
            system_prompt = f"{system_prompt}\n\n{skill_suffix}" if system_prompt else skill_suffix

        return AgentContext(
            agent=agent,
            model_config=model_config,
            system_prompt=system_prompt,
            tools=tools,
            mcp_servers=mcp_servers,
            temperature=agent.temperature,
            max_tokens=agent.max_tokens,
        )

    async def _resolve_model(self, model_id: uuid.UUID | None) -> AIProviderConfigModel | None:
        if model_id is not None:
            result = await self._db.execute(
                select(AIProviderConfigModel).where(
                    AIProviderConfigModel.id == model_id,
                    AIProviderConfigModel.is_active == True,  # noqa: E712
                )
            )
            return result.scalar_one_or_none()
        # 回落：默认模型 → 首个启用模型
        result = await self._db.execute(
            select(AIProviderConfigModel)
            .where(AIProviderConfigModel.is_active == True)  # noqa: E712
            .order_by(AIProviderConfigModel.is_default.desc())
        )
        return result.scalars().first()

    async def _build_skill_prompt(self, skill_ids: list[Any]) -> str:
        if not skill_ids:
            return ""
        result = await self._db.execute(
            select(SkillModel).where(
                SkillModel.skill_id.in_([str(s) for s in skill_ids]),
                SkillModel.is_active == True,  # noqa: E712
            )
        )
        skills = [
            Skill(
                id=m.id, skill_id=m.skill_id, name=m.name, description=m.description,
                prompt=m.prompt, tool_definition=m.tool_definition, icon=m.icon,
                category=m.category, is_active=m.is_active, is_builtin=m.is_builtin,
                created_at=m.created_at, updated_at=m.updated_at,
            )
            for m in result.scalars().all()
        ]
        if not skills:
            return ""
        from omichub.application.services.skill_service import SkillService
        return SkillService.build_skills_prompt(skills)

    @staticmethod
    def _parse_uuid(value: Any) -> uuid.UUID | None:
        if isinstance(value, uuid.UUID):
            return value
        try:
            return uuid.UUID(str(value))
        except (ValueError, AttributeError, TypeError):
            return None

    # --- DTO ---

    @staticmethod
    def _to_dto(a: AgentTemplateModel) -> AgentTemplateDTO:
        return AgentTemplateDTO(
            agent_id=a.agent_id, name=a.name, description=a.description,
            avatar=a.avatar, color=a.color, category=a.category,
            model_id=a.model_id, model_name=a.model_name, model_engine=a.model_engine,
            system_prompt=a.system_prompt, welcome_message=a.welcome_message,
            mcp_ids=list(a.mcp_ids or []), skill_ids=list(a.skill_ids or []),
            temperature=a.temperature, max_tokens=a.max_tokens,
            is_builtin=a.is_builtin, is_active=a.is_active, is_default=a.is_default,
            created_at=a.created_at, updated_at=a.updated_at,
        )

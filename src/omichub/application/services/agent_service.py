"""Agent 应用服务 — 模板 CRUD、内置 Agent 初始化、调度上下文组装

调度中枢调用 ``assemble_context(agent_id)`` 拿到一次 LLM 请求所需的全部拼装件：
绑定的模型配置、系统提示词（含技能 prompt 后缀）、OpenAI tools、MCP server 实体。
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
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


def _generate_agent_id(name: str) -> str:
    """根据名称生成唯一 agent_id"""
    base = re.sub(r"[^a-z0-9\u4e00-\u9fa5]+", "-", name.strip().lower()).strip("-") or "agent"
    suffix = uuid.uuid4().hex[:6]
    return f"{base}-{suffix}"


@dataclass
class AgentContext:
    """调度中枢组装出的一次请求上下文"""

    agent: AgentTemplateModel
    model_config: AIProviderConfigModel | None
    system_prompt: str
    tools: list[dict[str, Any]] = field(default_factory=list)
    mcp_servers: list[MCPServer] = field(default_factory=list)
    features: dict[str, Any] = field(default_factory=dict)
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
                "avatar": cfg.get("avatar", "\U0001f916"),
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
        query = query.order_by(AgentTemplateModel.is_default.desc(), AgentTemplateModel.created_at)
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

    async def update_agent(self, agent_id: str, req: UpdateAgentRequest) -> AgentTemplateDTO:
        agent = await self.get_agent(agent_id)
        if not agent:
            raise NotFoundError("Agent 不存在")
        try:
            data = req.model_dump(exclude_unset=True)
            if data.get("is_default"):
                await self._clear_other_defaults()
            self._normalize_json_lists(data)
            await self._validate_model_id(data)
            await self._sync_model_labels(data)
            for key, value in data.items():
                setattr(agent, key, value)
            await self._db.flush()
            await self._db.refresh(agent)
            return self._to_dto(agent)
        except IntegrityError as exc:
            await self._db.rollback()
            raise BusinessError("绑定的模型配置不存在或数据冲突，请检查模型选择") from exc
        except SQLAlchemyError as exc:
            await self._db.rollback()
            import logging

            logging.getLogger(__name__).exception(f"更新 Agent {agent_id} 数据库错误: {exc}")
            raise BusinessError("保存 Agent 时数据库出错，请稍后重试或联系管理员") from exc

    async def create_agent(self, req: CreateAgentRequest) -> AgentTemplateDTO:
        agent_id = req.agent_id.strip() if req.agent_id else ""
        if not agent_id:
            agent_id = _generate_agent_id(req.name)
        if await self.get_agent(agent_id) is not None:
            raise BusinessError(f"Agent ID '{agent_id}' 已存在")
        try:
            data = req.model_dump()
            data["agent_id"] = agent_id
            data.pop("is_builtin", None)
            self._normalize_json_lists(data)
            await self._validate_model_id(data)
            await self._sync_model_labels(data)
            agent = AgentTemplateModel(**data)
            self._db.add(agent)
            await self._db.flush()
            await self._db.refresh(agent)
            return self._to_dto(agent)
        except IntegrityError as exc:
            await self._db.rollback()
            raise BusinessError("绑定的模型配置不存在或数据冲突，请检查模型选择") from exc
        except SQLAlchemyError as exc:
            await self._db.rollback()
            import logging

            logging.getLogger(__name__).exception(f"创建 Agent {agent_id} 数据库错误: {exc}")
            raise BusinessError("创建 Agent 时数据库出错，请稍后重试或联系管理员") from exc

    @staticmethod
    def _normalize_json_lists(data: dict[str, Any]) -> None:
        """把前端可能传 null 的数组字段归一为 []，避免 ORM 写入 JSONB null 后与默认值不一致。"""
        for key in ("mcp_ids", "skill_ids"):
            if key in data and data[key] is None:
                data[key] = []

    async def _validate_model_id(self, data: dict[str, Any]) -> None:
        """校验 model_id 指向的 provider 真实存在且已启用，避免数据库 FK 500 或调用失败。"""
        model_id = data.get("model_id")
        if model_id is None:
            return
        result = await self._db.execute(
            select(AIProviderConfigModel.id).where(
                AIProviderConfigModel.id == model_id,
                AIProviderConfigModel.is_active == True,  # noqa: E712
            )
        )
        if result.scalar_one_or_none() is None:
            raise BusinessError("绑定的模型配置不存在、已被删除或未启用，请重新选择模型")

    async def _sync_model_labels(self, data: dict[str, Any]) -> None:
        """根据 model_id 同步 model_engine / model_name，确保展示与调用一致。"""
        model_id = data.get("model_id")
        if model_id is None:
            data["model_engine"] = ""
            data["model_name"] = ""
            return
        result = await self._db.execute(
            select(AIProviderConfigModel).where(
                AIProviderConfigModel.id == model_id,
                AIProviderConfigModel.is_active == True,  # noqa: E712
            )
        )
        provider = result.scalar_one_or_none()
        if provider is not None:
            data["model_engine"] = provider.model
            data["model_name"] = provider.name
        else:
            # 校验已通过时这里不应发生；保留兜底，避免空指针
            data["model_engine"] = ""
            data["model_name"] = ""

    async def delete_agent(self, agent_id: str) -> bool:
        agent = await self.get_agent(agent_id)
        if not agent:
            raise NotFoundError("Agent 不存在")
        if agent.is_builtin:
            # 内置 Agent 软删除：若其是默认助手，先转移默认状态
            if agent.is_default:
                successor = await self._find_default_successor(agent.category, agent.agent_id)
                if successor is not None:
                    successor.is_default = True
                agent.is_default = False
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

        new_active = not agent.is_active
        if not new_active and agent.is_default:
            # 停用默认 Agent 前，需将默认状态转移给同分类其他启用 Agent
            successor = await self._find_default_successor(agent.category, agent.agent_id)
            if successor is None:
                raise BusinessError(
                    "当前分类至少需要保留一个启用的 Agent，请先创建或启用其他 Agent 再停用默认助手"
                )
            successor.is_default = True
            agent.is_default = False

        agent.is_active = new_active
        await self._db.flush()
        await self._db.refresh(agent)
        return self._to_dto(agent)

    async def _find_default_successor(
        self, category: str, exclude_agent_id: str
    ) -> AgentTemplateModel | None:
        """查找同分类下可接替默认状态的其他启用 Agent，按创建时间优先取最新的。"""
        result = await self._db.execute(
            select(AgentTemplateModel)
            .where(
                AgentTemplateModel.category == category,
                AgentTemplateModel.is_active == True,  # noqa: E712
                AgentTemplateModel.agent_id != exclude_agent_id,
            )
            .order_by(AgentTemplateModel.created_at.desc())
        )
        return result.scalars().first()

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
                agent=agent,
                model_config=None,
                system_prompt=agent.system_prompt,
            )

        # 2. 收集绑定的 MCP server 及其工具，转成 OpenAI tools
        mcp_servers: list[MCPServer] = []
        tools: list[dict[str, Any]] = []
        mcp_uuids: list[uuid.UUID] = [
            u for u in (self._parse_uuid(mid) for mid in (agent.mcp_ids or [])) if u is not None
        ]
        if mcp_uuids:
            mcp_servers = await self._mcp_repo.get_by_ids(mcp_uuids)
            for server in mcp_servers:
                for t in server.tools:
                    tools.append(
                        {
                            "type": "function",
                            "function": {
                                "name": t.tool_name,
                                "description": t.description or "",
                                "parameters": t.input_schema
                                or {"type": "object", "properties": {}},
                            },
                        }
                    )

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
            features=dict(agent.features or {}),
            temperature=agent.temperature,
            max_tokens=agent.max_tokens,
        )

    async def _resolve_model(self, model_id: uuid.UUID | None) -> AIProviderConfigModel | None:
        """严格按 Agent 绑定的 model_id 解析模型，避免 fallback 导致调用与设置不一致。"""
        if model_id is None:
            return None
        result = await self._db.execute(
            select(AIProviderConfigModel).where(
                AIProviderConfigModel.id == model_id,
                AIProviderConfigModel.is_active == True,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

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
                created_at=m.created_at,
                updated_at=m.updated_at,
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
            agent_id=a.agent_id,
            name=a.name,
            description=a.description,
            avatar=a.avatar,
            color=a.color,
            category=a.category,
            model_id=a.model_id,
            model_name=a.model_name,
            model_engine=a.model_engine,
            system_prompt=a.system_prompt,
            welcome_message=a.welcome_message,
            mcp_ids=list(a.mcp_ids or []),
            skill_ids=list(a.skill_ids or []),
            features=dict(a.features or {}),
            temperature=a.temperature,
            max_tokens=a.max_tokens,
            is_builtin=a.is_builtin,
            is_active=a.is_active,
            is_default=a.is_default,
            created_at=a.created_at,
            updated_at=a.updated_at,
        )

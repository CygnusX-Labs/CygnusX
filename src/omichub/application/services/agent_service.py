"""Agent 应用服务 — 模板 CRUD、内置 Agent 初始化、调度上下文组装

调度中枢调用 ``assemble_context(agent_id)`` 拿到一次 LLM 请求所需的全部拼装件：
绑定的模型配置、系统提示词（含技能 prompt 后缀）、OpenAI tools、MCP server 实体。
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from omichub.application.schemas.agent import (
    AgentTemplateDTO,
    CreateAgentRequest,
    UpdateAgentRequest,
)
from omichub.application.services.site_settings_service import SiteSettingsService
from omichub.application.services.agent_handoff_service import HANDOFF_TOOL_NAME
from omichub.core.config import get_settings
from omichub.core.exceptions import BusinessError, NotFoundError
from omichub.domain.mcp.entities import MCPServer, MCPToolRegistry
from omichub.domain.mcp.value_objects import ServerStatus, Transport
from omichub.domain.skill.entities import Skill
from omichub.infrastructure.config.agent_loader import load_agent_configs
from omichub.infrastructure.database.models.agent import AgentTemplateModel
from omichub.infrastructure.database.models.ai_provider import AIProviderConfigModel
from omichub.infrastructure.database.models.skill import SkillModel
from omichub.infrastructure.database.repositories.mcp_repository import (
    SqlAlchemyMCPServerRepository,
)
from omichub.infrastructure.mcp.conda_meta_preset import CONDA_META_MCP_SERVER_ID
from omichub.infrastructure.mcp.presets import (
    OMICHUB_PLATFORM_SERVER_ID,
    OMICHUB_TOOLS_SERVER_ID,
    OMICHUB_TOOLS_SERVER_NAME,
    WORKSPACE_FILES_SYSTEM_PROMPT_SUFFIX,
    get_preset_by_name,
)
from omichub.tools.schema_loader import schema_loader

AGENTTEAMS_CASE_SYSTEM_PROMPT_SUFFIX = """## AgentTeams 协作 Case

你可以使用 `create_agentteams_case` 创建 AgentTeams 协作 Case。它适用于需要跨角色协作、
人工审批、长耗时流程执行、质量闸门或正式交付验收的任务。

- 普通问答、参数解释、一次性小任务和轻量并行任务不要创建 Case。
- 目标、项目、流程或交付物不明确时先澄清；不得默认创建 Case。
- 仅当用户已明确同意创建后才调用该工具；工具会展示确认卡，用户确认后再以原参数
  携带 `_confirmed: true` 调用。
- 若请求来自多专家会诊，须把会诊事件提供的 `consultation_id` 和 `consultation_summary`
  分别填入 `origin_consultation_id`、`consultation_summary`，以保留 Case 来源追溯。
- 创建成功后告知用户打开协作 Case，继续完成预检、审批和交付验收。
"""

AGENT_COMMUNICATION_SYSTEM_PROMPT_SUFFIX = """## 平台沟通与执行规范

- 默认使用专业、自然、克制的中文：先说明当前结论或状态，再给出依据和下一步。
- 不使用卖萌语气、颜文字或无必要的 emoji；不要以“请上传数据，我来一步步操作”一类
  空泛话术收尾。缺少输入时，明确列出缺少的文件、字段、分组或参数，并说明如何提供。
- 先检查当前会话已经给出的信息和可用工作区文件；能通过工具确认的事实必须调用工具，
  工具返回后只陈述真实结果。已完成、待确认和未能执行的事项必须明确区分。
- 用户要求执行分析或产出文件时，先给出简短执行计划；完成后交付结果路径、关键参数和
  可复现的下一步。没有执行就不要暗示已经完成。
- 任务不属于当前职责且系统提供了转交工具时，选择最合适的 Agent 并转交；不要让用户
  自己在助手列表中猜测该选谁。
"""

ROUTER_COMMUNICATION_SYSTEM_PROMPT_SUFFIX = """## 路由输出纪律

- 你的职责是理解意图、选择可用专家并输出规定的路由 JSON；不要执行分析、不要生成工作台
  指令，也不要向用户输出解释性话术。
- 不使用 emoji、寒暄或“请上传数据”式兜底。输入信息不足时仍须根据当前可用目录选择最
  合适的首接 Agent，并将缺失项交由该 Agent 继续澄清。
- 运行时提供的 Agent 目录是唯一有效候选集；不得引用目录外 Agent，也不得让前端规则替你
  做领域判断。
"""


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
    skills: list[Skill] = field(default_factory=list)
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

        configured_skill_ids = {
            str(skill_id).strip()
            for cfg in yaml_configs
            for skill_id in (cfg.get("skill_ids") or [])
            if str(skill_id).strip()
        }
        await self._ensure_configured_marketplace_skills(configured_skill_ids)

        # 预加载所有启用的模型配置，按 name 建索引
        model_result = await self._db.execute(
            select(AIProviderConfigModel).where(
                AIProviderConfigModel.is_active == True  # noqa: E712
            )
        )
        active_models = list(model_result.scalars().all())
        models_by_name = {m.name: m for m in active_models}
        models_by_id = {m.id: m for m in active_models}
        default_model = next((model for model in active_models if model.is_default), None)
        fallback_model = default_model or (active_models[0] if active_models else None)

        for cfg in yaml_configs:
            existing = await self.get_agent(cfg["agent_id"])
            if existing is not None:
                # 内置 Agent 的 YAML 是平台能力声明的来源；同步 features，
                # 但不覆盖管理员可能调整过的模型、提示词或绑定关系。
                if existing.is_builtin:
                    existing_features = dict(existing.features or {})
                    existing_features.update(dict(cfg.get("features") or {}))
                    if cfg.get("studio"):
                        existing_features["studio"] = cfg["studio"]
                    else:
                        existing_features.pop("studio", None)
                    existing.features = existing_features
                    configured_mcp_ids = [
                        str(value) for value in (existing.mcp_ids or []) if self._parse_uuid(value)
                    ]
                    # 旧版本已落库的内置 Agent 可能没有平台 MCP；回填工作区文件工具，
                    # 不覆盖管理员额外绑定的 MCP。
                    if (
                        not configured_mcp_ids
                        or str(OMICHUB_TOOLS_SERVER_ID) in configured_mcp_ids
                    ) and str(OMICHUB_PLATFORM_SERVER_ID) not in configured_mcp_ids:
                        configured_mcp_ids.append(str(OMICHUB_PLATFORM_SERVER_ID))
                        existing.mcp_ids = configured_mcp_ids
                    # 同路径回填 conda-meta-mcp（装包前查 conda 元数据）：幂等追加，
                    # 不动管理员额外绑定的 MCP。
                    if str(CONDA_META_MCP_SERVER_ID) not in configured_mcp_ids:
                        configured_mcp_ids.append(str(CONDA_META_MCP_SERVER_ID))
                        existing.mcp_ids = configured_mcp_ids
                    configured_skills = [
                        str(skill_id).strip()
                        for skill_id in (cfg.get("skill_ids") or [])
                        if str(skill_id).strip()
                    ]
                    if configured_skills:
                        existing_skill_ids = [
                            str(skill_id).strip()
                            for skill_id in (existing.skill_ids or [])
                            if str(skill_id).strip()
                        ]
                        existing.skill_ids = list(
                            dict.fromkeys([*existing_skill_ids, *configured_skills])
                        )

                    if existing.model_id not in models_by_id:
                        configured_model = models_by_name.get(str(cfg.get("model") or ""))
                        target_model = configured_model or fallback_model
                    else:
                        target_model = None
                    if target_model is not None:
                        existing.model_id = target_model.id
                        existing.model_name = target_model.name
                        existing.model_engine = target_model.model
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
            mcp_ids = cfg.get("mcp_ids", [])
            if not mcp_ids:
                mcp_ids = [
                    str(OMICHUB_TOOLS_SERVER_ID),
                    str(OMICHUB_PLATFORM_SERVER_ID),
                    str(CONDA_META_MCP_SERVER_ID),
                ]
            # 统一功能开关：yaml features 原样保留，studio 段归入 features["studio"]，
            # 不新增列（调度中枢经 AgentContext.features 读取）
            features = dict(cfg.get("features") or {})
            if cfg.get("studio"):
                features["studio"] = cfg["studio"]
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
                "mcp_ids": mcp_ids,
                "skill_ids": cfg.get("skill_ids", []),
                "features": features,
                "temperature": cfg.get("temperature", 0.7),
                "max_tokens": cfg.get("max_tokens", 4096),
                "is_builtin": True,
                "is_active": True,
            }
            self._db.add(AgentTemplateModel(**agent_data))
        await self._db.flush()

    async def _ensure_configured_marketplace_skills(self, skill_ids: set[str]) -> None:
        """安装 YAML 声明且存在于内置市场的 Skill，保留外部 Skill 的管理方式。"""
        if not skill_ids:
            return

        from omichub.application.services.skill_import_service import SkillImportService
        from omichub.core.config import get_settings

        marketplace = get_settings().skill_marketplace_dir
        available_ids = {
            skill_id
            for skill_id in skill_ids
            if (Path(marketplace) / skill_id / "SKILL.md").is_file()
        }
        if not available_ids:
            return

        result = await self._db.execute(
            select(SkillModel.skill_id).where(SkillModel.skill_id.in_(available_ids))
        )
        installed_ids = {str(skill_id) for skill_id in result.scalars().all()}
        installer = SkillImportService(self._db)
        for skill_id in sorted(available_ids - installed_ids):
            try:
                await installer.install_marketplace(skill_id)
            except BusinessError as exc:
                logging.getLogger(__name__).warning(
                    "内置 Agent Skill 自动安装失败 %s: %s", skill_id, exc
                )

    # --- 查询 ---

    async def list_agents(self, active_only: bool = False) -> list[AgentTemplateDTO]:
        await self.ensure_builtin_agents()
        await self._reconcile_model_bindings()
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
        await self._reconcile_model_bindings()
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
            # 部分更新未提交 model_id 时，必须保留既有绑定及其展示标签。
            if "model_id" in data:
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

    async def _reconcile_model_bindings(self) -> None:
        """修复历史失效绑定，并让助手展示标签与当前 Provider 配置保持一致。"""
        providers_result = await self._db.execute(
            select(AIProviderConfigModel)
            .where(AIProviderConfigModel.is_active == True)  # noqa: E712
            .order_by(
                AIProviderConfigModel.is_default.desc(),
                AIProviderConfigModel.updated_at.desc(),
            )
        )
        active_providers = list(providers_result.scalars().all())
        providers_by_id = {provider.id: provider for provider in active_providers}
        fallback_provider = active_providers[0] if active_providers else None

        agents_result = await self._db.execute(
            select(AgentTemplateModel).where(
                AgentTemplateModel.model_id.is_not(None) | (AgentTemplateModel.is_builtin == True)  # noqa: E712
            )
        )
        changed = False
        for agent in agents_result.scalars().all():
            provider = providers_by_id.get(agent.model_id) or fallback_provider
            if provider is None:
                if agent.model_id is not None or agent.model_name or agent.model_engine:
                    agent.model_id = None
                    agent.model_name = ""
                    agent.model_engine = ""
                    changed = True
                continue

            if (
                agent.model_id != provider.id
                or agent.model_name != provider.name
                or agent.model_engine != provider.model
            ):
                agent.model_id = provider.id
                agent.model_name = provider.name
                agent.model_engine = provider.model
                changed = True

        if changed:
            await self._db.flush()

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
        await self._reconcile_model_bindings()
        agent = await self.get_agent(agent_id)
        if agent is None or not agent.is_active:
            return None

        # 1. 解析绑定模型：优先 agent.model_id，否则回落到默认/首个启用模型
        model_config = await self._resolve_model(agent.model_id)
        if model_config is None:
            return AgentContext(
                agent=agent,
                model_config=None,
                system_prompt=self._append_communication_contract(agent.system_prompt, agent),
            )

        # 2. 收集绑定的 MCP server 及其工具，转成 OpenAI tools
        mcp_servers: list[MCPServer] = []
        tools: list[dict[str, Any]] = []
        tool_pack_config = self._tool_pack_config(agent.features or {})
        mcp_uuids: list[uuid.UUID] = [
            u for u in (self._parse_uuid(mid) for mid in (agent.mcp_ids or [])) if u is not None
        ]
        omichub_selected = OMICHUB_TOOLS_SERVER_ID in mcp_uuids
        other_uuids = [u for u in mcp_uuids if u != OMICHUB_TOOLS_SERVER_ID]
        if other_uuids:
            mcp_servers = await self._mcp_repo.get_by_ids(other_uuids)
            for server in mcp_servers:
                allowed_names = tool_pack_config["mcp_tools"].get(str(server.id))
                for t in server.tools:
                    if allowed_names and t.tool_name not in allowed_names:
                        continue
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

        # 内置 preset 可能在应用启动并发初始化期间尚未落库；使用代码定义的
        # preset 作为运行时兜底，确保已绑定平台 MCP 的 Agent 不会丢失工具。
        if OMICHUB_PLATFORM_SERVER_ID in mcp_uuids and not any(
            server.id == OMICHUB_PLATFORM_SERVER_ID for server in mcp_servers
        ):
            platform_preset = get_preset_by_name("omichub-platform")
            if platform_preset is not None:
                allowed_platform_names = tool_pack_config["mcp_tools"].get(
                    str(OMICHUB_PLATFORM_SERVER_ID)
                )
                preset_tools = [
                    tool
                    for tool in platform_preset["tools"]
                    if not allowed_platform_names or tool["name"] in allowed_platform_names
                ]
                platform_tools = [
                    MCPToolRegistry(
                        tool_name=tool["name"],
                        description=tool["description"],
                        input_schema=tool["inputSchema"],
                        server_id=OMICHUB_PLATFORM_SERVER_ID,
                    )
                    for tool in preset_tools
                ]
                mcp_servers.append(
                    MCPServer(
                        id=OMICHUB_PLATFORM_SERVER_ID,
                        name="omichub-platform",
                        description=platform_preset["description"],
                        transport=Transport.BUILTIN,
                        status=ServerStatus.ONLINE,
                        is_enabled=True,
                        is_preset=True,
                        tools=platform_tools,
                    )
                )
                tools.extend(
                    {
                        "type": "function",
                        "function": {
                            "name": tool.tool_name,
                            "description": tool.description,
                            "parameters": tool.input_schema
                            or {"type": "object", "properties": {}},
                        },
                    }
                    for tool in platform_tools
                )

        # 2.5 自动注入 omichub-tools builtin preset（显式选中，或为空时保持默认）
        omichub_tools_server = self._build_omichub_tools_server()
        if omichub_tools_server and (omichub_selected or not mcp_uuids):
            mcp_servers.append(omichub_tools_server)
            builtin_tools = schema_loader.to_openai_tools()
            allowed_builtin_names = tool_pack_config["builtin_tools"]
            if allowed_builtin_names:
                builtin_tools = [
                    tool
                    for tool in builtin_tools
                    if tool.get("function", {}).get("name") in allowed_builtin_names
                ]
            builtin_tools = self._filter_runtime_builtin_tools(
                builtin_tools,
                agentteams_chat_entry_enabled=await self._agentteams_chat_entry_enabled(),
            )
            tools.extend(builtin_tools)

        # 3. 系统提示词 = Agent 设定 + 技能 L1 索引 + omichub-tools 清单。
        # 技能采用三层渐进式披露：L1 仅注入 name+description 索引（每技能约 100 tokens）；
        # L2 正文由模型命中后调用 use_skill 工具按需加载；L3 references/assets 用
        # skill_resource 按需读取。Studio 会话另用结构化 capability_catalog 机制。
        system_prompt = agent.system_prompt
        skills = await self._load_skills(agent.skill_ids or [])
        skill_index = self._build_skills_index(skills)
        if skill_index:
            system_prompt = f"{system_prompt}\n\n{skill_index}" if system_prompt else skill_index
        if skills:
            from omichub.domain.skill.services import build_skill_tools

            tools.extend(build_skill_tools(skills))
        if omichub_tools_server and (omichub_selected or not mcp_uuids):
            tool_hint = schema_loader.build_system_hint(
                {
                    str(tool.get("function", {}).get("name") or "")
                    for tool in builtin_tools
                }
            )
            if tool_hint:
                system_prompt = f"{system_prompt}\n\n{tool_hint}" if system_prompt else tool_hint
        if self._has_builtin_tool(builtin_tools, "create_agentteams_case"):
            system_prompt = (
                f"{system_prompt}\n\n{AGENTTEAMS_CASE_SYSTEM_PROMPT_SUFFIX}"
                if system_prompt
                else AGENTTEAMS_CASE_SYSTEM_PROMPT_SUFFIX
            )
        if any(server.id == OMICHUB_PLATFORM_SERVER_ID for server in mcp_servers):
            system_prompt = (
                f"{system_prompt}\n\n{WORKSPACE_FILES_SYSTEM_PROMPT_SUFFIX}"
                if system_prompt
                else WORKSPACE_FILES_SYSTEM_PROMPT_SUFFIX
            )
        if self._has_builtin_tool(builtin_tools, HANDOFF_TOOL_NAME):
            handoff_catalog = await self._build_handoff_catalog(agent)
            if handoff_catalog:
                system_prompt = f"{system_prompt}\n\n{handoff_catalog}" if system_prompt else handoff_catalog
        system_prompt = self._append_communication_contract(system_prompt, agent)

        return AgentContext(
            agent=agent,
            model_config=model_config,
            system_prompt=system_prompt,
            tools=tools,
            mcp_servers=mcp_servers,
            skills=skills,
            features=dict(agent.features or {}),
            temperature=agent.temperature,
            max_tokens=agent.max_tokens,
        )

    @staticmethod
    def _append_communication_contract(system_prompt: str, agent: AgentTemplateModel) -> str:
        """将统一沟通规范注入所有运行时 Agent，兼容数据库中已存在的内置提示词。"""
        features = agent.features or {}
        suffix = (
            ROUTER_COMMUNICATION_SYSTEM_PROMPT_SUFFIX
            if features.get("router")
            else AGENT_COMMUNICATION_SYSTEM_PROMPT_SUFFIX
        )
        return f"{system_prompt}\n\n{suffix}" if system_prompt else suffix

    async def _agentteams_chat_entry_enabled(self) -> bool:
        settings = get_settings()
        return (
            settings.agentteams_chat_entry_enabled
            or await SiteSettingsService(self._db).is_agentteams_chat_entry_enabled()
        )

    @staticmethod
    def _filter_runtime_builtin_tools(
        tools: list[dict[str, Any]], *, agentteams_chat_entry_enabled: bool
    ) -> list[dict[str, Any]]:
        if agentteams_chat_entry_enabled:
            return tools
        return [
            tool
            for tool in tools
            if tool.get("function", {}).get("name") != "create_agentteams_case"
        ]

    @staticmethod
    def _has_builtin_tool(tools: list[dict[str, Any]], tool_name: str) -> bool:
        return any(tool.get("function", {}).get("name") == tool_name for tool in tools)

    async def _build_handoff_catalog(self, source: AgentTemplateModel) -> str:
        handoff_config = dict((source.features or {}).get("handoff") or {})
        allowed_targets = {str(item) for item in handoff_config.get("allowed_targets", [])}
        if not allowed_targets:
            return ""
        allow_all_active_targets = "*" in allowed_targets
        result = await self._db.execute(
            select(AgentTemplateModel)
            .where(AgentTemplateModel.is_active == True)  # noqa: E712
            .order_by(AgentTemplateModel.category, AgentTemplateModel.name)
        )
        catalog = [
            {
                "agent_id": candidate.agent_id,
                "name": candidate.name,
                "description": candidate.description,
                "category": candidate.category,
            }
            for candidate in result.scalars().all()
            if candidate.agent_id != source.agent_id
            and not (candidate.features or {}).get("router")
            and (allow_all_active_targets or candidate.agent_id in allowed_targets)
        ]
        if not catalog:
            return ""
        return (
            "## 当前可转交的 Agent（运行时目录）\n\n"
            f"{json.dumps(catalog, ensure_ascii=False)}\n\n"
            "当用户任务不属于你的职责且目标明确时，必须调用 `transfer_to_agent` 转交给目录中的目标。"
            "不要让用户手动挑选 Agent，也不要编造目录外的 Agent。"
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

    async def resolve_model_id_for_agent(
        self, agent: AgentTemplateModel
    ) -> uuid.UUID | None:
        """返回 Agent 当前可用的模型 ID，并修复内置 Agent 的历史空绑定。"""
        await self._reconcile_model_bindings()
        model = await self._resolve_model(agent.model_id)
        return model.id if model is not None else None

    async def _load_skills(self, skill_ids: list[Any]) -> list[Skill]:
        if not skill_ids:
            return []
        from omichub.application.services.skill_service import SkillService

        result = await self._db.execute(
            select(SkillModel).where(
                SkillModel.skill_id.in_([str(skill_id) for skill_id in skill_ids]),
                SkillModel.is_active == True,  # noqa: E712
            )
        )
        return [SkillService._to_entity(model) for model in result.scalars().all()]

    @staticmethod
    def _build_skills_prompt(skills: list[Skill]) -> str:
        if not skills:
            return ""
        from omichub.application.services.skill_service import SkillService

        return SkillService.build_skills_prompt(skills)

    @staticmethod
    def _build_skills_index(skills: list[Skill]) -> str:
        """L1：仅 name+description 元数据索引，正文经 use_skill 按需加载"""
        if not skills:
            return ""
        from omichub.application.services.skill_service import SkillService

        return SkillService.build_skills_index(skills)

    async def _build_skill_prompt(self, skill_ids: list[Any]) -> str:
        """兼容旧调用方；新代码优先使用结构化 skills。"""
        return self._build_skills_prompt(await self._load_skills(skill_ids))

    @staticmethod
    def _build_omichub_tools_server() -> MCPServer | None:
        """构造虚拟的 omichub-tools builtin MCP Server。"""
        tools = schema_loader.list_tools()
        if not tools:
            return None
        return MCPServer(
            id=OMICHUB_TOOLS_SERVER_ID,
            name=OMICHUB_TOOLS_SERVER_NAME,
            description="OmicHub 生信工具箱 MCP",
            transport=Transport.BUILTIN,
            is_enabled=True,
            is_preset=True,
            status=ServerStatus.ONLINE,
            tools=[
                MCPToolRegistry(
                    tool_name=t.name,
                    description=t.description,
                    input_schema=t.input_schema,
                    server_id=OMICHUB_TOOLS_SERVER_ID,
                )
                for t in tools
            ],
        )

    @staticmethod
    def _tool_pack_config(features: dict[str, Any]) -> dict[str, Any]:
        """汇总 YAML 工具包的内置/MCP 工具白名单。"""
        builtin_tools: set[str] = set()
        mcp_tools: dict[str, set[str]] = {}
        for pack in features.get("tool_packs", []) if isinstance(features, dict) else []:
            if not isinstance(pack, dict):
                continue
            builtin_tools.update(
                str(tool).strip()
                for tool in pack.get("builtin_tools", [])
                if str(tool).strip()
            )
            for server_id, tool_names in (pack.get("mcp_tools") or {}).items():
                if not isinstance(tool_names, list):
                    continue
                names = {
                    str(tool).strip() for tool in tool_names if str(tool).strip()
                }
                if names:
                    mcp_tools.setdefault(str(server_id), set()).update(names)
        return {"builtin_tools": builtin_tools, "mcp_tools": mcp_tools}

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

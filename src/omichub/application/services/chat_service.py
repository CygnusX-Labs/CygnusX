"""Cherry Studio 架构聊天业务服务

核心职责：
1. 会话 CRUD（创建、查询、更新、软删除）
2. 消息持久化（用户消息 + AI 消息）
3. SSE 流式聊天编排（调用 LLM + 实时更新数据库）
4. 内置助手管理（初始化预设助手）
"""

from __future__ import annotations

import contextlib
import ipaddress
import json
import re
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import anyio
import httpx
from loguru import logger
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from omichub.application.schemas.chat import (
    ChatAssistantDTO,
    ChatMessageDTO,
    ChatSearchContentMatchDTO,
    ChatSessionDTO,
    ChatSessionSearchDTO,
    UpdateAssistantRequest,
)
from omichub.application.services.agent_handoff_service import (
    HANDOFF_TOOL_NAME,
    AgentHandoffService,
    extract_handoff_directive,
)
from omichub.application.services.mas_plan_adapter import (
    MAS_PLAN_PREVIEW_PROMPT_SUFFIX,
    MAS_PLAN_PREVIEW_TOOL_NAME,
    MAS_PLAN_PREVIEW_TOOL_SCHEMA,
    MASPlanPreviewAdapter,
)
from omichub.application.services.parallel_subagent_service import (
    PARALLEL_SUBAGENTS_TOOL_NAME,
)
from omichub.application.services.search_provider_service import SearchProviderService
from omichub.application.services.studio_approval_service import (
    APPROVAL_REQUIRED_TOOLS,
    APPROVAL_TTL_SECONDS,
    get_studio_approval_service,
)
from omichub.application.services.studio_capabilities import (
    CAPABILITY_LIST_TOOL,
    CAPABILITY_LOAD_TOOL,
    CAPABILITY_TOOL_NAMES,
    CAPABILITY_TOOL_SCHEMAS,
    CapabilityState,
    audit_event,
    load_capability,
)
from omichub.application.services.studio_capabilities import (
    catalog as capability_catalog,
)
from omichub.application.services.studio_capabilities import (
    loaded_servers as loaded_capability_servers,
)
from omichub.application.services.studio_capabilities import (
    mcp_tools as capability_mcp_tools,
)
from omichub.application.services.studio_capabilities import (
    normalize_state as normalize_capability_state,
)
from omichub.application.services.studio_capabilities import (
    render_prompt as render_capability_prompt,
)
from omichub.application.services.studio_tools import (
    ASK_USER_TOOL_SCHEMA,
    STUDIO_SYSTEM_PROMPT_SUFFIX,
    STUDIO_TOOL_NAMES,
    STUDIO_TOOL_SCHEMAS,
    normalize_plan_steps,
    stream_studio_tool,
)
from omichub.core.config import get_settings
from omichub.core.exceptions import BusinessError, NotFoundError
from omichub.core.telemetry import get_meter, get_tracer
from omichub.domain.skill.services import (
    SKILL_RESOURCE_TOOL_NAME,
    SKILL_TOOL_NAMES,
    USE_SKILL_TOOL_NAME,
)
from omichub.infrastructure.ai_provider.openai_compatible import (
    ChatChunk,
    merge_token_usage,
    provider_manager,
)
from omichub.infrastructure.config.prompt_loader import get_prompt
from omichub.infrastructure.database.models.ai_provider import AIProviderConfigModel
from omichub.infrastructure.database.models.chat import (
    ChatAssistantModel,
    ChatHandoffEventModel,
    ChatMessageModel,
    ChatSessionModel,
)
from omichub.middleware.trace_context import session_id_var
from omichub.tools.schema_loader import schema_loader

if TYPE_CHECKING:
    from omichub.application.services.agent_service import AgentContext

# ===== 技能 / Agent 编排遥测指标（全局代理 meter，未初始化时为 noop）=====
_chat_meter = get_meter("omichub.chat")
_skill_count = _chat_meter.create_counter("skill.execute.count", description="技能工具执行次数")
_skill_duration = _chat_meter.create_histogram(
    "skill.execute.duration", unit="ms", description="技能工具执行耗时"
)
_agent_duration = _chat_meter.create_histogram(
    "agent.run.duration", unit="ms", description="Agent 单次运行耗时"
)

DEFAULT_SYSTEM_PROMPT = get_prompt("agents.general")

MULTI_AGENT_SYSTEM_PROMPT_SUFFIX = """## Multi-agent 协作模式

当前会话已开启 multi-agent 协作。对于可拆成 2–5 个彼此独立的专业子任务，应优先调用
`parallel_subagents` 并行分派、等待汇总后给出统一结论；不要为了简单问答而无意义拆分。

当用户明确要求跨角色协作、人工审批、长耗时流程执行或可审计交付时，可以提出创建
AgentTeams Case，并在用户确认后调用 `create_agentteams_case`。"""

MULTI_AGENT_TOOL_NAMES = frozenset({PARALLEL_SUBAGENTS_TOOL_NAME, "create_agentteams_case"})

# 智能路由器 system prompt：让 router LLM 从候选专家清单中选一个最合适的
ROUTER_SYSTEM_PROMPT = """你是一个意图路由器。根据用户消息，从下面的候选专家清单中选择一个最合适的专家来回答。

候选专家（JSON 数组）：
{catalog}

规则：
1. 直接输出一行 JSON：{{"agent_id": "...", "reason": "...", "expect_handoff": false, "consult_agent_ids": [], "intent": "chat|light_collab|delivery_case", "confidence": 0.0}}。
2. 禁止输出思考过程、复述用户消息或列候选清单，第一个字符必须是 {{。
3. agent_id 必须来自候选清单；reason 用一句中文简述分派理由。
4. 当用户请求明显横跨两个以上专业阶段时，选择第一阶段最合适的专家，并将 expect_handoff 设为 true；它仅供审计，不改变本次分派。
5. delivery_case 仅用于明确要求真实流程执行且要得到报告、结果文件或可审计交付物的请求；流程咨询、参数解释、普通问答和轻量并行一律不是 delivery_case。
6. 无法判断意图时，选择通用（general）专家对应的 agent_id，intent 设为 chat，confidence 保守取低值。"""


def _extract_route_json(text: str) -> dict[str, Any] | None:
    """从 router LLM 输出中容错提取路由 JSON。

    模型可能在 JSON 前后输出思考过程，甚至多次输出 JSON（先错后对）。
    逐个尝试所有 {...} 片段，取最后一个可解析且含 agent_id 的对象。
    """
    found: dict[str, Any] | None = None
    for match in re.finditer(r"\{[^{}]*\}", text, re.DOTALL):
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("agent_id"):
            found = data
    return found


def _studio_risk_hint(tool_name: str, args: dict[str, Any]) -> str:
    """审批卡片上的单行风险提示（supervised 模式，§3.1）。"""
    if tool_name == "sandbox_execute":
        language = str(args.get("language") or "python")
        return f"将在沙盒中执行 {language} 代码"
    if tool_name == "workspace_write":
        return f"将写入工作区文件 {args.get('path') or ''}".strip()
    if tool_name == "workspace_edit":
        return f"将修改工作区文件 {args.get('path') or ''}".strip()
    if tool_name == "artifact_register":
        return f"将把产物 {args.get('path') or ''} 登记到结果报告中心".strip()
    return "该操作需要用户批准"


def _normalize_ask_questions(args: dict[str, Any]) -> list[dict[str, Any]]:
    """ask_user 参数归一化为问题列表（最多 5 个）。

    优先取 questions[]（多问题分页收集），兼容单问题 question+options；
    模型偶尔把 questions 数组序列化成 JSON 字符串传来，先尝试解析还原；
    模型未给出有效问题时兜底一个空问题，前端据此渲染自由输入，保证用户总能回复。
    """
    questions: list[dict[str, Any]] = []
    raw = args.get("questions")
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            parsed = None
        if isinstance(parsed, list):
            raw = parsed
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            q = str(item.get("question") or "").strip()
            if not q:
                continue
            opts_raw = item.get("options")
            opts = (
                [str(o) for o in opts_raw if str(o).strip()]
                if isinstance(opts_raw, list)
                else []
            )
            questions.append({"question": q, "options": opts})
    if not questions:
        single_q = str(args.get("question") or "").strip()
        opts_raw = args.get("options")
        single_opts = (
            [str(o) for o in opts_raw if str(o).strip()]
            if isinstance(opts_raw, list)
            else []
        )
        if single_q:
            questions.append({"question": single_q, "options": single_opts})
    if not questions:
        logger.warning("ask_user 调用缺少有效问题，降级为自由输入卡片，args={}", args)
        questions.append({"question": "", "options": []})
    return questions[:5]

BUILTIN_ASSISTANTS: list[dict[str, Any]] = [
    {
        "assistant_id": "general", "name": "通用助手", "description": "OmicHub 通用 AI 助手，回答各类问题",
        "system_prompt": get_prompt("agents.general"), "default_temperature": 0.7, "default_max_tokens": 2048,
        "icon": "🤖", "color": "#4f8ef7", "category": "general",
    },
    {
        "assistant_id": "rna_seq_analyst", "name": "RNA-seq 分析师", "description": "专注于 RNA-seq 差异表达分析、通路富集、可视化",
        "system_prompt": get_prompt("agents.rnaseq"), "default_temperature": 0.3, "default_max_tokens": 4096,
        "icon": "🧬", "color": "#4f8ef7", "category": "analysis",
    },
    {
        "assistant_id": "scrna_analyst", "name": "单细胞分析师", "description": "专注于单细胞转录组分析、降维聚类、细胞注释",
        "system_prompt": get_prompt("agents.scrna"), "default_temperature": 0.3, "default_max_tokens": 4096,
        "icon": "🔬", "color": "#e74c3c", "category": "analysis",
    },
    {
        "assistant_id": "code_helper", "name": "代码助手", "description": "帮助编写和调试生信分析代码（Python / R）",
        "system_prompt": get_prompt("agents.code"), "default_temperature": 0.2, "default_max_tokens": 4096,
        "icon": "💻", "color": "#f39c12", "category": "code",
    },
    {
        "assistant_id": "visualization", "name": "可视化助手", "description": "帮助创建和优化科研图表",
        "system_prompt": get_prompt("agents.visualization"), "default_temperature": 0.3, "default_max_tokens": 4096,
        "icon": "📊", "color": "#27ae60", "category": "visualization",
    },
]


WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "联网搜索，获取与用户问题相关的实时信息。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "top_n": {"type": "integer", "default": 5, "description": "返回结果数量"},
            },
            "required": ["query"],
        },
    },
}

# 知识库检索：普通聊天同样挂载（Studio 由 STUDIO_TOOL_SCHEMAS 携带），
# 让 Agent 能检索平台知识库（含用户个人笔记/实验经验文档）再作答。
KNOWLEDGE_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "knowledge_search",
        "description": (
            "检索平台知识库（含用户个人笔记与实验经验文档），返回标题、分类和短摘录。"
            "涉及单细胞/生信分析流程、参数阈值、实验经验或平台使用方法的问题，先查知识库再回答。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "知识检索关键词"},
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 8,
                    "description": "最多返回条数，缺省 5",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}

FRESHNESS_SEARCH_TRIGGERS = (
    "实时",
    "最新",
    "最近",
    "今天",
    "今日",
    "昨天",
    "明天",
    "新闻",
    "天气",
    "时事",
    "价格",
    "股价",
    "汇率",
    "文献",
    "论文",
    "研究进展",
    "研究成果",
    "临床试验",
    "指南",
    "数据库更新",
    "latest",
    "recent",
    "today",
    "news",
    "weather",
    "literature",
    "paper",
    "pubmed",
)

MEMORY_TOOL_NAMES = {
    "omichub_save_memory",
    "omichub_update_memory",
    "omichub_forget_memory",
    "omichub_search_memory",
}

MEMORY_SYSTEM_PROMPT_SUFFIX = """## 长期记忆工具

你可保存、修正、遗忘或检索当前用户自己的跨会话研究记忆。
- 仅在用户明确要求记住，或提供稳定的研究偏好、物种、参考基因组、数据类型或项目进展时使用保存工具。
- 当前对话优先于历史记忆；冲突时修正记忆。用户要求忘记时调用遗忘工具。
- 禁止保存密钥、密码、Token、原始数据内容、他人隐私或仅对本轮有效的临时细节。
"""

HANDOFF_SYSTEM_PROMPT_SUFFIX = """## Agent 转交协议
当用户当前任务已进入明确的下一专业阶段、且你已完成自己负责的部分时，可以调用
`transfer_to_agent` 将会话交给白名单中的下一位 Agent。交接必须包含已完成工作的摘要、
用户后续诉求、相关 workspace 产物和约束；不要为了回避简单问题或重复工作而转交。"""

ASK_USER_SYSTEM_PROMPT_SUFFIX = """## 用户澄清协议（强制）

当任务缺少关键信息、存在多种可行方案、或需要用户在候选项中做选择时：
- **必须**调用 `ask_user` 工具，通过弹窗 options 让用户点选作答，而不是等待用户手动输入。
- **禁止**在回复正文中用纯文本罗列"方案 1 / 方案 2"或"选项 1/2/3"，让用户回复编号或文字作答。
- `questions` 参数必须按 schema 传结构化数组，不要把 JSON 序列化成字符串。
- 选项有推荐项时放在第一位，并在选项文本中以（推荐）标注。
- 只有问题完全无法用预设选项表达时，才允许在正文直接提问。
"""

KNOWLEDGE_SEARCH_SYSTEM_PROMPT_SUFFIX = """## 知识库检索

平台知识库已收录用户的个人笔记与实验经验文档。涉及单细胞/生信分析流程、参数阈值、
实验经验或平台使用方法的问题，先调用 `knowledge_search` 检索再作答；
检索不到相关内容时如实说明，不要假装查过。"""


class ChatService:
    """聊天业务服务"""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    @staticmethod
    def _escape_like(value: str) -> str:
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    @staticmethod
    def _requires_fresh_web_search(
        query: str,
        features: dict[str, Any] | None = None,
    ) -> bool:
        """判断问题是否必须先联网核验，避免把模型记忆当作最新事实。"""
        policy = (features or {}).get("web_search", {}) if isinstance(features, dict) else {}
        if policy is False:
            return False
        policy = policy if isinstance(policy, dict) else {}
        if str(policy.get("mode") or "").lower() in {"off", "disabled"}:
            return False
        configured_triggers = policy.get("triggers", [])
        if not isinstance(configured_triggers, (list, tuple, set)):
            configured_triggers = []
        triggers = [*FRESHNESS_SEARCH_TRIGGERS, *configured_triggers]
        normalized_query = query.casefold()
        return any(str(trigger).casefold() in normalized_query for trigger in triggers if trigger)

    @staticmethod
    def _clean_session_title(value: str) -> str:
        cleaned = re.sub(r"[\"'《》「」\n\r]", "", value or "").strip()
        # 去除模型偶尔带回的前缀（如“标题：”“Title:”），让标题更干净
        cleaned = re.sub(r"^(标题|主题|title)\s*[:：]\s*", "", cleaned, flags=re.IGNORECASE)
        # 剥掉第三人称叙述前缀（如“用户想要…”“最初询问了…”），标题应是主题而非摘要
        cleaned = re.sub(
            r"^(用户|该用户|这位用户)\s*(想要|想|希望|询问|咨询|请教|请求|问|需要|要求|讨论了|了解)\s*",
            "",
            cleaned,
        )
        cleaned = re.sub(r"^(最初|一开始|首先)\s*(询问|问|咨询|提到|讨论)了?\s*", "", cleaned)
        return cleaned[:40]

    @staticmethod
    def _is_topic_title(title: str) -> bool:
        """校验 LLM 产出是"主题短语"而非"对话摘要"；摘要式产出应弃用并走 fallback。

        模型不遵守提示时会把对话复述成一句话（如"用户输入了hi，助手回复了……并询问
        有什么可以帮忙的"），这类产出有稳定特征：含人称词、叙述动词+了、句末标点或超长。
        """
        t = (title or "").strip()
        if not t or len(t) > 15:
            return False
        if re.search(r"[。，；！？、…]$", t):
            return False
        if re.search(r"用户|助手", t):
            return False
        return not re.search(r"(输入|回复|回答|询问|提问|提供|表达|说明|介绍|讨论|描述)了", t)

    @staticmethod
    def _fallback_session_title(message: str = "") -> str:
        text = re.sub(r"\s+", " ", message or "").strip()
        if text:
            return text[:15] + ("…" if len(text) > 15 else "")
        return f"新会话 {datetime.now().strftime('%m-%d')}"

    @staticmethod
    def _is_default_session_title(title: str | None) -> bool:
        """判断标题是否仍是创建时的默认占位（尚无 LLM 生成的真实标题）。"""
        t = (title or "").strip()
        if not t or t in {"新对话", "生成中...", "新会话"}:
            return True
        return bool(re.fullmatch(r"与 .+ 的对话", t)) or bool(re.fullmatch(r"新会话 \d{2}-\d{2}", t))

    @staticmethod
    def _build_search_snippet(content: str, keyword: str) -> str:
        text = re.sub(r"\s+", " ", content or "")
        index = text.casefold().find(keyword.casefold())
        if index < 0:
            return text[:120]
        start = max(0, index - 45)
        end = min(len(text), index + len(keyword) + 75)
        prefix = "…" if start else ""
        suffix = "…" if end < len(text) else ""
        return f"{prefix}{text[start:end]}{suffix}"

    @staticmethod
    def _build_title_context(messages: list[ChatMessageModel]) -> tuple[str, str]:
        """构造标题生成的素材：首条用户消息作为主题锚点，最近若干轮用于捕捉细节。

        返回 (first_user_content, 拼好的多轮对话文本)。仅看首轮会让标题丢失后续
        多轮里用户真正关心的基因/流程/文件等细节，故这里把“锚点 + 最近窗口”一起喂给模型。
        """
        first_user = next((m for m in messages if m.role == "user"), None)
        anchor = (first_user.content if first_user else "")[:600]

        lines: list[str] = []
        if anchor.strip():
            lines.append(f"用户：{anchor}")
        # 最近窗口覆盖对话演进后的细节诉求；user 截 600、assistant 截 400 控制 token
        for m in messages[-6:]:
            if m is first_user:
                continue  # 首条已作为锚点加入，避免重复
            role = "用户" if m.role == "user" else "助手"
            snippet = (m.content or "")[: (600 if m.role == "user" else 400)].strip()
            if snippet:
                lines.append(f"{role}：{snippet}")
        return anchor, "\n".join(lines)

    async def _generate_title_with_llm(
        self,
        session: ChatSessionModel,
        messages: list[ChatMessageModel],
    ) -> str:
        result = await self._db.execute(
            select(AIProviderConfigModel).where(AIProviderConfigModel.id == session.model_id)
        )
        config = result.scalar_one_or_none()
        if not config or not config.api_key:
            return ""
        anchor, context = self._build_title_context(messages)
        if not context.strip():
            return ""
        system_prompt = (
            "你是会话标题生成器。阅读下面用户与助手的对话，生成一个简短但**具体**的标题。"
            "要求：1) 标题必须包含对话里出现的**具体对象与意图**，如基因/蛋白/通路名、样本或文件名、"
            "分析流程或工具名、要做的动作（差异分析、富集、画火山图、解读结果、排查报错等）；"
            "2) 抓住对话**最主要的诉求**，若多轮且话题演进，以最近/最核心的诉求为准，不要只复述第一轮；"
            "3) 优先具体，禁止空泛主题词。"
            "反例（太泛，禁止）：转录组分析咨询、生物信息问题、数据分析帮助。"
            "正例（具体，推荐）：DESeq2 差异分析与火山图、TP53 通路富集结果解读、FASTQ 质控报错排查。"
            "4) 标题是**对话主题本身**，不是对话摘要：禁止出现「用户」「助手」等人称或叙述词，"
            "禁止「用户想要…」「最初询问…」「讨论了…」这类第三人称叙述句式，"
            "直接用名词短语或动宾短语点出主题。"
            "反例（叙述句，禁止）：用户想要处理VCF文件并询问安装、用户咨询差异分析流程。"
            "正例（主题式，推荐）：VCF 文件处理与工具安装、RNA-seq 差异分析流程咨询。"
            "5) 用 6 到 15 个汉字，不加结尾标点、不加引号、不要解释，只输出标题本身；"
            "标题必须是**完整短语**，宁可更短也不要写半句话。"
            "6) 若对话只是打招呼/闲聊、没有具体任务或对象（如“hi”“你好”“在吗”），"
            "输出 2 到 6 个字的场景主题即可，如：日常问候、闲聊。"
            "禁止把问候过程复述成摘要。"
        )
        payload = [{"role": "user", "content": f"对话内容：\n{context}"}]
        output = ""
        try:
            with anyio.fail_after(5):
                async for chunk in provider_manager.chat_stream(
                    config=config,
                    messages=payload,
                    system_prompt=system_prompt,
                    temperature=0,
                    max_tokens=60,
                    tools=None,
                    deep_thinking=False,
                ):
                    if chunk.type == "text":
                        output += chunk.content
                    if chunk.type in {"done", "error"}:
                        break
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"生成会话标题失败: {exc}")
        cleaned = self._clean_session_title(output)
        if cleaned and not self._is_topic_title(cleaned):
            # 模型没遵守提示、把对话复述成了摘要句：弃用，让调用方走 fallback
            logger.info(f"会话标题形似摘要，弃用 LLM 产出: {cleaned!r}")
            return ""
        return cleaned

    # --- 会话管理 ---

    async def create_session(
        self,
        user_id: str,
        model_id: uuid.UUID,
        title: str = "新对话",
        assistant_id: str | None = None,
        agent_id: str | None = None,
        *,
        mode: str = "chat",
        workspace_id: str | None = None,
        sandbox_meta: dict[str, Any] | None = None,
    ) -> ChatSessionDTO:
        session = ChatSessionModel(
            id=uuid.uuid4(),
            session_id=str(uuid.uuid4()),
            user_id=user_id,
            model_id=model_id,
            title=title,
            assistant_id=assistant_id,
            agent_id=agent_id,
            status="active",
            mode=mode,
            sandbox_meta=sandbox_meta,
        )
        # Studio 会话工作区与沙盒容器均按会话 ID 命名（manager.workspace_dir / container_name）
        if mode == "studio" and not workspace_id:
            workspace_id = session.session_id
        session.workspace_id = workspace_id
        self._db.add(session)
        await self._db.flush()
        return self._to_session_dto(session)

    async def get_session(self, session_id: str, user_id: str) -> ChatSessionModel | None:
        result = await self._db.execute(
            select(ChatSessionModel).where(
                ChatSessionModel.session_id == session_id,
                ChatSessionModel.user_id == user_id,
                ChatSessionModel.status == "active",
            )
        )
        return result.scalar_one_or_none()

    async def list_sessions(
        self,
        user_id: str,
        mode: str | None = None,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ChatSessionDTO]:
        query = select(ChatSessionModel).where(
            ChatSessionModel.user_id == user_id, ChatSessionModel.status == "active"
        )
        if mode is not None:
            query = query.where(ChatSessionModel.mode == mode)
        result = await self._db.execute(
            query.order_by(desc(ChatSessionModel.updated_at)).limit(limit).offset(offset)
        )
        return [self._to_session_dto(s) for s in result.scalars().all()]

    async def update_session_title(
        self, session_id: str, user_id: str, title: str, *, locked: bool = False
    ) -> ChatSessionDTO:
        session = await self.get_session(session_id, user_id)
        if not session:
            raise NotFoundError("会话不存在或无权访问")
        session.title = self._clean_session_title(title) or self._fallback_session_title()
        if locked:
            session.title_locked = True
        session.updated_at = datetime.now(UTC)
        await self._db.flush()
        return self._to_session_dto(session)

    async def search_sessions(self, user_id: str, keyword: str) -> ChatSessionSearchDTO:
        normalized = keyword.strip()
        if not normalized:
            return ChatSessionSearchDTO()
        pattern = f"%{self._escape_like(normalized)}%"

        title_result = await self._db.execute(
            select(ChatSessionModel)
            .where(
                ChatSessionModel.user_id == user_id,
                ChatSessionModel.status == "active",
                ChatSessionModel.title.ilike(pattern, escape="\\"),
            )
            .order_by(desc(ChatSessionModel.updated_at))
            .limit(30)
        )
        title_matches = list(title_result.scalars().all())
        title_session_ids = {s.session_id for s in title_matches}

        content_result = await self._db.execute(
            select(ChatSessionModel, ChatMessageModel)
            .join(ChatMessageModel, ChatMessageModel.session_id == ChatSessionModel.session_id)
            .where(
                ChatSessionModel.user_id == user_id,
                ChatSessionModel.status == "active",
                ChatMessageModel.content.ilike(pattern, escape="\\"),
                ChatSessionModel.session_id.not_in(title_session_ids or {"__none__"}),
            )
            .order_by(desc(ChatSessionModel.updated_at), ChatMessageModel.created_at)
            .limit(40)
        )

        seen_content_sessions: set[str] = set()
        content_matches: list[ChatSearchContentMatchDTO] = []
        for session, message in content_result.all():
            if session.session_id in seen_content_sessions:
                continue
            seen_content_sessions.add(session.session_id)
            content_matches.append(
                ChatSearchContentMatchDTO(
                    session_id=session.session_id,
                    title=session.title,
                    title_locked=session.title_locked,
                    agent_id=session.agent_id,
                    model_id=session.model_id,
                    mode=session.mode or "chat",
                    message_id=message.message_id,
                    snippet=self._build_search_snippet(message.content, normalized),
                    created_at=session.created_at,
                    updated_at=session.updated_at,
                )
            )

        return ChatSessionSearchDTO(
            title_matches=[self._to_session_dto(s) for s in title_matches],
            content_matches=content_matches,
        )

    async def generate_session_title(self, session_id: str, user_id: str) -> str:
        session = await self.get_session(session_id, user_id)
        if not session:
            raise NotFoundError("会话不存在或无权访问")
        if session.title_locked:
            return session.title

        result = await self._db.execute(
            select(ChatMessageModel)
            .where(ChatMessageModel.session_id == session_id)
            .order_by(ChatMessageModel.created_at)
        )
        messages = list(result.scalars().all())
        first_user = next((m for m in messages if m.role == "user"), None)
        fallback = self._fallback_session_title(first_user.content if first_user else "")
        if not first_user or not first_user.content.strip():
            session.title = fallback
            session.updated_at = datetime.now(UTC)
            await self._db.flush()
            return session.title

        title = await self._generate_title_with_llm(session, messages)
        cleaned = self._clean_session_title(title)
        if cleaned:
            session.title = cleaned
        elif self._is_default_session_title(session.title):
            # 仅在尚无真实标题（首轮/默认占位）时降级到 fallback；
            # 刷新轮 LLM 失败则保留已有标题，避免越改越差、丢失已抓住的细节。
            session.title = fallback
        session.updated_at = datetime.now(UTC)
        await self._db.flush()
        return session.title

    async def delete_session(self, session_id: str, user_id: str) -> bool:
        session = await self.get_session(session_id, user_id)
        if not session:
            raise NotFoundError("会话不存在或无权访问")
        session.status = "deleted"
        session.updated_at = datetime.now(UTC)
        await self._db.flush()
        self._enqueue_memory_summary(session)
        return True

    @staticmethod
    def _enqueue_memory_summary(session: ChatSessionModel) -> None:
        """删除会话后异步提炼低置信度摘要；关闭开关时不产生任何副作用。"""
        from omichub.core.config import get_settings

        if not get_settings().agent_memory_auto_summary_enabled:
            return
        try:
            from omichub.infrastructure.celery_app.tasks.memory import summarize_session

            # API 事务会在请求结束后提交；短延时防止 worker 读到提交前的会话状态。
            summarize_session.apply_async(args=[session.session_id], countdown=5)
        except Exception as exc:  # noqa: BLE001
            logger.warning("会话摘要任务投递失败，已跳过: {}", exc)

    # --- 消息管理 ---

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str = "",
        content_type: str = "text",
        status: str = "complete",
        metadata: dict[str, Any] | None = None,
    ) -> ChatMessageModel:
        message = ChatMessageModel(
            id=uuid.uuid4(),
            message_id=str(uuid.uuid4()),
            session_id=session_id,
            role=role,
            content=content,
            content_type=content_type,
            status=status,
            metadata_json=metadata or {},
        )
        self._db.add(message)
        result = await self._db.execute(
            select(ChatSessionModel).where(ChatSessionModel.session_id == session_id)
        )
        session = result.scalar_one_or_none()
        if session:
            session.message_count += 1
            session.last_message_at = datetime.now(UTC)
            session.updated_at = datetime.now(UTC)
        await self._db.flush()
        return message

    async def update_message_content(
        self,
        message_id: str,
        content: str,
        status: str = "complete",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        result = await self._db.execute(
            select(ChatMessageModel).where(ChatMessageModel.message_id == message_id)
        )
        msg = result.scalar_one_or_none()
        if msg:
            msg.content = content
            msg.status = status
            if metadata:
                # 必须构造新 dict：原地 update 后赋回同一对象，SQLAlchemy 判等不变，
                # JSONB 列不会进 UPDATE（路由徽标 routed_agent 等元数据会丢）
                msg.metadata_json = {**(msg.metadata_json or {}), **metadata}
            await self._db.flush()

    async def get_messages(
        self, session_id: str, user_id: str | None = None
    ) -> list[ChatMessageDTO]:
        # 纵深防御：即便路由层已校验归属，service 层仍复核会话属于该用户，
        # 避免任何调用方绕过路由直接拿到他人会话消息。
        if user_id is not None:
            session = await self.get_session(session_id, user_id)
            if not session:
                raise NotFoundError("会话不存在或无权访问")
        result = await self._db.execute(
            select(ChatMessageModel)
            .where(ChatMessageModel.session_id == session_id)
            .order_by(ChatMessageModel.created_at)
        )
        return [self._to_msg_dto(m) for m in result.scalars().all()]

    async def _collect_session_file_context(
        self, session_id: str, exclude_file_ids: set[str] | None = None,
        user_id: str | None = None,
    ) -> str:
        """汇总本会话历史消息中的附件引用，供后续轮次继承文件上下文。

        返回空串表示没有可继承的历史文件。附件元数据在消息落库时写入
        metadata_json.attachments，这里只做读取与去重。
        额外兜底：扫描该用户 chat-uploads 目录，按文件名内嵌的会话标记
        （``.s{session_id前8位}``）找回本会话上传过、但未进入消息元数据的文件。
        严格按会话隔离：其它会话的上传不注入，避免跨对话污染。
        """
        exclude = exclude_file_ids or set()
        result = await self._db.execute(
            select(ChatMessageModel)
            .where(ChatMessageModel.session_id == session_id)
            .order_by(ChatMessageModel.created_at)
        )
        lines: list[str] = []
        seen: set[str] = set()
        for msg in result.scalars().all():
            if msg.role != "user":
                continue
            for att in (msg.metadata_json or {}).get("attachments") or []:
                file_id = str(att.get("file_id") or "")
                if not file_id or file_id in seen or file_id in exclude:
                    continue
                seen.add(file_id)
                ref = file_id if "://" in file_id else f"upload://{file_id}"
                lines.append(
                    f"- {att.get('name', '')}（file_id: {ref}，"
                    f"可用 workspace_read_file(file_id=\"{ref}\") 读取）"
                )

        sections: list[str] = []
        if lines:
            sections.append(
                "[本会话中用户历史上传过的文件，可直接用 file_id 引用，无需重新搜索。"
                "仅当用户请求涉及这些文件时才使用；与当前请求无关时忽略，不要主动读取或提及]\n"
                + "\n".join(lines)
            )

        if user_id:
            recent_lines = self._collect_recent_upload_lines(
                user_id, seen | exclude, session_id=session_id
            )
            if recent_lines:
                sections.append(
                    "[本会话最近上传的文件，仅供备用：仅当用户请求与这些文件相关"
                    "或用户明确引用时才可使用；与当前请求无关时忽略，不要主动读取、检查或提及。"
                    "纯代码编写/概念问答类请求无需任何数据文件]\n"
                    + "\n".join(recent_lines)
                )

        return "\n\n".join(sections)

    @staticmethod
    def _collect_recent_upload_lines(
        user_id: str, skip_file_ids: set[str], session_id: str = "", limit: int = 5
    ) -> list[str]:
        """扫描用户 chat-uploads 目录，返回本会话最近上传文件的引用行（按修改时间倒序）。

        聊天上传文件名内嵌会话标记（``.s{session_id前8位}``）；给了 session_id 时
        只保留带本会话标记的文件，其它会话的上传一律不注入（会话隔离）。
        """
        from omichub.infrastructure.config.storage_config import get_user_chat_upload_dir

        upload_dir = get_user_chat_upload_dir(user_id)
        if not upload_dir.is_dir():
            return []
        session_marker = f".s{session_id[:8]}" if session_id else ""
        try:
            recent = sorted(
                (
                    p
                    for p in upload_dir.iterdir()
                    if p.is_file() and (not session_marker or session_marker in p.name)
                ),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return []
        lines: list[str] = []
        for path in recent:
            fid = path.name.split(".", 1)[0]
            if not fid or fid in skip_file_ids:
                continue
            ref = f"upload://{fid}"
            lines.append(
                f"- {path.name}（file_id: {ref}，"
                f"可用 workspace_read_file(file_id=\"{ref}\") 读取）"
            )
            if len(lines) >= limit:
                break
        return lines

    @staticmethod
    def _append_context_to_last_user_message(
        messages: list[dict[str, Any]], context_text: str
    ) -> list[dict[str, Any]]:
        """把补充上下文追加到最后一条用户消息（仅影响送 LLM 的视图，不落库）。"""
        if not messages:
            return messages
        target_index = max(
            (i for i, m in enumerate(messages) if m.get("role") == "user"),
            default=-1,
        )
        if target_index == -1:
            return messages
        target = messages[target_index]
        content = target.get("content", "")
        new_messages = list(messages)
        if isinstance(content, list):
            new_messages[target_index] = {
                **target,
                "content": content + [{"type": "text", "text": f"\n\n{context_text}"}],
            }
        else:
            new_messages[target_index] = {
                **target,
                "content": f"{content}\n\n{context_text}",
            }
        return new_messages

    # --- 上下文压缩（256K 窗口保护） ---

    # 256K 上下文窗口预留输出/系统词/工具定义空间后的触发阈值
    _CONTEXT_COMPRESS_THRESHOLD_TOKENS = 200_000
    # 压缩时保留原文的最近消息条数
    _CONTEXT_KEEP_RECENT_MESSAGES = 10

    @staticmethod
    def _message_text(message: dict[str, Any]) -> str:
        content = message.get("content", "")
        if isinstance(content, list):
            return "".join(
                str(part.get("text", "")) for part in content if isinstance(part, dict)
            )
        return str(content)

    @classmethod
    def _estimate_messages_tokens(cls, messages: list[dict[str, Any]]) -> int:
        """粗略估算 token 数：中英混合按 2 字符 ≈ 1 token 的保守口径。"""
        return sum(len(cls._message_text(m)) // 2 + 4 for m in messages)

    async def _compress_context_if_needed(
        self,
        messages: list[dict[str, Any]],
        model_config: Any,
    ) -> tuple[list[dict[str, Any]], bool, int]:
        """估算 token 超过阈值时，把较早消息压缩为摘要，仅保留最近若干条原文。

        返回 (messages, 是否压缩, 压缩前估算 token)。摘要复用当前模型生成；
        摘要调用失败时降级为"保留首条 + 最近 N 条"的硬截断，保证请求可继续。
        """
        tokens = self._estimate_messages_tokens(messages)
        keep = self._CONTEXT_KEEP_RECENT_MESSAGES
        if tokens <= self._CONTEXT_COMPRESS_THRESHOLD_TOKENS or len(messages) <= keep + 2:
            return messages, False, tokens

        old, recent = messages[:-keep], messages[-keep:]
        digest_lines: list[str] = []
        for m in old:
            text = self._message_text(m)[:2000]
            if text.strip():
                digest_lines.append(f"[{m.get('role', '?')}] {text}")
        summary = ""
        try:
            from omichub.infrastructure.ai_provider.openai_compatible import provider_manager

            parts: list[str] = []
            async for chunk in provider_manager.chat_stream(
                config=model_config,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "请将以下对话历史压缩为一份结构化摘要，必须保留：用户的分析目标与需求、"
                            "关键数据文件引用（file_id / 文件名 / 路径）、已完成的分析步骤与结论、"
                            "生成的产物（图表/文件）、以及未完成的待办事项。\n\n"
                            + "\n\n".join(digest_lines)
                        ),
                    }
                ],
                system_prompt="你是对话压缩器，只输出摘要本身，不超过 1500 字。",
                max_tokens=2048,
            ):
                if chunk.type == "text":
                    parts.append(chunk.content)
            summary = "".join(parts).strip()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"上下文压缩摘要生成失败，降级为硬截断: {e}")

        if summary:
            compressed = [
                {
                    "role": "system",
                    "content": (
                        "[早期对话已压缩为摘要，后续请基于摘要与最近对话继续]\n" + summary
                    )
                }
            ] + recent
            logger.info(
                f"上下文已压缩: 估算 {tokens} tokens，{len(old)} 条早期消息 → 摘要 + 最近 {len(recent)} 条"
            )
            return compressed, True, tokens

        # 降级：摘要失败时保留首条用户消息 + 最近 N 条
        fallback = [m for m in old[:1] if m.get("role") == "user"] + recent
        logger.info(f"上下文硬截断: 估算 {tokens} tokens，保留 {len(fallback)}/{len(messages)} 条")
        return fallback, True, tokens

    async def get_handoff_events(
        self, session_id: str, user_id: str
    ) -> list[ChatHandoffEventModel]:
        """返回当前用户会话的 Handoff 审计链，不泄露其他用户事件。"""
        session = await self.get_session(session_id, user_id)
        if session is None:
            raise NotFoundError("会话不存在或无权访问")
        result = await self._db.execute(
            select(ChatHandoffEventModel)
            .where(ChatHandoffEventModel.session_id == session_id)
            .order_by(ChatHandoffEventModel.hop_index)
        )
        return list(result.scalars().all())

    # --- SSE 流式聊天 ---

    async def stream_chat(
        self,
        user_id: str,
        messages: list[dict[str, str]],
        model_id: uuid.UUID,
        session_id: str | None = None,
        assistant_id: str | None = None,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        enable_web_search: bool = False,
    ) -> AsyncIterator[ChatChunk]:
        cookie_error = await self._ensure_cookie_balance(user_id)
        if cookie_error:
            yield ChatChunk(type="error", content=cookie_error)
            return

        # 1. 获取并验证模型配置
        result = await self._db.execute(
            select(AIProviderConfigModel).where(
                AIProviderConfigModel.id == model_id,
                AIProviderConfigModel.is_active == True,  # noqa: E712
            )
        )
        model_config = result.scalar_one_or_none()
        if not model_config:
            yield ChatChunk(type="error", content="指定的模型不存在或未启用")
            return
        if not model_config.api_key:
            yield ChatChunk(
                type="error",
                content=f"模型 '{model_config.name}' 的 API Key 未配置，请联系管理员设置",
            )
            return

        # 2. 获取或创建会话
        if session_id:
            session = await self.get_session(session_id, user_id)
            if not session:
                yield ChatChunk(type="error", content="会话不存在或已被删除")
                return
            current_session_id = session_id
        else:
            title = "新对话"
            if assistant_id:
                ast = await self.get_assistant(assistant_id)
                if ast:
                    title = f"与 {ast.name} 的对话"
            dto = await self.create_session(user_id, model_id, title, assistant_id)
            current_session_id = dto.session_id

        # 发布会话 ID 到上下文：本次流式任务内所有 AI 调用日志都会带上 session_id，
        # 供管理端按会话聚合排查。每个请求运行在独立的 asyncio 上下文副本中，无需 reset。
        session_id_var.set(current_session_id)
        try:
            from opentelemetry import trace as _otel_trace

            _otel_trace.get_current_span().set_attribute("session.id", current_session_id)
        except Exception:  # noqa: BLE001
            pass

        # 3. 确定系统提示词：参数 > 助手配置 > 默认
        final_system_prompt = system_prompt
        if not final_system_prompt and assistant_id:
            ast = await self.get_assistant(assistant_id)
            if ast:
                final_system_prompt = ast.system_prompt
        if not final_system_prompt:
            final_system_prompt = DEFAULT_SYSTEM_PROMPT

        # 4. 保存用户消息
        # 敏感信息脱敏：落库前清洗用户消息，DB 不留存原始品种名等敏感词；
        # 同时构建送 LLM 的脱敏副本（不可逆，不还原）
        from omichub.core.sanitizer import sanitize_messages, sanitize_text

        sensitive_keywords = get_settings().sensitive_keywords
        user_content_raw = messages[-1].get("content", "") if messages else ""
        user_content = sanitize_text(user_content_raw, sensitive_keywords)
        await self.add_message(current_session_id, "user", user_content)

        # 5. 创建 AI 消息记录
        ai_message = await self.add_message(
            current_session_id,
            "assistant",
            "",
            status="streaming",
            metadata={"model": model_config.name, "model_id": str(model_id)},
        )

        # 6. 调用 LLM 流式输出
        # 送外部 LLM 的 messages 用脱敏副本，避免敏感词外泄到第三方模型
        llm_messages = sanitize_messages(messages, sensitive_keywords)
        web_sources: list[dict[str, Any]] = []
        if enable_web_search and user_content.strip():
            query = user_content.strip()
            yield ChatChunk(type="web_search", content=query, metadata={"status": "searching"})
            try:
                web_sources = await SearchProviderService(self._db).search_default(query)
                if web_sources:
                    context = "\n".join(
                        f"[{index}] {item['title']}\n{item['snippet']}\n来源: {item['url']}"
                        for index, item in enumerate(web_sources, 1)
                    )
                    final_system_prompt = (
                        f"{final_system_prompt}\n\n以下是联网搜索结果。仅在确有帮助时引用，"
                        "引用格式使用 [编号]，不要编造来源：\n" + context[:4000]
                    )
                    yield ChatChunk(type="web_search_results", metadata={"sources": web_sources})
                else:
                    yield ChatChunk(type="web_search", content="未找到相关结果，已基于模型知识回答", metadata={"status": "empty"})
            except Exception as exc:  # noqa: BLE001
                logger.warning("联网搜索失败，降级为普通对话: %s", exc)
                yield ChatChunk(type="web_search", content="联网搜索失败，已基于模型自身知识回答", metadata={"status": "failed"})
        full_content = ""
        update_counter = 0
        last_usage: dict[str, Any] | None = None

        try:
            final_temp = temperature if temperature is not None else model_config.temperature
            final_max = max_tokens if max_tokens is not None else model_config.max_tokens

            async for chunk in provider_manager.chat_stream(
                config=model_config,
                messages=llm_messages,
                system_prompt=final_system_prompt,
                temperature=final_temp,
                max_tokens=final_max,
            ):
                if chunk.type == "text":
                    full_content += chunk.content
                    update_counter += 1
                    if update_counter % 5 == 0:
                        await self.update_message_content(
                            ai_message.message_id, full_content, "streaming"
                        )
                    if update_counter == 1:
                        chunk.metadata["session_id"] = current_session_id
                        chunk.metadata["message_id"] = ai_message.message_id

                elif chunk.type == "error":
                    await self.update_message_content(
                        ai_message.message_id,
                        full_content or f"生成失败: {chunk.content}",
                        "error",
                        {"error": chunk.content},
                    )
                    yield chunk
                    return

                elif chunk.type == "done":
                    last_usage = chunk.metadata.get("usage")
                    await self.update_message_content(
                        ai_message.message_id,
                        full_content,
                        "complete",
                        {
                            **({"usage": last_usage} if last_usage else {}),
                            **({"web_sources": web_sources} if web_sources else {}),
                        }
                        or None,
                    )
                    await self._apply_usage_to_session(ai_message.message_id, last_usage)
                    chunk.metadata["session_id"] = current_session_id
                    chunk.metadata["message_id"] = ai_message.message_id
                    yield chunk
                    return

                yield chunk

        except Exception as e:  # noqa: BLE001
            await self.update_message_content(
                ai_message.message_id,
                full_content or f"生成失败: {e}",
                "error",
                {"error": str(e)},
            )
            yield ChatChunk(
                type="error",
                content=f"生成失败: {e}",
                metadata={"session_id": current_session_id, "message_id": ai_message.message_id},
            )

    # --- Agent 调度中枢：SSE 流式聊天（含 MCP 工具调用闭环） ---

    async def _route_to_agent(
        self, router_ctx: AgentContext, user_text: str
    ) -> tuple[AgentContext | None, dict[str, Any] | None]:
        """智能路由：用路由器 Agent 的模型做意图分派，返回目标 Agent 上下文与路由信息。

        任何失败（模型报错、解析失败、目标不存在）都静默回落 general 候选，绝不抛出。
        """
        from omichub.application.services.agent_service import AgentService

        try:
            agent_service = AgentService(self._db)
            agents = await agent_service.list_agents(active_only=True)
            candidates = [
                a for a in agents if not (a.features or {}).get("router")
            ]
            if not candidates or router_ctx.model_config is None:
                return None, None

            def _general_fallback() -> Any:
                for c in candidates:
                    if c.category == "general" or "general" in c.agent_id:
                        return c
                return candidates[0]

            catalog = json.dumps(
                [
                    {
                        "agent_id": c.agent_id,
                        "name": c.name,
                        "description": c.description,
                        "category": c.category,
                    }
                    for c in candidates
                ],
                ensure_ascii=False,
            )
            system_prompt = ROUTER_SYSTEM_PROMPT.replace("{catalog}", catalog)

            # 路由过程 chunk 全部消费，仅累加 text，不向外 yield
            route_text = ""
            async for chunk in provider_manager.chat_stream(
                config=router_ctx.model_config,
                messages=[{"role": "user", "content": user_text}],
                system_prompt=system_prompt,
                temperature=0,
                max_tokens=200,
                tools=None,
                deep_thinking=False,
            ):
                if chunk.type == "text":
                    route_text += chunk.content

            valid_ids = {c.agent_id for c in candidates}
            target_id = ""
            reason = ""
            expect_handoff = False
            consult_agent_ids: list[str] = []
            intent = "chat"
            confidence = 0.0
            decision = _extract_route_json(route_text)
            if decision:
                target_id = str(decision.get("agent_id") or "")
                reason = str(decision.get("reason") or "")
                expect_handoff = bool(decision.get("expect_handoff"))
                parsed_intent = str(decision.get("intent") or "chat")
                intent = (
                    parsed_intent
                    if parsed_intent in {"chat", "light_collab", "delivery_case"}
                    else "chat"
                )
                try:
                    confidence = min(1.0, max(0.0, float(decision.get("confidence", 0))))
                except (TypeError, ValueError):
                    confidence = 0.0
                if intent == "delivery_case" and confidence < 0.7:
                    intent = "light_collab"
                raw_consults = decision.get("consult_agent_ids")
                if get_settings().multi_expert_consultation_enabled and isinstance(
                    raw_consults, list
                ):
                    max_experts = max(
                        2, min(get_settings().multi_expert_consultation_max_experts, 3)
                    )
                    consult_agent_ids = list(
                        dict.fromkeys(
                            str(item)
                            for item in raw_consults
                            if str(item) in valid_ids and str(item) != target_id
                        )
                    )[:max_experts]
            if target_id not in valid_ids:
                fallback = _general_fallback()
                target_id = fallback.agent_id
                if not reason:
                    reason = "未识别出明确领域，转接通用助手"

            target_ctx = await agent_service.assemble_context(target_id)
            if target_ctx is None or target_ctx.model_config is None:
                fallback = _general_fallback()
                target_id = fallback.agent_id
                target_ctx = await agent_service.assemble_context(target_id)
                if target_ctx is None:
                    return None, None

            target_dto = next(
                (c for c in candidates if c.agent_id == target_id),
                _general_fallback(),
            )
            route_info = {
                "agent_id": target_dto.agent_id,
                "name": target_dto.name,
                "avatar": target_dto.avatar,
                "color": target_dto.color,
                "reason": reason,
                "expect_handoff": expect_handoff,
                "consult_agent_ids": consult_agent_ids,
                "intent": intent,
                "confidence": confidence,
            }
            return target_ctx, route_info
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[Agent路由] 意图分派失败，按原 Agent 继续: {e}")
            return None, None

    async def stream_agent_chat(
        self,
        user_id: str,
        agent_id: str,
        messages: list[dict[str, str]],
        session_id: str | None = None,
        model_id: uuid.UUID | None = None,
        attachments: list[dict[str, Any]] | None = None,
        enable_web_search: bool = False,
        enable_code_execution: bool = False,
        deep_thinking: bool = False,
        mode: str | None = None,
        mcp_mode: str | None = None,
        extra_mcp_servers: list[str] | None = None,
        multi_agent: bool | None = None,
        extend_max_rounds: bool = False,
    ) -> AsyncIterator[ChatChunk]:
        """Agent 编排入口（带 Trace/Log/Metrics 埋点）：作为 AI/MCP/技能 span 的父 span。"""
        tracer = get_tracer("omichub.chat")
        span_attrs: dict[str, Any] = {"agent.id": agent_id}
        if model_id is not None:
            span_attrs["agent.model_id"] = str(model_id)
        with tracer.start_as_current_span("agent.run", attributes=span_attrs) as span:
            start = time.perf_counter()
            status = "success"
            try:
                async for chunk in self._stream_agent_chat_inner(
                    user_id,
                    agent_id,
                    messages,
                    session_id=session_id,
                    model_id=model_id,
                    attachments=attachments,
                    enable_web_search=enable_web_search,
                    enable_code_execution=enable_code_execution,
                    deep_thinking=deep_thinking,
                    mode=mode,
                    mcp_mode=mcp_mode,
                    extra_mcp_servers=extra_mcp_servers,
                    multi_agent=multi_agent,
                    extend_max_rounds=extend_max_rounds,
                ):
                    if chunk.type == "error":
                        status = "error"
                    yield chunk
            except Exception as exc:  # noqa: BLE001
                status = "error"
                span.record_exception(exc)
                raise
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                attrs = {"agent.id": agent_id, "agent.status": status}
                span.set_attribute("agent.status", status)
                span.set_attribute("agent.duration_ms", round(duration_ms, 2))
                with contextlib.suppress(Exception):
                    _agent_duration.record(duration_ms, attrs)
                logger.bind(
                    event="agent.run",
                    agent_id=agent_id,
                    status=status,
                    duration_ms=round(duration_ms, 2),
                ).info("agent.run completed")

    async def _stream_agent_chat_inner(
        self,
        user_id: str,
        agent_id: str,
        messages: list[dict[str, str]],
        session_id: str | None = None,
        model_id: uuid.UUID | None = None,
        attachments: list[dict[str, Any]] | None = None,
        enable_web_search: bool = False,
        enable_code_execution: bool = False,
        deep_thinking: bool = False,
        mode: str | None = None,
        mcp_mode: str | None = None,
        extra_mcp_servers: list[str] | None = None,
        multi_agent: bool | None = None,
        extend_max_rounds: bool = False,
    ) -> AsyncIterator[ChatChunk]:
        """Agent 编排闭环：查 Agent → 组装模型/系统词/工具 → 打 LLM → 执行 tool_call 回灌 → 流式返回

        Studio 模式（mode="studio" 或会话行 mode="studio"）：追加 5 个工作台内置工具与
        Studio 系统提示词后缀，工具调用路由到沙盒执行（sandbox_execute 流式回传 stdout/stderr）。
        """
        from omichub.application.schemas.tool_invocation import ToolInvocationContext
        from omichub.application.services.agent_service import AgentService
        from omichub.core.sanitizer import sanitize_messages, sanitize_text
        from omichub.infrastructure.mcp.client import MCPClient

        cookie_error = await self._ensure_cookie_balance(user_id)
        if cookie_error:
            yield ChatChunk(type="error", content=cookie_error)
            return

        ctx = await AgentService(self._db).assemble_context(agent_id)
        if ctx is None:
            yield ChatChunk(type="error", content="Agent 不存在或已停用")
            return

        # 若请求指定了 model_id，校验并覆盖 Agent 默认模型
        if model_id is not None:
            override = await self._resolve_model(model_id)
            if override is None:
                yield ChatChunk(
                    type="error",
                    content="指定的模型不存在或未启用",
                )
                return
            if not override.api_key:
                yield ChatChunk(
                    type="error",
                    content=f"模型 '{override.name}' 的 API Key 未配置，请联系管理员设置",
                )
                return
            ctx.model_config = override

        if ctx.model_config is None:
            yield ChatChunk(
                type="error",
                content=f"Agent '{ctx.agent.name}' 未绑定可用模型，请联系管理员在 AI 资源中心配置",
            )
            return
        if not ctx.model_config.api_key:
            yield ChatChunk(
                type="error",
                content=f"模型 '{ctx.model_config.name}' 的 API Key 未配置，请联系管理员设置",
            )
            return

        model_config = ctx.model_config
        sensitive_keywords = get_settings().sensitive_keywords

        # 1. 取/建会话
        # Studio 模式判定：已有会话以会话行 mode 为准；新建会话取请求显式 mode。
        # 沙盒镜像优先取会话 sandbox_meta.image（创建时由 Agent studio 配置解析），
        # 其次取 Agent features.studio.image，均未配置时由 manager 回落默认镜像。
        # context_pack（报告一键优化场景，§7.2）只在已有会话上存在，随系统提示词注入。
        studio_mode = False
        studio_image: str | None = None
        studio_context_pack: dict[str, Any] | None = None
        # 会话级权限模式（§2）：supervised（默认，写/执行类工具需用户批准）| auto
        studio_permission_mode = "supervised"
        studio_capability_state = CapabilityState()
        bound_skills = list(getattr(ctx, "skills", []) or [])
        bound_mcp_servers = list(ctx.mcp_servers or [])
        session_mcp_meta = {}
        effective_mcp_mode = mcp_mode or "auto"
        effective_extra_mcp_servers = list(extra_mcp_servers or [])
        if session_id:
            session = await self.get_session(session_id, user_id)
            if not session:
                yield ChatChunk(type="error", content="会话不存在或已被删除")
                return
            if session.agent_id and session.agent_id != agent_id:
                yield ChatChunk(type="error", content="会话绑定的 Agent 与当前请求不一致")
                return
            # 若用户切换了模型，同步更新会话记录的 model_id
            if model_id is not None and session.model_id != model_id:
                session.model_id = model_id
                session.updated_at = datetime.now(UTC)
            studio_mode = session.mode == "studio"
            session_mcp_meta = dict(session.sandbox_meta or {})
            effective_mcp_mode = mcp_mode or session_mcp_meta.get("mcp_mode") or "auto"
            if extra_mcp_servers is None:
                effective_extra_mcp_servers = list(session_mcp_meta.get("extra_mcp_servers") or [])
            session_mcp_meta.update({
                "mcp_mode": effective_mcp_mode,
                "extra_mcp_servers": effective_extra_mcp_servers,
            })
            effective_multi_agent = (
                bool(multi_agent)
                if multi_agent is not None
                else bool(session_mcp_meta.get("multi_agent", False))
            )
            session_mcp_meta["multi_agent"] = effective_multi_agent
            # Skill 版本 pin：会话首轮快照挂载技能的活跃版本号（skill_id → revision）。
            # 整个会话内 use_skill 读取被 pin 的快照正文，会话中途升级不影响进行中的任务；
            # 新会话取新版本。pin 失败不阻断对话（回落到当前内容）。
            if bound_skills and "skill_pins" not in session_mcp_meta:
                try:
                    from sqlalchemy import func as _sa_func

                    from omichub.infrastructure.database.models.skill import (
                        SkillVersionModel,
                    )

                    pins: dict[str, int] = {}
                    for _s in bound_skills:
                        _rev = (
                            await self._db.execute(
                                select(_sa_func.max(SkillVersionModel.revision)).where(
                                    SkillVersionModel.skill_id == _s.skill_id
                                )
                            )
                        ).scalar()
                        if _rev:
                            pins[_s.skill_id] = int(_rev)
                    if pins:
                        session_mcp_meta["skill_pins"] = pins
                        session.sandbox_meta = session_mcp_meta
                except Exception as pin_exc:  # noqa: BLE001
                    logger.warning("skill_pins 写入失败（忽略，回落当前版本）: {}", pin_exc)
            session.sandbox_meta = session_mcp_meta
            if studio_mode:
                sandbox_meta = session.sandbox_meta or {}
                studio_image = sandbox_meta.get("image")
                studio_context_pack = sandbox_meta.get("context_pack")
                studio_permission_mode = (sandbox_meta.get("permissions") or {}).get(
                    "mode", "supervised"
                )
                studio_capability_state = normalize_capability_state(
                    sandbox_meta.get("capabilities"), bound_skills, bound_mcp_servers
                )
            current_session_id = session_id
        else:
            studio_mode = mode == "studio"
            effective_multi_agent = bool(multi_agent)
            if studio_mode:
                studio_image = (ctx.features.get("studio") or {}).get("image")
            title = f"与 {ctx.agent.name} 的对话"
            dto = await self.create_session(
                user_id,
                model_config.id,
                title,
                agent_id=agent_id,
                mode="studio" if studio_mode else "chat",
                sandbox_meta={
                    **({"image": studio_image} if studio_image else {}),
                    "mcp_mode": effective_mcp_mode,
                    "extra_mcp_servers": effective_extra_mcp_servers,
                    "multi_agent": bool(multi_agent),
                },
            )
            current_session_id = dto.session_id

        # 发布会话 ID 到上下文（覆盖 Agent + Studio 工作台）：本次流式任务内所有
        # AI/MCP/技能日志都会带上 session_id；同时写入 agent.run span 便于按会话查 trace。
        session_id_var.set(current_session_id)
        try:
            from opentelemetry import trace as _otel_trace

            _otel_trace.get_current_span().set_attribute("session.id", current_session_id)
        except Exception:  # noqa: BLE001
            pass

        # 2. 落库用户消息（脱敏）
        user_content_raw = messages[-1].get("content", "") if messages else ""
        user_content = sanitize_text(user_content_raw, sensitive_keywords)
        attachment_dicts = [
            att.model_dump() if hasattr(att, "model_dump") else dict(att)
            for att in (attachments or [])
        ]
        await self.add_message(
            current_session_id,
            "user",
            user_content,
            metadata={"attachments": attachment_dicts},
        )

        # 3. AI 占位消息
        ai_message = await self.add_message(
            current_session_id,
            "assistant",
            "",
            status="streaming",
            metadata={"model": model_config.name, "agent_id": agent_id},
        )

        route_info: dict[str, Any] | None = None

        # 3.5 智能路由：路由器 Agent 先做意图分派，再以目标 Agent 的上下文继续后续流程。
        # 会话绑定校验与落库的 agent_id 始终保持路由器不变；同一会话的每条消息都重新路由。
        if ctx.features.get("router"):
            target_ctx, route_info = await self._route_to_agent(ctx, user_content)
            if target_ctx is not None and route_info is not None:
                ctx = target_ctx
                if ctx.model_config is not None:
                    model_config = ctx.model_config
                bound_skills = list(getattr(ctx, "skills", []) or [])
                bound_mcp_servers = list(ctx.mcp_servers or [])
                await self.update_message_content(
                    ai_message.message_id,
                    "",
                    "streaming",
                    {"model": model_config.name, "routed_agent": route_info},
                )
                yield ChatChunk(
                    type="route",
                    metadata={
                        **route_info,
                        "session_id": current_session_id,
                        "message_id": ai_message.message_id,
                    },
                )

        # 4. 送 LLM 的 messages（脱敏 + 附件多模态注入）
        llm_messages: list[dict[str, Any]] = sanitize_messages(messages, sensitive_keywords)
        if attachments:
            llm_messages = await self._build_multimodal_messages(llm_messages, attachments)

        # 4.1 上下文继承：把本会话历史消息中上传过的文件（file_id 引用）注入本轮，
        # 避免后续轮次丢失附件上下文后模型重新全局搜索文件。
        current_file_ids = {
            str(att.get("file_id") or "") for att in attachment_dicts if att.get("file_id")
        }
        history_file_ctx = await self._collect_session_file_context(
            current_session_id, exclude_file_ids=current_file_ids, user_id=user_id
        )
        if history_file_ctx:
            llm_messages = self._append_context_to_last_user_message(
                llm_messages, history_file_ctx
            )

        # 4.2 上下文压缩：估算 token 接近模型上下文窗口（256K）时，
        # 把较早的对话压缩为摘要，只保留最近若干条原文，避免超窗报错。
        llm_messages, context_compressed, tokens_before = await self._compress_context_if_needed(
            llm_messages, model_config
        )
        if context_compressed:
            yield ChatChunk(
                type="context_compressed",
                content="对话历史较长，已将早期内容压缩为摘要后继续",
                metadata={
                    "session_id": current_session_id,
                    "estimated_tokens_before": tokens_before,
                },
            )

        # 动态追加联网搜索工具。普通聊天保持 Agent 全量 MCP/Skill 行为；
        # Studio 使用元数据目录 + 会话级按需加载，未加载能力不进入 prompt/tools。
        search_required = self._requires_fresh_web_search(user_content, ctx.features)
        effective_web_search = (
            enable_web_search
            or bool(ctx.features.get("enable_web_search"))
            or search_required
        )
        supports_function_tools = bool((model_config.extra_params or {}).get("supports_tools", True))
        base_tools: list[dict[str, Any]] = []
        if effective_web_search and supports_function_tools and not search_required:
            base_tools.append(WEB_SEARCH_TOOL)

        active_mcp_servers = [] if effective_mcp_mode == "off" else list(bound_mcp_servers)
        if effective_mcp_mode == "manual" and effective_extra_mcp_servers:
            try:
                extra_ids = [uuid.UUID(server_id) for server_id in effective_extra_mcp_servers]
            except (ValueError, AttributeError):
                extra_ids = []
            if extra_ids:
                from omichub.infrastructure.database.repositories.mcp_repository import (
                    SqlAlchemyMCPServerRepository,
                )

                defaults_by_name = {server.name: server for server in active_mcp_servers}
                for server in await SqlAlchemyMCPServerRepository(self._db).get_by_ids(extra_ids):
                    if server.is_enabled and server.name not in defaults_by_name:
                        active_mcp_servers.append(server)
        tools = list(ctx.tools or []) + base_tools
        if effective_multi_agent and supports_function_tools:
            known_tool_names = {
                str(item.get("function", {}).get("name") or "")
                for item in tools
                if isinstance(item, dict)
            }
            tools.extend(
                tool
                for tool in schema_loader.to_openai_tools()
                if tool.get("function", {}).get("name") in MULTI_AGENT_TOOL_NAMES
                and tool.get("function", {}).get("name") not in known_tool_names
            )
        # ask_user 澄清弹窗在普通聊天同样可用（Studio 由 STUDIO_TOOL_SCHEMAS 携带），
        # 让所有 Agent 的多选项澄清都走弹窗而不是纯文本罗列编号。
        if not studio_mode and supports_function_tools and not any(
            t.get("function", {}).get("name") == "ask_user" for t in tools
        ):
            tools.append(ASK_USER_TOOL_SCHEMA)
        # 知识库检索在普通聊天同样可用（Studio 由 STUDIO_TOOL_SCHEMAS 携带），
        # 让 Agent 能检索平台知识库（含用户个人笔记/实验经验文档）再作答。
        if not studio_mode and supports_function_tools and not any(
            t.get("function", {}).get("name") == "knowledge_search" for t in tools
        ):
            tools.append(KNOWLEDGE_SEARCH_TOOL)
        system_prompt = ctx.system_prompt or None
        if effective_multi_agent:
            system_prompt = (
                f"{system_prompt}\n\n{MULTI_AGENT_SYSTEM_PROMPT_SUFFIX}"
                if system_prompt
                else MULTI_AGENT_SYSTEM_PROMPT_SUFFIX
            )
        if any(
            tool.get("function", {}).get("name") in MEMORY_TOOL_NAMES
            for tool in tools
            if isinstance(tool, dict)
        ):
            system_prompt = (
                f"{system_prompt}\n\n{MEMORY_SYSTEM_PROMPT_SUFFIX}"
                if system_prompt
                else MEMORY_SYSTEM_PROMPT_SUFFIX
            )
        if any(
            tool.get("function", {}).get("name") == HANDOFF_TOOL_NAME
            for tool in tools
            if isinstance(tool, dict)
        ):
            system_prompt = (
                f"{system_prompt}\n\n{HANDOFF_SYSTEM_PROMPT_SUFFIX}"
                if system_prompt
                else HANDOFF_SYSTEM_PROMPT_SUFFIX
            )
        if not studio_mode and any(
            tool.get("function", {}).get("name") == "ask_user"
            for tool in tools
            if isinstance(tool, dict)
        ):
            system_prompt = (
                f"{system_prompt}\n\n{ASK_USER_SYSTEM_PROMPT_SUFFIX}"
                if system_prompt
                else ASK_USER_SYSTEM_PROMPT_SUFFIX
            )
        if not studio_mode and any(
            tool.get("function", {}).get("name") == "knowledge_search"
            for tool in tools
            if isinstance(tool, dict)
        ):
            system_prompt = (
                f"{system_prompt}\n\n{KNOWLEDGE_SEARCH_SYSTEM_PROMPT_SUFFIX}"
                if system_prompt
                else KNOWLEDGE_SEARCH_SYSTEM_PROMPT_SUFFIX
            )
        if self._db is not None:
            try:
                from omichub.application.services.agent_memory_service import AgentMemoryService

                memory_context = await AgentMemoryService(self._db).build_prompt_context(
                    user_id, getattr(ctx.agent, "agent_id", agent_id), user_content
                )
                if memory_context:
                    system_prompt = (
                        f"{system_prompt}\n\n{memory_context}" if system_prompt else memory_context
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Agent 长期记忆召回失败，已跳过: %s", exc)

        if (
            get_settings().multi_expert_consultation_enabled
            and route_info is not None
            and route_info.get("consult_agent_ids")
        ):
            try:
                from omichub.application.services.multi_expert_consultation_service import (
                    MultiExpertConsultationService,
                )

                opinions = await MultiExpertConsultationService(AgentService(self._db)).collect(
                    list(route_info["consult_agent_ids"]), user_content
                )
                consultation_context = MultiExpertConsultationService.render_prompt_context(opinions)
                if consultation_context:
                    system_prompt = f"{system_prompt}\n\n{consultation_context}".strip()
                    yield ChatChunk(
                        type="consultation",
                        metadata={
                            "experts": opinions,
                            "session_id": current_session_id,
                            "message_id": ai_message.message_id,
                        },
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("多专家会诊失败，回退单专家回答: {}", exc)
        mas_plan_tool_enabled = get_settings().mas_enabled and (
            studio_mode or bool(ctx.features.get("mas_orchestrator"))
        )

        def _attach_mas_plan_tool(
            runtime_tools: list[dict[str, Any]], runtime_prompt: str | None
        ) -> tuple[list[dict[str, Any]], str]:
            if not mas_plan_tool_enabled:
                return runtime_tools, runtime_prompt or ""
            if not any(
                item.get("function", {}).get("name") == MAS_PLAN_PREVIEW_TOOL_NAME
                for item in runtime_tools
            ):
                runtime_tools.append(MAS_PLAN_PREVIEW_TOOL_SCHEMA)
            prompt = runtime_prompt or ""
            return runtime_tools, f"{prompt}\n\n{MAS_PLAN_PREVIEW_PROMPT_SUFFIX}".strip()

        def _studio_runtime(state: CapabilityState) -> tuple[list[dict[str, Any]], str, list[Any]]:
            runtime_tools = list(base_tools)
            runtime_tools.extend(STUDIO_TOOL_SCHEMAS)
            runtime_tools.extend(CAPABILITY_TOOL_SCHEMAS)
            reserved_names = {
                item.get("function", {}).get("name", "") for item in runtime_tools
            }
            safe_servers = []
            for server in loaded_capability_servers(bound_mcp_servers, state):
                server_names = {tool.tool_name for tool in server.tools}
                if server_names & reserved_names:
                    continue
                safe_servers.append(server)
                reserved_names.update(server_names)
            runtime_tools.extend(capability_mcp_tools(safe_servers))

            base_prompt = getattr(ctx.agent, "system_prompt", "") or ""
            if not base_prompt and not bound_skills:
                base_prompt = ctx.system_prompt or ""
            runtime_prompt = render_capability_prompt(
                base_prompt, bound_skills, bound_mcp_servers, state
            )
            runtime_prompt = (
                f"{runtime_prompt}\n\n{STUDIO_SYSTEM_PROMPT_SUFFIX}"
                if runtime_prompt
                else STUDIO_SYSTEM_PROMPT_SUFFIX
            )
            if studio_context_pack:
                from omichub.application.services.studio_context_service import (
                    render_context_pack_hint,
                )

                runtime_prompt += f"\n\n{render_context_pack_hint(studio_context_pack)}"
            return runtime_tools, runtime_prompt, safe_servers

        if studio_mode:
            tools, system_prompt, active_mcp_servers = _studio_runtime(
                studio_capability_state
            )
        tools, system_prompt = _attach_mas_plan_tool(tools, system_prompt)

        async def _prepare_handoff_target(
            directive: dict[str, Any],
        ) -> tuple[AgentContext, Any, list[Any], list[Any], list[dict[str, Any]], str]:
            """重新装配目标 Agent，且只向其提供 handoff packet 而非完整历史。"""
            target_ctx = await AgentService(self._db).assemble_context(
                str(directive["target_agent_id"])
            )
            if target_ctx is None or target_ctx.model_config is None:
                raise BusinessError("目标 Agent 不存在、已停用或未绑定可用模型")
            if not target_ctx.model_config.api_key:
                raise BusinessError("目标 Agent 的模型 API Key 未配置")

            target_skills = list(getattr(target_ctx, "skills", []) or [])
            target_servers = [] if effective_mcp_mode == "off" else list(target_ctx.mcp_servers or [])
            target_tools = list(target_ctx.tools or []) + list(base_tools)
            target_prompt = target_ctx.system_prompt or ""
            if effective_multi_agent and supports_function_tools:
                target_tool_names = {
                    str(item.get("function", {}).get("name") or "")
                    for item in target_tools
                    if isinstance(item, dict)
                }
                target_tools.extend(
                    tool
                    for tool in schema_loader.to_openai_tools()
                    if tool.get("function", {}).get("name") in MULTI_AGENT_TOOL_NAMES
                    and tool.get("function", {}).get("name") not in target_tool_names
                )
                target_prompt = f"{target_prompt}\n\n{MULTI_AGENT_SYSTEM_PROMPT_SUFFIX}".strip()
            # 与主路径一致：ask_user 澄清弹窗兜底挂载，多选项澄清走弹窗而非纯文本罗列
            if supports_function_tools and not any(
                t.get("function", {}).get("name") == "ask_user" for t in target_tools
            ):
                target_tools.append(ASK_USER_TOOL_SCHEMA)
            if any(
                item.get("function", {}).get("name") == "ask_user"
                for item in target_tools
                if isinstance(item, dict)
            ):
                target_prompt = f"{target_prompt}\n\n{ASK_USER_SYSTEM_PROMPT_SUFFIX}".strip()
            if any(
                item.get("function", {}).get("name") in MEMORY_TOOL_NAMES
                for item in target_tools
                if isinstance(item, dict)
            ):
                target_prompt = f"{target_prompt}\n\n{MEMORY_SYSTEM_PROMPT_SUFFIX}".strip()
            if any(
                item.get("function", {}).get("name") == HANDOFF_TOOL_NAME
                for item in target_tools
                if isinstance(item, dict)
            ):
                target_prompt = f"{target_prompt}\n\n{HANDOFF_SYSTEM_PROMPT_SUFFIX}".strip()
            try:
                from omichub.application.services.agent_memory_service import AgentMemoryService

                memory_context = await AgentMemoryService(self._db).build_prompt_context(
                    user_id,
                    target_ctx.agent.agent_id,
                    user_content,
                )
                if memory_context:
                    target_prompt = f"{target_prompt}\n\n{memory_context}".strip()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Handoff 目标 Agent 长期记忆召回失败，已跳过: %s", exc)
            target_prompt = f"{target_prompt}\n\n{directive['packet']}".strip()
            return (
                target_ctx,
                target_ctx.model_config,
                target_skills,
                target_servers,
                target_tools,
                target_prompt,
            )

        # 不支持 function calling 的模型总是在调用前搜索；对时效/文献类问题，
        # 即使模型支持工具也强制预搜索，保证先核验事实再回答。
        presearch_sources: list[dict[str, Any]] = []
        if effective_web_search and (not supports_function_tools or search_required) and user_content.strip():
            yield ChatChunk(type="web_search", content=user_content, metadata={"status": "searching"})
            try:
                presearch_sources = await SearchProviderService(self._db).search_default(user_content)
                if presearch_sources:
                    context = "\n".join(
                        f"[{index}] {item['title']}\n{item['snippet']}\n来源: {item['url']}"
                        for index, item in enumerate(presearch_sources, 1)
                    )
                    system_prompt = (
                        f"{system_prompt}\n\n以下是联网搜索结果。仅在确有帮助时引用，"
                        "引用格式使用 [编号]，不要编造来源：\n" + context[:4000]
                    )
                    yield ChatChunk(type="web_search_results", metadata={"sources": presearch_sources})
                else:
                    yield ChatChunk(type="web_search", content="未找到相关结果，已基于模型知识回答", metadata={"status": "empty"})
            except Exception as exc:  # noqa: BLE001
                logger.warning("Agent 预搜索失败，降级为普通对话: %s", exc)
                if search_required:
                    system_prompt = (
                        f"{system_prompt}\n\n本轮问题要求联网核验，但检索不可用。"
                        "必须先说明无法完成实时或文献核验；不得将模型记忆表述为最新事实，"
                        "不得编造引用。"
                    )
                yield ChatChunk(type="web_search", content="联网搜索失败，已基于模型自身知识回答", metadata={"status": "failed"})

        full_content = ""
        web_sources: list[dict[str, Any]] = list(presearch_sources)
        update_counter = 0
        first_chunk_sent = False
        # 默认 100 轮；用户在弹窗中确认继续后前端传 extend_max_rounds=True 扩展到 1000 轮
        max_rounds = 1000 if extend_max_rounds else 100
        last_usage: dict[str, Any] | None = None
        last_finish_reason: str | None = None
        # Studio 工具调用落库累积（代码卡片 / 产物 / diff，供历史重载渲染）
        studio_invocations: list[dict[str, Any]] = []
        # 正文/工具调用的时间线：按发生顺序记录 text 段与 tool 段，
        # 供前端按"内容→工具→内容"的实际过程交错渲染，而不是上正文下工具两段式
        timeline: list[dict[str, Any]] = []

        mcp_client = MCPClient()

        tool_context = ToolInvocationContext(
            user_id=user_id,
            agent_id=agent_id,
            session_id=current_session_id,
            db=self._db,
        )

        async def _persist_capability_state(
            state: CapabilityState, event: dict[str, Any]
        ) -> CapabilityState:
            audited = CapabilityState(
                state.loaded_skill_ids,
                state.loaded_mcp_ids,
                tuple((*state.audit, event)[-100:]),
            )
            capability_session = await self.get_session(current_session_id, user_id)
            if capability_session is not None:
                meta = dict(capability_session.sandbox_meta or {})
                meta["capabilities"] = audited.as_dict()
                capability_session.sandbox_meta = meta
                capability_session.updated_at = datetime.now(UTC)
                await self._db.flush()
            return audited

        async def _activate_langgraph_handoff(directive: dict[str, Any]) -> dict[str, Any]:
            """持久化交接并返回下一段 LangGraph 运行时所需的完整配置。"""
            target_ctx, target_model, target_skills, target_servers, target_tools, target_prompt = (
                await _prepare_handoff_target(directive)
            )
            await AgentHandoffService(self._db).record_handoff(
                user_id=user_id,
                session_id=current_session_id,
                directive=directive,
            )
            handoff_session = await self.get_session(current_session_id, user_id)
            if handoff_session is not None:
                handoff_session.agent_id = target_ctx.agent.agent_id
                handoff_session.model_id = target_model.id
                handoff_session.updated_at = datetime.now(UTC)
            return {
                "model_config": target_model,
                "llm_messages": [{"role": "user", "content": str(directive["packet"])}],
                "system_prompt": target_prompt,
                "tools": target_tools,
                "temperature": target_ctx.temperature,
                "max_tokens": target_ctx.max_tokens,
                "active_mcp_servers": target_servers,
                "tool_context": ToolInvocationContext(
                    user_id=user_id,
                    agent_id=target_ctx.agent.agent_id,
                    session_id=current_session_id,
                    db=self._db,
                ),
                "skills": target_skills,
                "directive": directive,
            }

        # LangGraph 引擎分流：features.engine == "langgraph" 且非 Studio 模式时
        # 走状态图运行时；其余（含 Studio 沙盒、未标记 engine）保持手写循环不变。
        if ctx.features.get("engine") == "langgraph" and not studio_mode:
            async for chunk in self._stream_agent_chat_langgraph(
                user_id=user_id,
                session_id=current_session_id,
                ai_message_id=ai_message.message_id,
                model_config=model_config,
                llm_messages=llm_messages,
                system_prompt=system_prompt,
                tools=tools,
                temperature=ctx.temperature,
                max_tokens=ctx.max_tokens,
                deep_thinking=deep_thinking,
                active_mcp_servers=active_mcp_servers,
                mcp_client=mcp_client,
                tool_context=tool_context,
                skills=bound_skills,
                skill_pins=session_mcp_meta.get("skill_pins"),
                web_sources=presearch_sources,
                handoff_handler=_activate_langgraph_handoff,
            ):
                yield chunk
            return

        try:
            logger.info(
                f"[Agent聊天] 开始调用模型 provider={model_config.name} model={model_config.model} "
                f"messages={len(llm_messages)} tools={len(tools)} attachments={len(attachments or [])}"
            )
            for _round in range(max_rounds):
                round_text = ""
                round_tool_calls: list[dict[str, Any]] = []
                # 父单轮工具回合内 fan-out 调用计数（subagent_max_children_per_message 护栏）
                subagent_calls_this_round = 0

                async for chunk in provider_manager.chat_stream(
                    config=model_config,
                    messages=llm_messages,
                    system_prompt=system_prompt,
                    temperature=ctx.temperature,
                    max_tokens=ctx.max_tokens,
                    tools=tools or None,
                    deep_thinking=deep_thinking,
                ):
                    if chunk.type == "text":
                        if chunk.metadata.get("is_reasoning"):
                            # 推理过程不并入最终正文，但仍透传给前端
                            yield chunk
                            continue
                        round_text += chunk.content
                        full_content += chunk.content
                        update_counter += 1
                        if update_counter % 5 == 0:
                            await self.update_message_content(
                                ai_message.message_id, full_content, "streaming"
                            )
                        if not first_chunk_sent:
                            chunk.metadata["session_id"] = current_session_id
                            chunk.metadata["message_id"] = ai_message.message_id
                            first_chunk_sent = True
                        yield chunk

                    elif chunk.type == "tool_calls":
                        round_tool_calls = chunk.metadata.get("tool_calls", [])

                    elif chunk.type == "error":
                        await self.update_message_content(
                            ai_message.message_id,
                            full_content or f"生成失败: {chunk.content}",
                            "error",
                            {"error": chunk.content},
                        )
                        yield chunk
                        return

                    elif chunk.type == "done":
                        # Studio 工具循环会产生多次模型请求，逐轮累计实际计费用量。
                        last_usage = merge_token_usage(
                            last_usage, chunk.metadata.get("usage")
                        )
                        last_finish_reason = chunk.metadata.get("finish_reason") or last_finish_reason

                # 本轮无工具调用 → 正常结束
                if not round_tool_calls:
                    if round_text:
                        timeline.append({"kind": "text", "text": round_text})
                    completion_metadata = {
                        **({"usage": last_usage} if last_usage else {}),
                        **({"web_sources": web_sources} if web_sources else {}),
                        **({"timeline": timeline} if timeline else {}),
                    }
                    await self.update_message_content(
                        ai_message.message_id,
                        full_content,
                        "complete",
                        completion_metadata or None,
                    )
                    await self._apply_usage_to_session(ai_message.message_id, last_usage)
                    done_meta: dict[str, Any] = {
                            "session_id": current_session_id,
                            "message_id": ai_message.message_id,
                            "usage": last_usage,
                        }
                    if last_finish_reason:
                        done_meta["finish_reason"] = last_finish_reason
                    yield ChatChunk(type="done", metadata=done_meta)
                    return

                # 有工具调用 → 执行并回灌，进入下一轮
                # 先把 assistant 的 tool_calls 消息加入上下文
                llm_messages.append(
                    {
                        "role": "assistant",
                        "content": round_text or "",
                        "tool_calls": round_tool_calls,
                    }
                )
                if round_text:
                    full_content += "\n\n" if full_content else ""
                    timeline.append({"kind": "text", "text": round_text})
                    # 工具调用阶段的正文并入落库内容
                    await self.update_message_content(
                        ai_message.message_id, full_content, "streaming"
                    )

                # ask_user 拦截时置 True：回灌工具结果后收尾跳出大循环，等待用户下条消息
                stop_after_tools = False
                handoff_requested = False
                for tc in round_tool_calls:
                    fn = tc.get("function", {}) or {}
                    tool_name = fn.get("name", "")
                    raw_args = fn.get("arguments", "")
                    try:
                        args = json.loads(raw_args) if raw_args else {}
                    except json.JSONDecodeError:
                        args = {}

                    # Studio 内置工具优先路由到沙盒，其余仍按 MCP server 匹配
                    is_capability_tool = studio_mode and tool_name in CAPABILITY_TOOL_NAMES
                    # ask_user 在普通会话也挂载，两种模式下都走澄清拦截分支
                    is_studio_tool = (
                        studio_mode
                        and (tool_name in STUDIO_TOOL_NAMES or is_capability_tool)
                    ) or tool_name == "ask_user"
                    is_mas_plan_tool = (
                        mas_plan_tool_enabled and tool_name == MAS_PLAN_PREVIEW_TOOL_NAME
                    )
                    is_handoff_tool = (not studio_mode) and tool_name == HANDOFF_TOOL_NAME
                    is_subagent_tool = tool_name == PARALLEL_SUBAGENTS_TOOL_NAME
                    is_agentteams_case_tool = tool_name == "create_agentteams_case"
                    # Skills 三层渐进式披露内部工具（非 Studio；Studio 走 capability_load 机制）
                    is_skill_tool = (not studio_mode) and tool_name in SKILL_TOOL_NAMES

                    # 在绑定的 MCP server 中找到拥有该工具的 server
                    server = None
                    if (
                        not is_studio_tool
                        and not is_mas_plan_tool
                        and not is_skill_tool
                        and not is_handoff_tool
                        and not is_subagent_tool
                        and not is_agentteams_case_tool
                    ):
                        server = next(
                            (
                                s
                                for s in active_mcp_servers
                                if any(t.tool_name == tool_name for t in s.tools)
                            ),
                            None,
                        )
                    tool_channel = (
                        "studio-capabilities"
                        if is_capability_tool
                        else "mas-plan"
                        if is_mas_plan_tool
                        else "handoff"
                        if is_handoff_tool
                        else "subagents"
                        if is_subagent_tool
                        else "agentteams-case"
                        if is_agentteams_case_tool
                        else "skills"
                        if is_skill_tool
                        else "studio"
                        if is_studio_tool
                        else (server.name if server else None)
                    )

                    yield ChatChunk(
                        type="tool_call",
                        metadata={
                            "tool_call_id": tc.get("id", ""),
                            "tool_name": tool_name,
                            "arguments": args,
                            "mcp_server": tool_channel,
                        },
                    )

                    if is_mas_plan_tool:
                        result = MASPlanPreviewAdapter().adapt(args)
                    elif is_handoff_tool:
                        from omichub.application.services.tool_bridge_service import (
                            get_tool_bridge_service,
                        )

                        bridge_result = await get_tool_bridge_service().execute(
                            user_id=user_id,
                            tool_name=tool_name,
                            arguments=args,
                            context=tool_context,
                        )
                        result = {
                            "success": bool(bridge_result.get("success")),
                            "result": bridge_result,
                        }
                    elif is_subagent_tool:
                        # 并行子 Agent fan-out：mas_plan_preview 同款特判直调，不经
                        # ToolBridge._package（其 llm_payload 3KB 上限会截断汇总结果）
                        if (
                            subagent_calls_this_round
                            >= get_settings().subagent_max_children_per_message
                        ):
                            limit_error = "本轮已执行过子 Agent 并行分派，请先消化汇总结果再决定下一步"
                            result = {
                                "success": False,
                                "result": {
                                    "llm_payload": {"success": False, "error": limit_error},
                                    "ui_payload": {"error": limit_error},
                                },
                            }
                        else:
                            subagent_calls_this_round += 1
                            fanout_tasks = [
                                item for item in (args.get("tasks") or []) if isinstance(item, dict)
                            ]
                            yield ChatChunk(
                                type="subagents",
                                metadata={
                                    "phase": "started",
                                    "tool_call_id": tc.get("id", ""),
                                    "tasks": [
                                        {
                                            "index": fanout_index,
                                            "agent_id": str(item.get("agent_id") or ""),
                                            "task": str(item.get("task") or "")[:120],
                                        }
                                        for fanout_index, item in enumerate(fanout_tasks, start=1)
                                    ],
                                },
                            )
                            from omichub.application.services.parallel_subagent_tool_service import (
                                ParallelSubAgentToolService,
                            )

                            fanout_envelope = await ParallelSubAgentToolService().run_parallel_subagents(
                                context_summary=str(args.get("context_summary") or ""),
                                tasks=fanout_tasks,
                                context=tool_context,
                            )
                            result = {
                                "success": bool(fanout_envelope.get("success")),
                                "result": {
                                    "llm_payload": fanout_envelope.get("llm_payload"),
                                    "ui_payload": fanout_envelope.get("ui_payload"),
                                },
                            }
                            yield ChatChunk(
                                type="subagents",
                                metadata={
                                    "phase": "aggregated",
                                    "tool_call_id": tc.get("id", ""),
                                    "success": bool(fanout_envelope.get("success")),
                                    "summary": str(
                                        (fanout_envelope.get("llm_payload") or {}).get("summary")
                                        or ""
                                    ),
                                    "progress": (fanout_envelope.get("ui_payload") or {}).get(
                                        "progress"
                                    )
                                    or [],
                                },
                            )
                    elif is_agentteams_case_tool:
                        from omichub.application.services.agentteams_case_tool_service import (
                            AgentTeamsCaseToolService,
                        )
                        from omichub.application.services.tool_bridge_service import (
                            get_tool_bridge_service,
                        )

                        if not args.get("_confirmed"):
                            bridge_result = await get_tool_bridge_service().execute(
                                user_id=user_id,
                                tool_name=tool_name,
                                arguments=args,
                                context=tool_context,
                            )
                            if (bridge_result.get("llm_payload") or {}).get("needs_confirm"):
                                await AgentTeamsCaseToolService().record_confirmation_request(
                                    objective=str(args.get("objective") or ""),
                                    project_id=str(args.get("project_id") or ""),
                                    flow_id=str(args.get("flow_id") or ""),
                                    context=tool_context,
                                )
                            result = {"success": bool(bridge_result.get("success")), "result": bridge_result}
                        else:
                            case_envelope = await AgentTeamsCaseToolService().run(
                                objective=str(args.get("objective") or ""),
                                project_id=str(args.get("project_id") or ""),
                                flow_id=str(args.get("flow_id") or ""),
                                sample_context_refs=args.get("sample_context_refs") or [],
                                context=tool_context,
                            )
                            card = (case_envelope.get("ui_payload") or {}).get("case_card") or {}
                            result = {
                                "success": bool(case_envelope.get("success")),
                                "result": {
                                    "llm_payload": case_envelope.get("llm_payload"),
                                    "ui_payload": case_envelope.get("ui_payload"),
                                },
                            }
                            yield ChatChunk(
                                type="agentteams_case",
                                metadata={
                                    "phase": "created",
                                    "tool_call_id": tc.get("id", ""),
                                    "session_id": current_session_id,
                                    "message_id": ai_message.message_id,
                                    **card,
                                },
                            )
                    elif is_skill_tool:
                        # L2 use_skill / L3 skill_resource：按需加载技能正文与资源
                        # Skill 调用可视化：use_skill（技能加载）发 invoked/completed/failed
                        # 事件并落库 skill_invocations；skill_resource（资源读取）不发事件避免刷屏
                        skill_key_evt = str(
                            args.get("skill_id") or args.get("name") or ""
                        ).strip()
                        bound_skill = next(
                            (
                                s
                                for s in bound_skills
                                if s.skill_id == skill_key_evt or s.name == skill_key_evt
                            ),
                            None,
                        )
                        evt_skill_meta = {
                            "skill_id": bound_skill.skill_id if bound_skill else skill_key_evt,
                            "name": bound_skill.name if bound_skill else skill_key_evt,
                            "version": (bound_skill.version if bound_skill else "") or "",
                            "source": (bound_skill.source_type if bound_skill else "") or "",
                            "icon": (bound_skill.icon if bound_skill else "") or "",
                        }
                        emit_skill_event = tool_name == USE_SKILL_TOOL_NAME
                        if emit_skill_event:
                            yield ChatChunk(
                                type="skill",
                                metadata={
                                    "phase": "invoked",
                                    "tool_call_id": tc.get("id", ""),
                                    "message_id": ai_message.message_id,
                                    "agent": ctx.agent.name if ctx and ctx.agent else "",
                                    **evt_skill_meta,
                                },
                            )
                        skill_start = time.perf_counter()
                        skill_exc: Exception | None = None
                        try:
                            result = await self._execute_skill_tool(
                                tool_name,
                                args,
                                bound_skills,
                                skill_pins=session_mcp_meta.get("skill_pins"),
                            )
                        except Exception as exc:  # noqa: BLE001
                            skill_exc = exc
                            result = {"success": False, "error": str(exc)}
                        skill_ms = (time.perf_counter() - skill_start) * 1000
                        if emit_skill_event:
                            skill_ok = bool(result.get("success"))
                            if skill_ok:
                                resources = ((result.get("result") or {}).get("resources")) or []
                                skill_summary = (
                                    f"已加载技能指令正文"
                                    + (f"（含 {len(resources)} 个资源文件）" if resources else "")
                                )
                            else:
                                skill_summary = ""
                            skill_error = "" if skill_ok else str(result.get("error") or "")
                            yield ChatChunk(
                                type="skill",
                                metadata={
                                    "phase": "completed" if skill_ok else "failed",
                                    "tool_call_id": tc.get("id", ""),
                                    "message_id": ai_message.message_id,
                                    "duration_ms": round(skill_ms, 1),
                                    "summary": skill_summary,
                                    "error": skill_error,
                                    **evt_skill_meta,
                                },
                            )
                            await self._record_skill_invocation(
                                skill_meta=evt_skill_meta,
                                status="completed" if skill_ok else "failed",
                                duration_ms=round(skill_ms, 1),
                                summary=skill_summary,
                                error=skill_error,
                                session_id=current_session_id,
                                message_id=ai_message.message_id,
                                user_id=user_id,
                            )
                        if skill_exc is not None:
                            raise skill_exc
                    elif is_capability_tool and tool_name == CAPABILITY_LIST_TOOL:
                        event = audit_event("list", None, None, True)
                        studio_capability_state = await _persist_capability_state(
                            studio_capability_state, event
                        )
                        visible_catalog = capability_catalog(
                            bound_skills, bound_mcp_servers, studio_capability_state
                        )
                        result = {
                            "success": True,
                            "result": {
                                "llm_payload": visible_catalog,
                                "ui_payload": {
                                    "capabilities": visible_catalog,
                                    "audit_event": event,
                                },
                            },
                        }
                    elif is_capability_tool and tool_name == CAPABILITY_LOAD_TOOL:
                        kind = str(args.get("kind", "")).strip().lower()
                        capability_id = str(args.get("id", "")).strip()
                        if kind not in {"skill", "mcp"} or not capability_id:
                            next_state = None
                            load_result = {
                                "success": False,
                                "error": "kind 必须为 skill/mcp，且 id 不能为空",
                            }
                        else:
                            reserved_names = {
                                item.get("function", {}).get("name", "") for item in tools
                            }
                            next_state, load_result = load_capability(
                                kind,
                                capability_id,
                                bound_skills,
                                bound_mcp_servers,
                                studio_capability_state,
                                reserved_names,
                            )
                        success = bool(load_result.get("success"))
                        event = audit_event("load", kind or None, capability_id or None, success)
                        if next_state is not None:
                            studio_capability_state = next_state
                        studio_capability_state = await _persist_capability_state(
                            studio_capability_state, event
                        )
                        if success:
                            tools, system_prompt, active_mcp_servers = _studio_runtime(
                                studio_capability_state
                            )
                            tools, system_prompt = _attach_mas_plan_tool(tools, system_prompt)
                        result = {
                            "success": success,
                            "result": {
                                "llm_payload": load_result,
                                "ui_payload": {
                                    "capability": load_result,
                                    "audit_event": event,
                                },
                            },
                        }
                    elif is_studio_tool and tool_name == "update_plan":
                        # 待办计划（§5.3 agent.plan）：不打沙盒，直接产出 plan 事件
                        # 驱动右栏待办面板，并把最新计划落库到会话 sandbox_meta.plan；
                        # 结果信封照常走 tool_result/落库流程（tool_invocations 记录）。
                        steps, plan_error = normalize_plan_steps(args)
                        if steps is None:
                            result = {
                                "success": False,
                                "result": {
                                    "llm_payload": {"error": plan_error},
                                    "ui_payload": {"error": plan_error},
                                },
                            }
                        else:
                            plan_session = await self.get_session(current_session_id, user_id)
                            if plan_session is not None:
                                meta = dict(plan_session.sandbox_meta or {})
                                meta["plan"] = {"steps": steps}
                                # 整体重赋值触发 JSONB 变更检测
                                plan_session.sandbox_meta = meta
                                plan_session.updated_at = datetime.now(UTC)
                                await self._db.flush()
                            yield ChatChunk(
                                type="plan",
                                metadata={"tool_call_id": tc.get("id", ""), "steps": steps},
                            )
                            result = {
                                "success": True,
                                "result": {
                                    "llm_payload": {
                                        "steps": steps,
                                        "message": "计划已更新，右栏待办面板已同步",
                                    },
                                    "ui_payload": {"steps": steps},
                                },
                            }
                    elif is_studio_tool and tool_name == "ask_user":
                        # 澄清交互（§3.4）：不进沙盒，产出 ask_request 事件并以"本轮结束"收尾，
                        # 用户在下一条聊天消息中回答，对话自然继续。
                        questions = _normalize_ask_questions(args)
                        first = questions[0]
                        yield ChatChunk(
                            type="ask_request",
                            metadata={
                                "tool_call_id": tc.get("id", ""),
                                "questions": questions,
                                # 兼容旧前端：首问题的平铺字段
                                "question": first["question"],
                                "options": first["options"],
                            },
                        )
                        ask_payload: dict[str, Any] = {
                            "questions": questions,
                            "question": first["question"],
                            "options": first["options"],
                            "message": "问题已展示给用户，用户将在下一条消息中回答。本轮回复到此结束，请等待用户答复。",
                        }
                        result = {
                            "success": True,
                            "result": {"llm_payload": ask_payload, "ui_payload": dict(ask_payload)},
                        }
                        stop_after_tools = True
                    elif is_studio_tool:
                        # 审批闸（§3）：supervised 模式下写/执行类工具先经用户批准
                        approval_passed = True
                        if (
                            studio_permission_mode == "supervised"
                            and tool_name in APPROVAL_REQUIRED_TOOLS
                        ):
                            approval_service = get_studio_approval_service()
                            approval = await approval_service.create(
                                user_id=user_id,
                                session_id=current_session_id,
                                tool_call_id=tc.get("id", ""),
                                tool_name=tool_name,
                                arguments=args,
                                risk_hint=_studio_risk_hint(tool_name, args),
                            )
                            yield ChatChunk(
                                type="approval_request",
                                metadata={
                                    "approval_id": approval["approval_id"],
                                    "tool_call_id": tc.get("id", ""),
                                    "tool_name": tool_name,
                                    "arguments": args,
                                    "risk_hint": approval["risk_hint"],
                                    "timeout_seconds": APPROVAL_TTL_SECONDS,
                                },
                            )
                            resolution = await approval_service.wait_resolution(
                                approval["approval_id"]
                            )
                            action = str(resolution.get("action") or "timeout")
                            yield ChatChunk(
                                type="approval_resolved",
                                metadata={
                                    "approval_id": approval["approval_id"],
                                    "tool_call_id": tc.get("id", ""),
                                    "action": action,
                                },
                            )
                            if action == "edited" and isinstance(
                                resolution.get("modified_args"), dict
                            ):
                                args = resolution["modified_args"]
                                action = "approved"
                            if action != "approved":
                                approval_passed = False
                                reason = resolution.get("reason") or (
                                    "用户未响应（超时）"
                                    if action == "timeout"
                                    else "用户拒绝了该操作"
                                )
                                reject_payload = {"rejected": True, "error": reason}
                                result = {
                                    "success": False,
                                    "rejected": True,
                                    "result": {
                                        "llm_payload": reject_payload,
                                        "ui_payload": dict(reject_payload),
                                    },
                                }
                        # 沙盒执行：sandbox_execute 的 stdout/stderr 以 tool_output 事件边跑边推
                        if approval_passed:
                            result = {}
                            async for item in stream_studio_tool(
                                tool_name,
                                args,
                                current_session_id,
                                image=studio_image,
                                tool_call_id=tc.get("id", ""),
                                user_id=user_id,
                                db=self._db,
                            ):
                                if isinstance(item, ChatChunk):
                                    yield item
                                else:
                                    result = item
                    elif server is None:
                        if tool_name == "knowledge_search":
                            result = await self._knowledge_search_chat(args)
                        elif tool_name == "web_search":
                            query = str(args.get("query") or "")
                            yield ChatChunk(
                                type="web_search",
                                content=query,
                                metadata={"status": "searching"},
                            )
                            result = await self._web_search(args)
                            search_payload = result.get("result") if isinstance(result, dict) else None
                            search_results = (
                                search_payload.get("results", [])
                                if isinstance(search_payload, dict)
                                else []
                            )
                            if result.get("success") and isinstance(search_results, list):
                                web_sources.extend(
                                    item for item in search_results if isinstance(item, dict)
                                )
                                if search_results:
                                    yield ChatChunk(
                                        type="web_search_results",
                                        metadata={"sources": search_results},
                                    )
                                else:
                                    yield ChatChunk(
                                        type="web_search",
                                        content="未找到相关结果，已基于模型知识回答",
                                        metadata={"status": "empty"},
                                    )
                            else:
                                yield ChatChunk(
                                    type="web_search",
                                    content="联网搜索失败，已基于模型自身知识回答",
                                    metadata={"status": "failed"},
                                )
                        else:
                            result = {
                                "success": False,
                                "error": f"工具 {tool_name} 未挂载到该 Agent",
                            }
                    else:
                        result = await mcp_client.call_tool(
                            server,
                            tool_name,
                            args,
                            user_id=user_id,
                            context=tool_context,
                        )

                    # 双通道：llm_payload 给 LLM，ui_payload 给前端
                    tool_output = result.get("result") if isinstance(result, dict) else result
                    if isinstance(tool_output, dict) and ("llm_payload" in tool_output or "ui_payload" in tool_output):
                        ui_payload = tool_output.get("ui_payload")
                        llm_result = tool_output.get("llm_payload", tool_output)
                    else:
                        ui_payload = None
                        llm_result = tool_output if tool_output is not None else result
                    if not isinstance(llm_result, dict):
                        llm_result = {"result": llm_result}

                    yield ChatChunk(
                        type="tool_result",
                        metadata={
                            "tool_call_id": tc.get("id", ""),
                            "tool_name": tool_name,
                            "mcp_server": tool_channel,
                            "success": bool(result.get("success")),
                            "result": llm_result,
                            "ui_payload": ui_payload,
                        },
                    )
                    timeline.append(
                        {
                            "kind": "tool",
                            "tool_call_id": tc.get("id", ""),
                            "tool_name": tool_name,
                        }
                    )
                    # Studio 工具调用随消息落库：历史重载时凭 ui_payload 渲染代码卡片/产物/diff
                    if is_studio_tool or is_mas_plan_tool:
                        studio_invocations.append(
                            {
                                "tool_call_id": tc.get("id", ""),
                                "tool_name": tool_name,
                                "arguments": args,
                                "success": bool(result.get("success")),
                                "result": llm_result,
                                "ui_payload": ui_payload,
                            }
                        )
                        await self.update_message_content(
                            ai_message.message_id,
                            full_content,
                            "streaming",
                            {"tool_invocations": studio_invocations, "timeline": timeline},
                        )
                    elif is_agentteams_case_tool and bool(result.get("success")):
                        case_card = (ui_payload or {}).get("case_card")
                        if isinstance(case_card, dict):
                            await self.update_message_content(
                                ai_message.message_id,
                                full_content,
                                "streaming",
                                {"agentteams_cases": [case_card], "timeline": timeline},
                            )
                    llm_content = json.dumps(llm_result, ensure_ascii=False, default=str)
                    # 技能正文（L2）允许更长回灌；fan-out 汇总含多个子任务结论放宽到 12000；
                    # 其余工具结果保持 4000 字符护栏
                    llm_limit = (
                        24000
                        if is_skill_tool
                        else 12000
                        if is_subagent_tool or is_agentteams_case_tool
                        else 4000
                    )
                    if len(llm_content) > llm_limit:
                        llm_content = llm_content[:llm_limit]
                    llm_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.get("id", ""),
                            "content": llm_content,
                        }
                    )
                    directive = extract_handoff_directive(result) if is_handoff_tool else None
                    if directive is not None and bool(result.get("success")):
                        target_ctx, target_model, target_skills, target_servers, target_tools, target_prompt = (
                            await _prepare_handoff_target(directive)
                        )
                        await AgentHandoffService(self._db).record_handoff(
                            user_id=user_id,
                            session_id=current_session_id,
                            directive=directive,
                        )
                        handoff_session = await self.get_session(current_session_id, user_id)
                        if handoff_session is not None:
                            handoff_session.agent_id = str(directive["target_agent_id"])
                            handoff_session.model_id = target_model.id
                            handoff_session.updated_at = datetime.now(UTC)
                        await self.update_message_content(
                            ai_message.message_id,
                            full_content,
                            "streaming",
                            {
                                "agent_id": str(directive["target_agent_id"]),
                                "model": target_model.name,
                                "handoff_chain": [
                                    {
                                        "from": directive["source_agent_id"],
                                        "to": directive["target_agent_id"],
                                        "reason": directive["reason"],
                                        "hop_index": directive["hop_index"],
                                    }
                                ],
                            },
                        )
                        yield ChatChunk(
                            type="handoff",
                            metadata={
                                **directive,
                                "session_id": current_session_id,
                                "message_id": ai_message.message_id,
                            },
                        )
                        ctx = target_ctx
                        agent_id = target_ctx.agent.agent_id
                        model_config = target_model
                        bound_skills = target_skills
                        bound_mcp_servers = target_servers
                        active_mcp_servers = target_servers
                        tools = target_tools
                        system_prompt = target_prompt
                        tool_context = ToolInvocationContext(
                            user_id=user_id,
                            agent_id=agent_id,
                            session_id=current_session_id,
                            db=self._db,
                        )
                        llm_messages = [{"role": "user", "content": str(directive["packet"])}]
                        handoff_requested = True
                        break

                if handoff_requested:
                    continue

                # ask_user：问题已展示，收尾跳出工具大循环，等用户下一条消息
                if stop_after_tools:
                    completion_metadata = {
                        **({"usage": last_usage} if last_usage else {}),
                        **({"web_sources": web_sources} if web_sources else {}),
                        **({"timeline": timeline} if timeline else {}),
                    }
                    await self.update_message_content(
                        ai_message.message_id,
                        full_content,
                        "complete",
                        completion_metadata or None,
                    )
                    await self._apply_usage_to_session(ai_message.message_id, last_usage)
                    yield ChatChunk(
                        type="done",
                        metadata={
                            "session_id": current_session_id,
                            "message_id": ai_message.message_id,
                            "usage": last_usage,
                        },
                    )
                    return

            # 超过最大轮次仍未结束
            await self.update_message_content(
                ai_message.message_id,
                full_content,
                "complete",
                {
                    "warning": "工具调用轮次达上限，已提前结束",
                    **({"web_sources": web_sources} if web_sources else {}),
                    **({"timeline": timeline} if timeline else {}),
                },
            )
            # 通知前端轮次触顶：由用户弹窗选择是否以扩展上限继续
            yield ChatChunk(
                type="round_limit",
                content=f"工具调用轮次达到上限（{max_rounds}），任务提前结束",
                metadata={
                    "session_id": current_session_id,
                    "message_id": ai_message.message_id,
                    "max_rounds": max_rounds,
                    "can_extend": max_rounds < 1000,
                },
            )
            yield ChatChunk(
                type="done",
                metadata={
                    "session_id": current_session_id,
                    "message_id": ai_message.message_id,
                },
            )

        except Exception as e:  # noqa: BLE001
            await self.update_message_content(
                ai_message.message_id,
                full_content or f"生成失败: {e}",
                "error",
                {"error": str(e)},
            )
            yield ChatChunk(
                type="error",
                content=f"生成失败: {e}",
                metadata={"session_id": current_session_id, "message_id": ai_message.message_id},
            )

    async def _stream_agent_chat_langgraph(
        self,
        *,
        user_id: str,
        session_id: str,
        ai_message_id: str,
        model_config: Any,
        llm_messages: list[dict[str, Any]],
        system_prompt: str | None,
        tools: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
        deep_thinking: bool,
        active_mcp_servers: list[Any],
        mcp_client: Any,
        tool_context: Any,
        skills: list[Any] | None = None,
        skill_pins: dict[str, int] | None = None,
        web_sources: list[dict[str, Any]] | None = None,
        handoff_handler: Any | None = None,
    ) -> AsyncIterator[ChatChunk]:
        """LangGraph 引擎路径：状态图驱动 ReAct 循环，事件协议与手写循环一致

        tool_executor 复刻 legacy 非 Studio 工具路由：技能内部工具（use_skill /
        skill_resource）→ self._execute_skill_tool；ask_user → 澄清信封（图经
        state["ask_request"] 收尾，由本函数产出 ask_request 事件）；knowledge_search →
        self._knowledge_search_chat；MCP server 匹配 → MCPClient.call_tool；
        web_search → self._web_search；未挂载 → 报错信封。
        """
        runtime_state: dict[str, Any] = {
            "model_config": model_config,
            "llm_messages": list(llm_messages),
            "system_prompt": system_prompt,
            "tools": list(tools),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "active_mcp_servers": list(active_mcp_servers),
            "tool_context": tool_context,
            "skills": list(skills or []),
            "skill_pins": skill_pins or {},
        }
        persisted_web_sources = web_sources if web_sources is not None else []
        from omichub.infrastructure.execution.langgraph_nodes import NodeDeps
        from omichub.infrastructure.execution.langgraph_runtime import (
            LangGraphRuntimeService,
        )

        def _find_server(tool_name: str) -> Any:
            return next(
                (
                    s
                    for s in runtime_state["active_mcp_servers"]
                    if any(t.tool_name == tool_name for t in s.tools)
                ),
                None,
            )

        def _resolve_channel(tool_name: str) -> str | None:
            if tool_name == HANDOFF_TOOL_NAME:
                return "handoff"
            if tool_name in SKILL_TOOL_NAMES:
                return "skills"
            server = _find_server(tool_name)
            return server.name if server else None

        async def _tool_executor(
            tool_name: str, args: dict[str, Any], tool_call_id: str
        ) -> dict[str, Any]:
            if tool_name == HANDOFF_TOOL_NAME:
                from omichub.application.services.tool_bridge_service import (
                    get_tool_bridge_service,
                )

                bridge_result = await get_tool_bridge_service().execute(
                    user_id=user_id,
                    tool_name=tool_name,
                    arguments=args,
                    context=runtime_state["tool_context"],
                )
                return {
                    "success": bool(bridge_result.get("success")),
                    "result": bridge_result,
                }
            if tool_name in SKILL_TOOL_NAMES:
                return await self._execute_skill_tool(
                    tool_name,
                    args,
                    runtime_state["skills"],
                    skill_pins=runtime_state.get("skill_pins"),
                )
            if tool_name == "ask_user":
                # 与 legacy stop_after_tools 同一信封；图经 state["ask_request"]
                # 结束后由下方产出 ask_request 事件并收尾本轮。
                questions = _normalize_ask_questions(args)
                first = questions[0]
                ask_payload: dict[str, Any] = {
                    "questions": questions,
                    "question": first["question"],
                    "options": first["options"],
                    "message": "问题已展示给用户，用户将在下一条消息中回答。本轮回复到此结束，请等待用户答复。",
                }
                return {
                    "success": True,
                    "result": {"llm_payload": ask_payload, "ui_payload": dict(ask_payload)},
                }
            if tool_name == "knowledge_search":
                return await self._knowledge_search_chat(args)
            if tool_name == "web_search":
                result = await self._web_search(args)
                search_payload = result.get("result") if isinstance(result, dict) else None
                search_results = (
                    search_payload.get("results", [])
                    if isinstance(search_payload, dict)
                    else []
                )
                if isinstance(search_results, list):
                    persisted_web_sources.extend(
                        item for item in search_results if isinstance(item, dict)
                    )
                return result
            server = _find_server(tool_name)
            if server is None:
                return {"success": False, "error": f"工具 {tool_name} 未挂载到该 Agent"}
            return await mcp_client.call_tool(
                server,
                tool_name,
                args,
                user_id=user_id,
                context=runtime_state["tool_context"],
            )

        full_content = ""
        update_counter = 0
        first_chunk_sent = False
        accumulated_usage: dict[str, Any] | None = None
        try:
            while True:
                deps = NodeDeps(
                    model_config=runtime_state["model_config"],
                    system_prompt=runtime_state["system_prompt"],
                    temperature=runtime_state["temperature"],
                    max_tokens=runtime_state["max_tokens"],
                    tools=runtime_state["tools"] or None,
                    deep_thinking=deep_thinking,
                    tool_executor=_tool_executor,
                    channel_resolver=_resolve_channel,
                    chat_stream=provider_manager.chat_stream,
                )
                runtime = LangGraphRuntimeService(deps)
                async for chunk in runtime.stream(runtime_state["llm_messages"]):
                    if chunk.type == "text":
                        if chunk.metadata.get("is_reasoning"):
                            # 推理过程不并入最终正文，但仍透传给前端
                            yield chunk
                            continue
                        full_content += chunk.content
                        update_counter += 1
                        if update_counter % 5 == 0:
                            await self.update_message_content(
                                ai_message_id, full_content, "streaming"
                            )
                        if not first_chunk_sent:
                            chunk.metadata["session_id"] = session_id
                            chunk.metadata["message_id"] = ai_message_id
                            first_chunk_sent = True
                        yield chunk
                    elif chunk.type == "error":
                        await self.update_message_content(
                            ai_message_id,
                            full_content or f"生成失败: {chunk.content}",
                            "error",
                            {"error": chunk.content},
                        )
                        yield chunk
                        return
                    else:
                        # tool_call / tool_result 直接透传（metadata 已对齐 legacy）
                        yield chunk

                accumulated_usage = merge_token_usage(accumulated_usage, runtime.last_usage)
                # ask_user 澄清：问题经 ask_request 事件展示给用户，收尾本轮，
                # 等用户下一条消息回答（对齐 legacy stop_after_tools 语义）。
                ask_request = runtime.last_ask_request
                if ask_request is not None:
                    questions = _normalize_ask_questions(ask_request.get("args") or {})
                    first = questions[0]
                    yield ChatChunk(
                        type="ask_request",
                        metadata={
                            "tool_call_id": ask_request.get("tool_call_id", ""),
                            "questions": questions,
                            # 兼容旧前端：首问题的平铺字段
                            "question": first["question"],
                            "options": first["options"],
                        },
                    )
                    break
                directive = runtime.last_handoff
                if directive is None:
                    break
                if handoff_handler is None:
                    await self.update_message_content(
                        ai_message_id,
                        full_content or "Agent 转交未被当前运行时处理",
                        "error",
                        {"error": "Agent 转交未被当前运行时处理"},
                    )
                    yield ChatChunk(type="error", content="Agent 转交未被当前运行时处理")
                    return
                next_state = await handoff_handler(directive)
                runtime_state.update(next_state)
                yield ChatChunk(
                    type="handoff",
                    metadata={
                        **directive,
                        "session_id": session_id,
                        "message_id": ai_message_id,
                    },
                )
        except Exception as e:  # noqa: BLE001
            await self.update_message_content(
                ai_message_id,
                full_content or f"生成失败: {e}",
                "error",
                {"error": str(e)},
            )
            yield ChatChunk(
                type="error",
                content=f"生成失败: {e}",
                metadata={"session_id": session_id, "message_id": ai_message_id},
            )
            return

        # 收尾：complete + usage + 会话用量累计 + done（与 legacy 一致）
        last_usage = accumulated_usage
        await self.update_message_content(
            ai_message_id,
            full_content,
            "complete",
            {
                **({"usage": last_usage} if last_usage else {}),
                **({"web_sources": persisted_web_sources} if persisted_web_sources else {}),
            }
            or None,
        )
        await self._apply_usage_to_session(ai_message_id, last_usage)
        yield ChatChunk(
            type="done",
            metadata={
                "session_id": session_id,
                "message_id": ai_message_id,
                "usage": last_usage,
            },
        )

    # --- 多模态与联网搜索辅助 ---

    @staticmethod
    async def _build_multimodal_messages(
        messages: list[dict[str, Any]], attachments: list[Any]
    ) -> list[dict[str, Any]]:
        """把附件注入到最后一条用户消息中。

        兼容策略：
        - 只有文本/文件附件时，保持 content 为字符串（对 Qwen 等国产模型兼容性最好）。
        - 包含图片附件时，使用 OpenAI 多模态 list 格式。
        """
        if not messages:
            return messages
        target_index = max(
            (i for i, m in enumerate(messages) if m.get("role") == "user"),
            default=-1,
        )
        if target_index == -1:
            return messages

        target = messages[target_index]
        base_text = str(target.get("content", ""))

        # attachments 可能是 Pydantic ChatAttachment 对象列表，统一转成 dict
        attachment_dicts: list[dict[str, Any]] = [
            att.model_dump() if hasattr(att, "model_dump") else dict(att)
            for att in (attachments or [])
        ]

        has_image = any(
            att.get("type") == "image"
            or (att.get("mime_type", "").startswith("image/"))
            for att in attachment_dicts
        )

        async def _build_snippets(att: dict[str, Any]) -> list[str]:
            """为单个附件生成文本提示片段。"""
            text = await ChatService._read_attachment_text(att)
            file_id = att.get("file_id", "")
            max_len = 8000
            snippets: list[str] = []
            if file_id:
                # file_id 可能已带 scheme（file://uuid 或 upload://hex）；无 scheme 时按上传文件处理
                ref = file_id if "://" in file_id else f"upload://{file_id}"
                snippets.append(
                    f"[文件: {att.get('name', '')}，file_id: {ref}，"
                    f"可用 workspace_read_file(file_id=\"{ref}\") 读取内容，"
                    f"或在其它工具参数中直接引用该 file_id]"
                )
            if text:
                snippet = text[:max_len] + ("\n...（已截断）" if len(text) > max_len else "")
                snippets.append(f"[文件内容预览: {att.get('name', '')}]\n{snippet}")
            if not snippets:
                snippets.append(f"[文件 {att.get('name', '')} 读取失败或为空]")
            return snippets

        new_messages = list(messages)

        if not has_image:
            # 纯文本附件：拼成字符串，兼容性最好
            parts = [base_text]
            for att in attachment_dicts:
                snippets = await _build_snippets(att)
                parts.append("\n\n".join(snippets))
            new_messages[target_index] = {**target, "content": "\n\n".join(parts)}
            return new_messages

        # 含图片：使用 OpenAI 多模态 list 格式
        content: list[dict[str, Any]] = [{"type": "text", "text": base_text}]
        for att in attachment_dicts:
            att_type = att.get("type", "file")
            mime = att.get("mime_type", "")
            if att_type == "image" or (mime and mime.startswith("image/")):
                data_url = await ChatService._read_attachment_data_url(att)
                if data_url:
                    content.append({"type": "image_url", "image_url": {"url": data_url}})
                else:
                    content.append(
                        {
                            "type": "text",
                            "text": f"\n\n[图片 {att.get('name', '')} 读取失败]",
                        }
                    )
            else:
                snippets = await _build_snippets(att)
                content.append({"type": "text", "text": "\n\n" + "\n\n".join(snippets)})

        new_messages[target_index] = {**target, "content": content}
        return new_messages

    @staticmethod
    def _resolve_attachment_path(att_url: str) -> str | None:
        """把聊天附件 URL 解析为本地路径，非本地上传或越权则返回 None。"""
        prefix = "/api/v1/files/chat-upload/"
        if not att_url.startswith(prefix):
            return None
        rest = att_url[len(prefix) :]
        parts = rest.split("/", 1)
        if len(parts) != 2:
            return None
        user_id, filename = parts
        filename = Path(filename).name
        from omichub.infrastructure.config.storage_config import get_user_chat_upload_dir

        path = get_user_chat_upload_dir(user_id) / filename
        if path.is_file():
            return str(path)
        return None

    @staticmethod
    def _is_internal_url(url: str) -> bool:
        """禁止访问内网、回环、链路本地、metadata 等地址，防止 SSRF。"""
        if not url:
            return True
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return True
        host = parsed.hostname
        if not host:
            return True
        if host == "169.254.169.254":
            return True
        try:
            addr = ipaddress.ip_address(host)
            return (
                addr.is_loopback
                or addr.is_private
                or addr.is_link_local
                or addr.is_multicast
                or addr.is_reserved
            )
        except ValueError:
            # 域名：放行；如需更严格可再校验是否解析到内网
            return False

    @staticmethod
    async def _read_attachment_data_url(att: dict[str, Any]) -> str:
        """读取附件并返回 base64 data URL（主要用于图片）。"""
        import base64

        att_url = att.get("url", "")
        mime = att.get("mime_type") or "application/octet-stream"
        local_path = ChatService._resolve_attachment_path(att_url)
        try:
            if local_path:
                async with await anyio.open_file(local_path, "rb") as f:
                    data = await f.read()
            else:
                if ChatService._is_internal_url(att_url):
                    logger.warning(f"拒绝读取内网/非法附件 URL: {att_url}")
                    return ""
                async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                    resp = await client.get(att_url)
                    resp.raise_for_status()
                    data = resp.content
            encoded = base64.b64encode(data).decode("ascii")
            return f"data:{mime};base64,{encoded}"
        except Exception as e:  # noqa: BLE001
            logger.warning(f"读取附件失败 {att.get('name')}: {e}")
            return ""

    @staticmethod
    async def _read_attachment_text(att: dict[str, Any]) -> str:
        """读取文本类附件内容。"""
        att_url = att.get("url", "")
        local_path = ChatService._resolve_attachment_path(att_url)
        try:
            if local_path:
                async with await anyio.open_file(
                    local_path, "r", encoding="utf-8", errors="ignore"
                ) as f:
                    return await f.read()
            if ChatService._is_internal_url(att_url):
                logger.warning(f"拒绝读取内网/非法附件 URL: {att_url}")
                return ""
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                resp = await client.get(att_url)
                resp.raise_for_status()
                return resp.text
        except Exception as e:  # noqa: BLE001
            logger.warning(f"读取文本附件失败 {att.get('name')}: {e}")
            return ""

    async def _resolve_model(self, model_id: uuid.UUID) -> AIProviderConfigModel | None:
        """按 ID 解析已启用的模型配置。"""
        result = await self._db.execute(
            select(AIProviderConfigModel).where(
                AIProviderConfigModel.id == model_id,
                AIProviderConfigModel.is_active == True,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def _apply_usage_to_session(
        self,
        message_id: str,
        usage: dict[str, Any] | None,
    ) -> None:
        """把 LLM 返回的 usage 累加到会话 total_tokens，并写入消息 metadata。"""
        if not usage:
            return
        try:
            total = int(
                usage.get("total_tokens")
                or usage.get("total")
                or (
                    int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
                    + int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
                )
                or 0
            )
            if total <= 0:
                return
            msg_result = await self._db.execute(
                select(ChatMessageModel).where(ChatMessageModel.message_id == message_id)
            )
            msg = msg_result.scalar_one_or_none()
            if not msg:
                return
            session_result = await self._db.execute(
                select(ChatSessionModel).where(ChatSessionModel.session_id == msg.session_id)
            )
            session = session_result.scalar_one_or_none()
            if session:
                session.total_tokens += total
                await self._deduct_ai_cookies(session, total, message_id)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"累加 token 用量失败: {e}")

    async def _ensure_cookie_balance(self, user_id: str) -> str | None:
        """AI 对话准入闸门：饼干余额不足时返回错误文案，放行返回 None。"""
        settings = get_settings()
        if not settings.enable_cookie_system:
            return None
        try:
            from omichub.application.services.cookie_service import CookieService

            balance = await CookieService(self._db).check_balance(uuid.UUID(user_id))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"AI 对话饼干余额检查失败，放行: {e}")
            return None
        if balance > 0:
            return None
        rate = settings.ai_token_cookie_rate
        return (
            f"饼干余额不足，无法使用 AI 助手（每 1K tokens 消耗 {rate} 🥫）。"
            "请先通过提交分析任务赚取饼干后再试。"
        )

    async def _deduct_ai_cookies(
        self, session: ChatSessionModel, tokens: int, message_id: str
    ) -> None:
        """按 ai_token_cookie_rate 🥫/1K tokens 从会话属主账户扣减饼干。"""
        settings = get_settings()
        if not settings.enable_cookie_system or tokens <= 0:
            return
        try:
            from omichub.application.services.cookie_service import CookieService

            await CookieService(self._db).spend_ai_tokens(
                user_id=uuid.UUID(str(session.user_id)),
                tokens=tokens,
                source_id=message_id,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"AI 对话饼干扣减失败: {e}")

    async def _record_skill_invocation(
        self,
        *,
        skill_meta: dict[str, Any],
        status: str,
        duration_ms: float,
        summary: str,
        error: str,
        session_id: str,
        message_id: Any,
        user_id: str | None,
    ) -> None:
        """落库一条技能调用记录（绝不阻断对话流：任何失败只记日志）。"""
        try:
            from omichub.application.services.skill_service import SkillService

            def _to_uuid(value: Any) -> uuid.UUID | None:
                try:
                    return uuid.UUID(str(value)) if value else None
                except (ValueError, AttributeError, TypeError):
                    return None

            await SkillService(self._db).record_invocation(
                skill_id=str(skill_meta.get("skill_id") or ""),
                skill_name=str(skill_meta.get("name") or ""),
                skill_version=str(skill_meta.get("version") or "") or None,
                source=str(skill_meta.get("source") or ""),
                tool_name=USE_SKILL_TOOL_NAME,
                status=status,
                duration_ms=duration_ms,
                summary=summary,
                error=error,
                session_id=_to_uuid(session_id),
                message_id=_to_uuid(message_id),
                user_id=_to_uuid(user_id),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("技能调用记录落库失败（忽略）: {}", exc)

    async def _execute_skill_tool(
        self,
        tool_name: str,
        args: dict[str, Any],
        skills: list[Any],
        skill_pins: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        """技能工具执行入口（带 Trace/Log/Metrics 埋点）。"""
        skill_key = str(args.get("skill_id") or args.get("name") or "").strip()
        tracer = get_tracer("omichub.chat")
        with tracer.start_as_current_span(
            "skill.execute",
            attributes={"skill.tool_name": tool_name, "skill.skill_id": skill_key},
        ) as span:
            start = time.perf_counter()
            status = "success"
            try:
                result = await self._execute_skill_tool_inner(
                    tool_name, args, skills, skill_pins=skill_pins
                )
                if not result.get("success"):
                    status = "error"
                return result
            except Exception as exc:  # noqa: BLE001
                status = "error"
                span.record_exception(exc)
                raise
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                attrs = {"skill.tool_name": tool_name, "skill.status": status}
                span.set_attribute("skill.status", status)
                span.set_attribute("skill.duration_ms", round(duration_ms, 2))
                try:
                    _skill_count.add(1, attrs)
                    _skill_duration.record(duration_ms, attrs)
                except Exception:  # noqa: BLE001
                    pass
                logger.bind(
                    event="skill.execute",
                    tool_name=tool_name,
                    skill_id=skill_key,
                    status=status,
                    duration_ms=round(duration_ms, 2),
                ).info("skill.execute completed")

    async def _execute_skill_tool_inner(
        self,
        tool_name: str,
        args: dict[str, Any],
        skills: list[Any],
        skill_pins: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        """技能渐进式披露内部工具：

        - use_skill（L2）：返回已挂载技能的 SKILL.md 正文。会话 pin 优先（会话启动时
          锁定的版本快照），其次磁盘优先，最后 DB prompt 兜底
        - skill_resource（L3）：按需读取技能 references/assets 文件，代码不进上下文
        """
        from omichub.infrastructure.skills import skill_store

        skill_key = str(args.get("skill_id") or args.get("name") or "").strip()
        skill = next(
            (s for s in skills if s.skill_id == skill_key or s.name == skill_key), None
        )
        if skill is None:
            mounted = "、".join(s.skill_id for s in skills) or "无"
            return {
                "success": False,
                "error": f"技能 '{skill_key}' 未挂载到该助手（已挂载：{mounted}）",
            }

        if tool_name == USE_SKILL_TOOL_NAME:
            body: str | None = None
            pinned_from: str | None = None
            pinned_rev = (skill_pins or {}).get(skill.skill_id)
            if pinned_rev:
                # 会话 pin：读取会话启动时锁定 revision 的快照正文，
                # 会话中途升级/回滚不影响进行中的任务
                try:
                    from omichub.infrastructure.database.models.skill import (
                        SkillVersionModel,
                    )

                    snap = (
                        await self._db.execute(
                            select(SkillVersionModel).where(
                                SkillVersionModel.skill_id == skill.skill_id,
                                SkillVersionModel.revision == int(pinned_rev),
                            )
                        )
                    ).scalar_one_or_none()
                    if snap and (snap.prompt or "").strip():
                        body = snap.prompt
                        pinned_from = f"r{snap.revision}"
                except Exception as pin_exc:  # noqa: BLE001
                    logger.warning("读取 pin 版本失败（回落当前内容）: {}", pin_exc)
            if body is None:
                body = skill_store.read_skill_body(skill.skill_id) or (skill.prompt or "")
            if not body.strip():
                return {"success": False, "error": f"技能 '{skill.name}' 暂无指令正文"}
            resources = skill_store.list_skill_files(skill.skill_id)
            return {
                "success": True,
                "result": {
                    "skill_id": skill.skill_id,
                    "name": skill.name,
                    "instructions": body,
                    "pinned_revision": pinned_from,
                    "resources": resources or None,
                    "resource_hint": (
                        "正文引用的 references/assets 文件请用 skill_resource 工具读取"
                        if resources
                        else None
                    ),
                },
            }

        if tool_name == SKILL_RESOURCE_TOOL_NAME:
            path = str(args.get("path") or "").strip()
            if not path:
                return {"success": False, "error": "缺少 path 参数"}
            ok, msg, content = skill_store.read_skill_resource(skill.skill_id, path)
            if not ok or content is None:
                return {"success": False, "error": msg}
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                return {
                    "success": True,
                    "result": {
                        "path": path,
                        "note": "该资源为二进制文件，无法作为文本读取",
                    },
                }
            return {"success": True, "result": {"path": path, "content": text}}

        return {"success": False, "error": f"未知技能工具: {tool_name}"}

    async def _web_search(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """执行默认联网搜索服务商，并返回统一结果结构。"""
        query = arguments.get("query", "")
        top_n = int(arguments.get("top_n", 5))
        if not query.strip():
            return {"success": False, "error": "缺少搜索关键词"}
        try:
            from omichub.application.services.search_provider_service import SearchProviderService

            results = await SearchProviderService(self._db).search_default(query, top_n)
            return {"success": True, "result": {"query": query, "results": results}}
        except Exception as exc:  # noqa: BLE001
            logger.warning("联网搜索工具调用失败: %s", exc)
            return {"success": False, "error": "联网搜索失败，已跳过搜索结果"}

    async def _knowledge_search_chat(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """普通聊天的知识库检索：复用 Studio 工具实现（只检索已发布文档的当前修订）。"""
        from omichub.application.services.studio_tools import _knowledge_search

        try:
            return await _knowledge_search(arguments, self._db)
        except Exception as exc:  # noqa: BLE001
            logger.warning("知识库检索工具调用失败: %s", exc)
            return {"success": False, "error": "知识库检索失败，已跳过"}

    # --- 助手管理 ---

    async def init_builtin_assistants(self) -> None:
        result = await self._db.execute(
            select(ChatAssistantModel).where(ChatAssistantModel.is_builtin == True)  # noqa: E712
        )
        if result.scalars().first():
            return
        for cfg in BUILTIN_ASSISTANTS:
            self._db.add(ChatAssistantModel(is_builtin=True, is_active=True, **cfg))
        await self._db.flush()

    async def list_assistants(self, category: str | None = None) -> list[ChatAssistantDTO]:
        await self.init_builtin_assistants()
        query = select(ChatAssistantModel).where(ChatAssistantModel.is_active == True)  # noqa: E712
        if category:
            query = query.where(ChatAssistantModel.category == category)
        query = query.order_by(ChatAssistantModel.created_at)
        result = await self._db.execute(query)
        return [self._to_ast_dto(a) for a in result.scalars().all()]

    async def get_assistant(self, assistant_id: str) -> ChatAssistantModel | None:
        result = await self._db.execute(
            select(ChatAssistantModel).where(ChatAssistantModel.assistant_id == assistant_id)
        )
        return result.scalar_one_or_none()

    async def get_assistant_dto(self, assistant_id: str) -> ChatAssistantDTO:
        ast = await self.get_assistant(assistant_id)
        if not ast:
            raise NotFoundError("助手不存在")
        return self._to_ast_dto(ast)

    async def create_custom_assistant(
        self,
        user_id: str,
        assistant_id: str,
        name: str,
        description: str,
        system_prompt: str,
        default_model_id: uuid.UUID | None = None,
        default_temperature: float = 0.3,
        default_max_tokens: int = 4096,
        icon: str = "\U0001f916",
        color: str = "#4f8ef7",
        category: str = "general",
    ) -> ChatAssistantDTO:
        existing = await self.get_assistant(assistant_id)
        if existing:
            raise BusinessError(f"助手 ID '{assistant_id}' 已存在")
        ast = ChatAssistantModel(
            assistant_id=assistant_id,
            name=name,
            description=description,
            system_prompt=system_prompt,
            default_model_id=default_model_id,
            default_temperature=default_temperature,
            default_max_tokens=default_max_tokens,
            icon=icon,
            color=color,
            category=category,
            is_builtin=False,
            is_active=True,
            created_by=user_id,
        )
        self._db.add(ast)
        await self._db.flush()
        return self._to_ast_dto(ast)

    async def list_all_assistants(self) -> list[ChatAssistantDTO]:
        """列出所有助手（含停用，供管理员）"""
        await self.init_builtin_assistants()
        result = await self._db.execute(
            select(ChatAssistantModel).order_by(
                ChatAssistantModel.is_default.desc(), ChatAssistantModel.created_at
            )
        )
        return [self._to_ast_dto(a) for a in result.scalars().all()]

    async def update_assistant(self, assistant_id: str, req: UpdateAssistantRequest) -> ChatAssistantDTO:
        ast = await self.get_assistant(assistant_id)
        if not ast:
            raise NotFoundError("助手不存在")
        data = req.model_dump(exclude_unset=True)
        # is_default=True 时需先清除其他助手默认标记
        if data.get("is_default"):
            result = await self._db.execute(
                select(ChatAssistantModel).where(ChatAssistantModel.is_default == True)  # noqa: E712
            )
            for existing in result.scalars().all():
                existing.is_default = False
        for key, value in data.items():
            setattr(ast, key, value)
        await self._db.flush()
        return self._to_ast_dto(ast)

    async def delete_assistant(self, assistant_id: str) -> bool:
        ast = await self.get_assistant(assistant_id)
        if not ast:
            raise NotFoundError("助手不存在")
        if ast.is_builtin:
            ast.is_active = False
            await self._db.flush()
            return True
        await self._db.delete(ast)
        await self._db.flush()
        return True

    async def toggle_assistant(self, assistant_id: str) -> ChatAssistantDTO:
        ast = await self.get_assistant(assistant_id)
        if not ast:
            raise NotFoundError("助手不存在")
        ast.is_active = not ast.is_active
        await self._db.flush()
        return self._to_ast_dto(ast)

    async def set_default_assistant(self, assistant_id: str) -> None:
        ast = await self.get_assistant(assistant_id)
        if not ast:
            raise NotFoundError("助手不存在")
        result = await self._db.execute(
            select(ChatAssistantModel).where(ChatAssistantModel.is_default == True)  # noqa: E712
        )
        for existing in result.scalars().all():
            existing.is_default = False
        ast.is_default = True
        await self._db.flush()

    # --- DTO 转换 ---

    @staticmethod
    def _to_session_dto(s: ChatSessionModel) -> ChatSessionDTO:
        return ChatSessionDTO(
            session_id=s.session_id,
            title=s.title,
            title_locked=s.title_locked,
            assistant_id=s.assistant_id,
            agent_id=s.agent_id,
            model_id=s.model_id,
            message_count=s.message_count,
            status=s.status,
            mode=s.mode or "chat",
            created_at=s.created_at,
            updated_at=s.updated_at,
            last_message_at=s.last_message_at,
            mcp_mode=(s.sandbox_meta or {}).get("mcp_mode", "auto"),
            extra_mcp_servers=[str(value) for value in (s.sandbox_meta or {}).get("extra_mcp_servers", [])],
            multi_agent=bool((s.sandbox_meta or {}).get("multi_agent", False)),
        )

    @staticmethod
    def _to_msg_dto(m: ChatMessageModel) -> ChatMessageDTO:
        # Token usage belongs to the model response only; never expose it on user rows.
        usage = (
            (m.metadata_json or {}).get("usage") or {}
            if m.role == "assistant"
            else {}
        )
        input_tokens = (
            usage.get("prompt_tokens", 0)
            or usage.get("input_tokens", 0)
            or usage.get("input", 0)
        )
        output_tokens = (
            usage.get("completion_tokens", 0)
            or usage.get("output_tokens", 0)
            or usage.get("output", 0)
        )
        total_tokens = (
            usage.get("total_tokens", 0)
            or usage.get("total", 0)
            or input_tokens + output_tokens
        )
        return ChatMessageDTO(
            message_id=m.message_id,
            role=m.role,
            content=m.content,
            content_type=m.content_type,
            status=m.status,
            metadata_json=m.metadata_json or {},
            created_at=m.created_at,
            tokens={
                "input": input_tokens,
                "output": output_tokens,
                "total": total_tokens,
            },
        )

    @staticmethod
    def _to_ast_dto(a: ChatAssistantModel) -> ChatAssistantDTO:
        return ChatAssistantDTO(
            assistant_id=a.assistant_id,
            name=a.name,
            description=a.description,
            system_prompt=a.system_prompt,
            default_model_id=a.default_model_id,
            default_temperature=a.default_temperature,
            default_max_tokens=a.default_max_tokens,
            icon=a.icon,
            color=a.color,
            category=a.category,
            is_builtin=a.is_builtin,
            is_active=a.is_active,
            is_default=a.is_default,
        )

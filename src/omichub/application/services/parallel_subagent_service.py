"""对话内并行子 Agent fan-out 运行时。

设计文档：ARCHITECTURE_DESIN/multi-agent.md §4。

父 Agent 一次工具调用提交相互独立的子任务列表，本服务在请求内并行运行
受限子 ReAct 循环（可调用 builtin 工具），失败隔离后结构化汇总回父上下文。

关键正确性约束（对应设计文档 §4.4 C1–C7）：
- C1 每个子循环的工具执行独占 AsyncSession（并发共享父 session 必崩）；
- C2 子 Agent 工具表剥离 parallel_subagents 自身（防递归，深度恒为 1）；
- C3 剥离 handoff / ask_user 等控制工具（子任务无法切换会话、无人应答澄清）；
- C4 剥离 requires_confirm 工具（子任务没有确认通道）；
- C5 单工具回灌截断 + 子循环总轮数上限；
- C6 子任务产物写入各自隔离子目录（经 ToolInvocationContext.extra 透出）；
- C7 fan-out 对父循环只计一次 tool_call。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from omichub.application.schemas.tool_invocation import ToolInvocationContext
from omichub.application.services.agent_service import AgentService
from omichub.core.config import get_settings
from omichub.infrastructure.ai_provider.openai_compatible import provider_manager
from omichub.infrastructure.database.session import get_session_factory
from omichub.tools.schema_loader import schema_loader

logger = logging.getLogger(__name__)

PARALLEL_SUBAGENTS_TOOL_NAME = "parallel_subagents"

# 子循环内必须剥离的控制类工具（C2/C3）
_CONTROL_TOOL_NAMES = frozenset(
    {
        PARALLEL_SUBAGENTS_TOOL_NAME,  # C2 防递归 fan-out
        "transfer_to_agent",  # C3 子任务不能切换父会话
        "create_agentteams_case",  # 子任务不得创建跨会话交付 Case
        "ask_user",  # C3 子任务无用户应答，会死锁
        "omichub_save_memory",  # 子任务是临时工，不写长期记忆
        "omichub_update_memory",  # 26.8.4：子任务同样不得改写主用户记忆
        "omichub_forget_memory",  # 26.8.4：子任务不得删除主用户记忆
        # 保留 omichub_search_memory：只读检索对子任务有用且无副作用
    }
)

# 子任务最终结论截断长度（父循环回灌有 12000 字符护栏，按 4 子任务预算）
_ANSWER_CAP_CHARS = 1200
# 单条工具结果回灌子上下文的字符上限（C5）
_TOOL_RESULT_CAP_CHARS = 8000
_TASK_INSTRUCTION_MAX_CHARS = 2000
_CONTEXT_SUMMARY_MAX_CHARS = 4000

SUBAGENT_SYSTEM_SUFFIX = (
    "\n\n## 子任务模式\n"
    "你正在执行由上级 Agent 并行分派的子任务。约束：\n"
    "1. 只专注完成本子任务，不要向用户提问，不要做会话交接；\n"
    "2. 优先只读操作，谨慎执行写文件或提交计算任务；\n"
    f"3. 完成后直接输出自包含、可核验的精简结论（控制在 {_ANSWER_CAP_CHARS} 字以内），"
    "包含关键证据与产物路径（如有）。"
)


class ParallelSubAgentService:
    """将独立子任务列表 fan-out 给已注册 Agent 并行执行，失败隔离并汇总。"""

    async def run(
        self,
        *,
        user_id: str,
        parent_agent_id: str,
        parent_session_id: str,
        context_summary: str,
        tasks: list[dict[str, Any]],
        db: AsyncSession,
    ) -> dict[str, Any]:
        """执行 fan-out，返回统一信封 {success, llm_payload, ui_payload}。"""
        settings = get_settings()
        # env 开关与管理端平台设置（DB）任一为真即启用；管理端为运行时主开关
        from omichub.application.services.site_settings_service import SiteSettingsService

        db_enabled = await SiteSettingsService(db).is_subagent_fanout_enabled()
        if not (settings.subagent_fanout_enabled or db_enabled):
            return self._error(
                "子 Agent 并行分派未启用（管理端「设置 → 平台设置」开关"
                "或环境变量 SUBAGENT_FANOUT_ENABLED=true 任一启用即可）"
            )

        normalized = self._validate_tasks(tasks, settings.subagent_max_parallel)
        if isinstance(normalized, dict):  # 校验失败信封
            return normalized
        context_summary = (context_summary or "").strip()[:_CONTEXT_SUMMARY_MAX_CHARS]

        # 顺序预组装：单线程复用父 session 读库，满足 C1（并发阶段不再碰父 session）
        agent_service = AgentService(db)
        prepared: list[tuple[dict[str, Any], Any, list[dict[str, Any]]]] = []
        for index, item in enumerate(normalized, start=1):
            ctx = await agent_service.assemble_context(item["agent_id"])
            if ctx is None or ctx.model_config is None:
                return self._error(
                    f"子任务 #{index} 的目标 Agent {item['agent_id']} 不存在或未绑定可用模型"
                )
            if not bool((ctx.features or {}).get("subagents_spawnable")):
                return self._error(
                    f"Agent {item['agent_id']} 未标记为可派生子 Agent"
                    "（需在 Agent YAML 的 features 增加 subagents_spawnable: true）"
                )
            prepared.append((item, ctx, self._filter_child_tools(ctx.tools)))

        run_id = uuid4().hex[:12]
        workdir_root = Path(get_settings().storage_path) / "subagents" / run_id
        semaphore = asyncio.Semaphore(max(1, settings.subagent_max_concurrent))
        started = time.monotonic()
        logger.info(
            "subagent fan-out 启动: run_id=%s parent_agent=%s parent_session=%s tasks=%d",
            run_id,
            parent_agent_id,
            parent_session_id,
            len(prepared),
        )
        results = await asyncio.gather(
            *(
                self._run_child(
                    index=index,
                    agent_id=item["agent_id"],
                    task=item["task"],
                    context_summary=context_summary,
                    ctx=ctx,
                    child_tools=child_tools,
                    user_id=user_id,
                    parent_session_id=parent_session_id,
                    run_id=run_id,
                    workdir=workdir_root / str(index),
                    timeout_seconds=settings.subagent_child_timeout_seconds,
                    max_rounds=settings.subagent_max_rounds_per_child,
                    semaphore=semaphore,
                )
                for index, (item, ctx, child_tools) in enumerate(prepared, start=1)
            )
        )
        elapsed = round(time.monotonic() - started, 1)
        ok_count = sum(1 for item in results if item["status"] == "ok")
        total = len(results)
        summary = (
            f"{ok_count}/{total} 个子任务成功，总墙钟 {elapsed}s"
            if ok_count == total
            else f"{ok_count}/{total} 个子任务成功，总墙钟 {elapsed}s（含失败/超时项，见明细）"
        )
        return {
            "success": ok_count > 0,
            "llm_payload": {
                "summary": summary,
                "results": [self._llm_view(item) for item in results],
            },
            "ui_payload": {
                "fanout_run_id": run_id,
                "elapsed_s": elapsed,
                "progress": [
                    {
                        "index": item["index"],
                        "agent_id": item["agent_id"],
                        "status": item["status"],
                        "elapsed_s": item["elapsed_s"],
                    }
                    for item in results
                ],
            },
        }

    # --- 校验 ---

    @staticmethod
    def _validate_tasks(
        tasks: Any, max_parallel: int
    ) -> list[dict[str, str]] | dict[str, Any]:
        if not isinstance(tasks, list) or not tasks:
            return ParallelSubAgentService._error("tasks 必须为非空列表")
        if len(tasks) > max_parallel:
            return ParallelSubAgentService._error(
                f"单次 fan-out 最多 {max_parallel} 个子任务（SUBAGENT_MAX_PARALLEL）"
            )
        normalized: list[dict[str, str]] = []
        for index, item in enumerate(tasks, start=1):
            if not isinstance(item, dict):
                return ParallelSubAgentService._error(f"子任务 #{index} 必须是对象")
            agent_id = str(item.get("agent_id") or "").strip()
            task = str(item.get("task") or "").strip()
            if not agent_id or not task:
                return ParallelSubAgentService._error(
                    f"子任务 #{index} 缺少 agent_id 或 task"
                )
            if len(task) > _TASK_INSTRUCTION_MAX_CHARS:
                return ParallelSubAgentService._error(
                    f"子任务 #{index} 的指令超过 {_TASK_INSTRUCTION_MAX_CHARS} 字"
                )
            normalized.append({"agent_id": agent_id, "task": task})
        return normalized

    # --- 工具过滤（C2/C3/C4）---

    @staticmethod
    def _filter_child_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        """子循环只保留 ToolBridge 可执行的 backend_sync builtin 工具。

        MCP 工具不经 ToolBridge 分发（chat 循环自持 server 分支），v1 不带入子循环；
        analysis_flow 长任务与需确认工具同样排除（C4）。
        """
        kept: list[dict[str, Any]] = []
        for tool in tools or []:
            name = str((tool.get("function") or {}).get("name") or "")
            if not name or name in _CONTROL_TOOL_NAMES:
                continue
            schema = schema_loader.get_tool(name)
            if schema is None:
                continue  # MCP / skill 等桥外工具
            if schema.invocation_mode != "backend_sync":
                continue  # analysis_flow 长耗时管道应走 MAS
            if schema.requires_confirm:
                continue  # C4 子循环无确认通道
            kept.append(tool)
        return kept

    # --- 子循环执行 ---

    async def _run_child(
        self,
        *,
        index: int,
        agent_id: str,
        task: str,
        context_summary: str,
        ctx: Any,
        child_tools: list[dict[str, Any]],
        user_id: str,
        parent_session_id: str,
        run_id: str,
        workdir: Path,
        timeout_seconds: int,
        max_rounds: int,
        semaphore: asyncio.Semaphore,
    ) -> dict[str, Any]:
        started = time.monotonic()
        base = {
            "index": index,
            "agent_id": agent_id,
            "agent_name": str(getattr(getattr(ctx, "agent", None), "name", agent_id)),
        }
        try:
            workdir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:  # 存储不可写不致命：路径仍透出给工具自选
            logger.warning("子任务工作目录创建失败 %s: %s", workdir, exc)
        async with semaphore:
            try:
                async with asyncio.timeout(float(max(1, timeout_seconds))):
                    outcome = await self._child_loop(
                        agent_id=agent_id,
                        task=task,
                        context_summary=context_summary,
                        ctx=ctx,
                        child_tools=child_tools,
                        user_id=user_id,
                        parent_session_id=parent_session_id,
                        run_id=run_id,
                        index=index,
                        workdir=workdir,
                        max_rounds=max_rounds,
                    )
            except TimeoutError:
                outcome = {"status": "timeout", "answer": None, "error": "子任务超时"}
            except Exception as exc:  # noqa: BLE001 — 失败隔离，不影响兄弟子任务
                logger.warning("子任务 #%d (%s) 执行异常: %s", index, agent_id, exc)
                outcome = {"status": "failed", "answer": None, "error": str(exc)[:500]}
        return {
            **base,
            "status": outcome["status"],
            "answer": outcome.get("answer"),
            "error": outcome.get("error"),
            "workdir": str(workdir),
            "elapsed_s": round(time.monotonic() - started, 1),
        }

    async def _child_loop(
        self,
        *,
        agent_id: str,
        task: str,
        context_summary: str,
        ctx: Any,
        child_tools: list[dict[str, Any]],
        user_id: str,
        parent_session_id: str,
        run_id: str,
        index: int,
        workdir: Path,
        max_rounds: int,
    ) -> dict[str, Any]:
        """受限 ReAct 循环：chat_service legacy 工具循环的最小克隆。"""
        instruction = f"{context_summary}\n\n{task}".strip() if context_summary else task
        system_prompt = f"{ctx.system_prompt or ''}{SUBAGENT_SYSTEM_SUFFIX}"
        messages: list[dict[str, Any]] = [{"role": "user", "content": instruction}]
        child_session_id = f"{parent_session_id}:sub:{run_id}:{index}"
        last_text = ""
        for _round in range(max(1, max_rounds)):
            text = ""
            tool_calls: list[dict[str, Any]] = []
            async for chunk in provider_manager.chat_stream(
                config=ctx.model_config,
                messages=messages,
                system_prompt=system_prompt,
                temperature=0.3,
                max_tokens=min(int(getattr(ctx, "max_tokens", 2048) or 2048), 2048),
                tools=child_tools or None,
            ):
                if chunk.type == "text":
                    text += chunk.content
                elif chunk.type == "tool_calls":
                    tool_calls = list(chunk.metadata.get("tool_calls", []))
                elif chunk.type == "error":
                    return {
                        "status": "failed",
                        "answer": None,
                        "error": str(chunk.content or "模型调用失败")[:500],
                    }
            last_text = text.strip()
            if not tool_calls:
                return {"status": "ok", "answer": last_text[:_ANSWER_CAP_CHARS], "error": None}

            messages.append(
                {"role": "assistant", "content": text or None, "tool_calls": tool_calls}
            )
            for tc in tool_calls:
                fn = tc.get("function", {}) or {}
                tool_name = str(fn.get("name") or "")
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                tool_envelope = await self._execute_child_tool(
                    user_id=user_id,
                    agent_id=agent_id,
                    child_session_id=child_session_id,
                    tool_name=tool_name,
                    args=args if isinstance(args, dict) else {},
                    workdir=workdir,
                    run_id=run_id,
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": str(tc.get("id") or ""),
                        "content": json.dumps(tool_envelope, ensure_ascii=False, default=str)[
                            :_TOOL_RESULT_CAP_CHARS
                        ],
                    }
                )
        # 预算耗尽：把最后一段文本作为部分结论返回
        return {
            "status": "budget_exhausted",
            "answer": last_text[:_ANSWER_CAP_CHARS] or None,
            "error": f"子循环超过 {max_rounds} 轮工具上限，返回阶段性结论",
        }

    @staticmethod
    async def _execute_child_tool(
        *,
        user_id: str,
        agent_id: str,
        child_session_id: str,
        tool_name: str,
        args: dict[str, Any],
        workdir: Path,
        run_id: str,
    ) -> dict[str, Any]:
        """C1：每次工具执行独占一个 AsyncSession，用完即关。"""
        from omichub.application.services.tool_bridge_service import get_tool_bridge_service

        async with get_session_factory()() as session:
            try:
                result = await get_tool_bridge_service().execute(
                    user_id=user_id,
                    tool_name=tool_name,
                    arguments=args,
                    context=ToolInvocationContext(
                        user_id=user_id,
                        agent_id=agent_id,
                        session_id=child_session_id,
                        db=session,
                        extra={
                            "subagent_workdir": str(workdir),  # C6 隔离工作目录
                            "fanout_run_id": run_id,
                            "subagent_depth": 1,
                        },
                    ),
                )
                await session.commit()
                return result
            except Exception as exc:  # noqa: BLE001 — 工具失败回灌模型自行决策
                await session.rollback()
                return {"success": False, "error": f"工具 {tool_name} 执行失败：{exc}"}

    # --- 视图与信封 ---

    @staticmethod
    def _llm_view(item: dict[str, Any]) -> dict[str, Any]:
        view: dict[str, Any] = {
            "index": item["index"],
            "agent_id": item["agent_id"],
            "status": item["status"],
            "answer": item.get("answer"),
            "elapsed_s": item["elapsed_s"],
        }
        if item.get("error"):
            view["error"] = item["error"]
        if item.get("workdir"):
            view["workdir"] = item["workdir"]
        return view

    @staticmethod
    def _error(message: str) -> dict[str, Any]:
        return {
            "success": False,
            "llm_payload": {"success": False, "error": message},
            "ui_payload": {"error": message},
        }

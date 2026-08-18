"""AgentTeams 聊天 Case 的执行意图判定（保守策略，宁漏勿错）。

设计背景：历史上曾因关键词误触发，把纯咨询问题（如“介绍一下 Manager 能做什么”）
送进 planning 流水线。因此本模块只在“明确执行动词 + 明确作用对象”同时成立、
且未命中咨询/寒暄否决词时才判 execute；任何歧义都判 chat/clarify，宁可漏触发也
不误启动真实的规划与沙盒执行。

三态语义（优化项 O6，阶段 2）：
- execute：执行动词 + 明确作用对象，且未命中否决词——可直接启动 planning；
- clarify：执行动词成立但无作用对象——由调用方发起选项式追问补全对象；
- chat：命中否决词或无执行动词——纯对话。

``detect_execution_intent`` 保留旧布尔语义（仅 execute 为 True），作为兼容适配层；
新调用方应使用 ``classify_execution_intent`` 获取三态。
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

# 触发 planning 时附在 objective 尾部的通用计划契约：约束规划者输出可被
# execute_general_plan 直接消费的 proposed_submission 结构。
GENERAL_PLAN_CONTRACT = (
    "请输出 proposed_submission，结构为 "
    '{"name": "...", "parameters": {"work_items": ['
    '{"work_item_id": "exec-01", "target": "agent-viz", "objective": "...", '
    '"skill_name": "...", "execution_mode": "workspace_execution", "depends_on": []}]}, '
    '"quality_gate_required": false}；'
    "target 只能是声明了 workspace_execution 的 worker（可视化/绘图用 agent-viz，"
    "通用脚本用 agent-code）；"
    "工作项 objective 必须写清输入文件引用与期望产物文件名。"
)

# 一票否决：咨询/寒暄模式，命中即 chat（中英文，词表保持窄）。
_VETO_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern)
    for pattern in (
        "能做什么",
        "你会什么",
        "介绍一下",
        "是什么",
        "怎么用",
        "如何使用",
        "如何理解",
        "为什么",
        "你好",
        "谢谢",
        r"\bwhat can you\b",
        r"\bwho are you\b",
        r"\bhow to use\b",
        r"^\s*(hi|hello|hey)\b",
        r"\bthank(s| you)\b",
    )
)

# 必要条件 1：明确的执行动词（中文子串匹配；英文整词匹配避免误伤）。
_EXECUTION_VERB_PATTERN = re.compile(
    "可视化|绘图|画|绘制|渲染|出图|运行|执行|跑|分析|生成|统计|比对|建树|转换|计算"
    "|处理|整理|汇总|检索|搜索|制作|导出"
    r"|\bvisuali[sz]e\b|\bplot\b|\brender\b|\brun\b|\bgenerate\b|\bsearch\b|\bexport\b",
    re.IGNORECASE,
)

# 必要条件 2（文本侧）：出现带常见扩展名的文件名片段。
_FILE_NAME_PATTERN = re.compile(
    r"[\w.\-]+\.(?:nwk|treefile|tree|csv|tsv|xlsx|fastq|fq|bam|png|jpe?g|svg|txt|json|bed|gtf|gff)\b",
    re.IGNORECASE,
)


class ExecutionIntent(StrEnum):
    """聊天 Case 执行意图三态（O6）。"""

    EXECUTE = "execute"
    CLARIFY = "clarify"
    CHAT = "chat"


def has_explicit_object(content: str, context_refs: list[dict[str, Any]]) -> bool:
    """是否存在明确作用对象：context_refs 非空，或文本含带扩展名的文件名片段。"""
    if context_refs:
        return True
    return bool(_FILE_NAME_PATTERN.search((content or "").strip()))


def classify_execution_intent(
    content: str, context_refs: list[dict[str, Any]]
) -> ExecutionIntent:
    """三态判定用户发言的执行意图。

    判定规则：
    1. 命中一票否决词（咨询/寒暄）→ chat；
    2. 无明确执行动词 → chat；
    3. 执行动词 + 明确作用对象（context_refs 或文件名）→ execute；
    4. 执行动词但无作用对象 → clarify（由调用方追问补全对象后再判）。
    """
    text = (content or "").strip()
    if not text:
        return ExecutionIntent.CHAT
    if any(pattern.search(text) for pattern in _VETO_PATTERNS):
        return ExecutionIntent.CHAT
    if not _EXECUTION_VERB_PATTERN.search(text):
        return ExecutionIntent.CHAT
    if has_explicit_object(text, context_refs):
        return ExecutionIntent.EXECUTE
    return ExecutionIntent.CLARIFY


def detect_execution_intent(content: str, context_refs: list[dict[str, Any]]) -> bool:
    """布尔兼容适配层：仅 execute 态返回 True，判定语义与旧二元版本完全一致。"""
    return classify_execution_intent(content, context_refs) is ExecutionIntent.EXECUTE

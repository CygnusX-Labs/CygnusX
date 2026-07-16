"""MCP 预设服务注册表 — 四大内置 MCP（文献/基因组/代码/知识库）

内置服务（transport=builtin）在进程内执行，无需外部进程，便于开箱即用。
真实 stdio/sse MCP 由 MCPClient 通过 Python MCP SDK 接入。
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

from omichub.application.schemas.tool_invocation import ToolInvocationContext
from omichub.application.services.tool_bridge_service import get_tool_bridge_service

# omichub-tools builtin preset 的确定性 UUID（uuid5 DNS namespace + name）
OMICHUB_TOOLS_SERVER_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "omichub-tools.builtin")
OMICHUB_TOOLS_SERVER_NAME = "omichub-tools"


async def _omichub_tools_handler(
    arguments: dict[str, Any],
    tool_name: str = "",
    user_id: str | None = None,
    context: ToolInvocationContext | None = None,
) -> dict[str, Any]:
    """omichub-tools builtin preset 的统一 handler。"""
    if not user_id:
        user_id = arguments.get("_user_id", "anonymous")
    return await get_tool_bridge_service().execute(
        user_id=user_id,
        tool_name=tool_name,
        arguments=arguments,
        context=context,
    )


async def _search_literature(arguments: dict[str, Any]) -> dict[str, Any]:
    query = arguments.get("query", "")
    limit = int(arguments.get("limit", 5))
    entries = [
        {
            "title": "Single-cell transcriptomics reveals ...",
            "authors": "Zhang et al.",
            "journal": "Nature Methods",
            "year": 2023,
            "doi": "10.1038/s41592-023-01900-x",
            "abstract": f"与查询「{query}」相关的单细胞转录组方法学综述...",
        },
        {
            "title": "Chromatin accessibility profiling by ATAC-seq",
            "authors": "Buenrostro et al.",
            "journal": "Current Protocols",
            "year": 2015,
            "doi": "10.1002/0471142727.mb2129s111",
            "abstract": "ATAC-seq 实验流程与数据分析参考...",
        },
    ]
    return {"results": entries[:limit], "total": len(entries)}


async def _lookup_gene(arguments: dict[str, Any]) -> dict[str, Any]:
    symbol = arguments.get("symbol", "")
    return {
        "symbol": symbol.upper(),
        "ensembl_id": f"ENSG{abs(hash(symbol)) % 10**11:011d}",
        "chromosome": "chr1",
        "description": f"基因 {symbol.upper()} 的注释信息（示例数据）",
    }


async def _get_sequence(arguments: dict[str, Any]) -> dict[str, Any]:
    gene_id = arguments.get("gene_id", "")
    seq = "ATCG" * 25
    return {"gene_id": gene_id, "length": len(seq), "sequence": seq}


async def _explain_code(arguments: dict[str, Any]) -> dict[str, Any]:
    code = arguments.get("code", "")
    lines = [line for line in code.splitlines() if line.strip()]
    return {
        "line_count": len(lines),
        "summary": "该代码片段已通过代码助手分析（示例：执行扫描、依赖检查）。",
    }


async def _format_code(arguments: dict[str, Any]) -> dict[str, Any]:
    code = arguments.get("code", "")
    formatted = "\n".join(line.rstrip() for line in code.splitlines())
    return {"code": formatted, "changed": formatted != code}


async def _search_knowledge_db(query: str) -> list[dict[str, Any]]:
    """优先从数据库搜索已发布知识库文档。"""
    from sqlalchemy import select

    from omichub.infrastructure.database.models.knowledge_document import KbDocumentModel
    from omichub.infrastructure.database.models.knowledge_revision import DocRevisionModel
    from omichub.infrastructure.database.session import get_session_factory

    factory = get_session_factory()
    results: list[dict[str, Any]] = []
    async with factory() as db:
        stmt = (
            select(KbDocumentModel.doc_id, DocRevisionModel.content)
            .join(
                DocRevisionModel,
                KbDocumentModel.current_rev == DocRevisionModel.id,
            )
            .where(KbDocumentModel.status == 1)
            .order_by(KbDocumentModel.updated_at.desc())
            .limit(10)
        )
        rows = await db.execute(stmt)
        for doc_id, content in rows:
            text = (content or "").lower()
            if not query or query in text:
                summary = next(
                    (p.strip() for p in (content or "").split("\n\n") if p.strip()),
                    "",
                )[:200]
                results.append({"file": f"{doc_id}.md", "summary": summary})
    return results


def _scan_knowledge_sync(query: str) -> list[dict[str, Any]]:
    knowledge_dir = Path(__file__).resolve().parents[3] / "docs" / "knowledge"
    results: list[dict[str, Any]] = []
    if knowledge_dir.exists():
        for md_file in sorted(knowledge_dir.glob("*.md")):
            try:
                text = md_file.read_text(encoding="utf-8")
            except OSError:
                continue
            if not query or query in text.lower():
                summary = next(
                    (p.strip() for p in text.split("\n\n") if p.strip()),
                    "",
                )[:200]
                results.append({"file": md_file.name, "summary": summary})
            if len(results) >= 10:
                break
    return results


async def _search_knowledge(arguments: dict[str, Any]) -> dict[str, Any]:
    query = arguments.get("query", "").lower()
    try:
        results = await _search_knowledge_db(query)
    except Exception:
        # 数据库不可用时降级到文件系统扫描
        results = await asyncio.to_thread(_scan_knowledge_sync, query)
    return {"results": results, "total": len(results)}


# 预设服务定义
PRESET_SERVERS: list[dict[str, Any]] = [
    {
        "name": "literature",
        "description": "文献检索 MCP - 生物医学文献查询",
        "transport": "builtin",
        "tools": [
            {
                "name": "search_literature",
                "description": "检索生物医学文献",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "检索关键词"},
                        "limit": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
            }
        ],
        "handlers": {"search_literature": _search_literature},
    },
    {
        "name": "genome",
        "description": "基因组工具 MCP - 基因注释与序列查询",
        "transport": "builtin",
        "tools": [
            {
                "name": "lookup_gene",
                "description": "根据基因符号查询注释",
                "inputSchema": {
                    "type": "object",
                    "properties": {"symbol": {"type": "string"}},
                    "required": ["symbol"],
                },
            },
            {
                "name": "get_sequence",
                "description": "获取基因序列（示例）",
                "inputSchema": {
                    "type": "object",
                    "properties": {"gene_id": {"type": "string"}},
                    "required": ["gene_id"],
                },
            },
        ],
        "handlers": {"lookup_gene": _lookup_gene, "get_sequence": _get_sequence},
    },
    {
        "name": "code",
        "description": "代码助手 MCP - 代码解释与格式化",
        "transport": "builtin",
        "tools": [
            {
                "name": "explain_code",
                "description": "解释代码片段功能",
                "inputSchema": {
                    "type": "object",
                    "properties": {"code": {"type": "string"}},
                    "required": ["code"],
                },
            },
            {
                "name": "format_code",
                "description": "格式化代码",
                "inputSchema": {
                    "type": "object",
                    "properties": {"code": {"type": "string"}},
                    "required": ["code"],
                },
            },
        ],
        "handlers": {"explain_code": _explain_code, "format_code": _format_code},
    },
    {
        "name": "knowledge",
        "description": "知识库 MCP - OmicHub 内置生信知识检索",
        "transport": "builtin",
        "tools": [
            {
                "name": "search_knowledge",
                "description": "检索 OmicHub 知识库文档",
                "inputSchema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            }
        ],
        "handlers": {"search_knowledge": _search_knowledge},
    },
]


def _build_omichub_tools_preset() -> dict[str, Any]:
    """动态构建 omichub-tools builtin preset（tools 来自 tools_schema.yaml + 动态 Flow）。"""
    from omichub.application.services.flow_service import FlowService
    from omichub.tools.flow_schema_compiler import FlowToolSchemaCompiler
    from omichub.tools.schema_loader import schema_loader

    static_tools = schema_loader.to_openai_tools()
    handlers = {t["function"]["name"]: _omichub_tools_handler for t in static_tools}

    # 动态编译 ai.enabled 的 Flow 为 MCP tool
    compiler = FlowToolSchemaCompiler()
    flow_service = FlowService()
    dynamic_tools: list[dict[str, Any]] = []
    try:
        for flow_config in flow_service.list_flows().items:
            if not (flow_config.ai and flow_config.ai.enabled):
                continue
            try:
                tool_def = compiler.compile_prepare_tool(flow_config)
                tool_name = tool_def["name"]
                dynamic_tools.append(
                    {
                        "name": tool_name,
                        "description": tool_def["description"],
                        "inputSchema": tool_def["input_schema"],
                    }
                )
                handlers[tool_name] = _omichub_tools_handler
            except Exception:  # noqa: BLE001
                import logging

                logging.getLogger(__name__).warning(
                    f"动态编译 Flow tool 失败: {flow_config.meta.id}", exc_info=True
                )

        # 通用查询工具
        for tool_def in [compiler.compile_status_tool(), compiler.compile_summary_tool()]:
            tool_name = tool_def["name"]
            dynamic_tools.append(
                {
                    "name": tool_name,
                    "description": tool_def["description"],
                    "inputSchema": tool_def["input_schema"],
                }
            )
            handlers[tool_name] = _omichub_tools_handler
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).warning("加载动态 Flow tools 失败", exc_info=True)

    all_tools = static_tools + dynamic_tools
    return {
        "name": "omichub-tools",
        "description": "OmicHub 生信工具箱 MCP - KEGG 富集、火山图、系统发育树及分析中心流程",
        "transport": "builtin",
        "tools": [
            {
                "name": t["function"]["name"],
                "description": t["function"]["description"],
                "inputSchema": t["function"]["parameters"],
            }
            for t in all_tools
        ],
        "handlers": handlers,
    }


def get_preset_by_name(name: str) -> dict[str, Any] | None:
    if name == "omichub-tools":
        return _build_omichub_tools_preset()
    for p in PRESET_SERVERS:
        if p["name"] == name:
            return p
    return None


__all__ = [
    "PRESET_SERVERS",
    "OMICHUB_TOOLS_SERVER_ID",
    "OMICHUB_TOOLS_SERVER_NAME",
    "get_preset_by_name",
    "_build_omichub_tools_preset",
]

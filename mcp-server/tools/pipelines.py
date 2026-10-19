"""完整分析流水线 MCP 工具。"""

from __future__ import annotations

from typing import Any

from client.api_client import CygnusXAPIClient, CygnusXAPIError
from fastmcp import FastMCP

# 旧四件套工具名（LEGACY_PIPELINE_TOOLS=false 时注册为同名迁移 stub）
LEGACY_TOOL_NAMES: tuple[str, ...] = (
    "rna_seq_prepare",
    "rna_seq_submit",
    "rna_seq_status",
    "rna_seq_results",
    "atac_seq_prepare",
    "atac_seq_submit",
    "atac_seq_status",
    "atac_seq_results",
    "list_available_pipelines",
    "check_workspace_data",
)

_MIGRATION_MESSAGE = (
    "[已迁移] 该工具已由统一固定工具替代：流程目录请用 cygnusx_list_flows / "
    "cygnusx_get_flow_detail；预检与提交请用 cygnusx_prepare / cygnusx_submit"
    "（参数快照冻结 + 用户网页确认 + 幂等提交）；任务状态/结果/日志请用 "
    "cygnusx_get_task / cygnusx_get_task_progress / cygnusx_get_task_logs。"
    "如需临时恢复旧工具，由平台管理员设置 legacy_pipeline_tools=true。"
)


def _register_migration_stubs(mcp: FastMCP) -> None:
    """旧四件套同名迁移 stub：存量客户端收到明确"已迁移"提示而非 tool-not-found。"""

    async def _stub(
        raw_data_path: str = "",
        species: str = "",
        genome_version: str = "",
        sample_sheet: list[dict] | None = None,
        comparisons: list[dict] | None = None,
        library_type: str = "",
        project_name: str = "",
        task_name: str = "",
        extra_parameters: dict | None = None,
        prepared_params: dict | None = None,
        task_id: str = "",
        result_types: list[str] | None = None,
        analysis_type: str = "",
        data_path: str = "",
        user_confirmed: bool = False,
    ) -> dict[str, Any]:
        # 仅返回迁移提示；无论传入什么参数都不触发任何服务端行为。
        return {"success": False, "summary": _MIGRATION_MESSAGE, "data": None}

    for tool_name in LEGACY_TOOL_NAMES:
        mcp.tool(name=tool_name)(_stub)


def _failure(error: CygnusXAPIError) -> dict[str, Any]:
    return {
        "success": False,
        "summary": f"调用失败: {error.detail}",
        "error": error.detail,
        "error_code": error.status_code,
        "guidance": "请根据错误信息修正参数或确认当前 API Key 对工作区数据具有访问权限。",
    }


def _needs_confirmation(
    pipeline_label: str, prepared_params: dict[str, Any]
) -> dict[str, Any]:
    """写操作确认门 — 与 tools/analysis.py 的 needs_confirmation 摘要风格一致。"""
    sample_sheet = prepared_params.get("sample_sheet")
    comparisons = prepared_params.get("comparisons")
    return {
        "success": True,
        "needs_confirmation": True,
        "summary": (
            "即将提交分析任务:\n"
            f"  流程: {pipeline_label}\n"
            f"  项目: {prepared_params.get('project_name') or '(未命名)'}\n"
            f"  样本数: {len(sample_sheet) if sample_sheet else 0}\n"
            f"  比较组: {len(comparisons) if comparisons else 0}\n"
            "请在平台网页批准预检确认记录后重试提交。"
        ),
        "data": {"prepared_params": prepared_params},
    }


def register(mcp: FastMCP, api: CygnusXAPIClient) -> None:
    from core.config import settings

    # 阶段 3（MCP 工具固定化）：legacy_pipeline_tools=false 时旧四件套变为
    # 同名迁移 stub（明确"已迁移"提示），固定工具接管提交主链。
    if not settings.legacy_pipeline_tools:
        _register_migration_stubs(mcp)
        return

    async def prepare(pipeline_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return await api.prepare_pipeline(pipeline_type, payload)
        except CygnusXAPIError as error:
            return _failure(error)

    async def submit(pipeline_type: str, prepared_params: dict[str, Any]) -> dict[str, Any]:
        try:
            return await api.submit_pipeline(pipeline_type, prepared_params)
        except CygnusXAPIError as error:
            return _failure(error)

    async def status(pipeline_type: str, task_id: str) -> dict[str, Any]:
        try:
            return await api.get_pipeline_status(pipeline_type, task_id)
        except CygnusXAPIError as error:
            return _failure(error)

    async def results(
        pipeline_type: str, task_id: str, result_types: list[str] | None
    ) -> dict[str, Any]:
        try:
            return await api.get_pipeline_results(
                pipeline_type, task_id, result_types or ["summary", "artifacts"]
            )
        except CygnusXAPIError as error:
            return _failure(error)

    @mcp.tool()
    async def rna_seq_prepare(
        raw_data_path: str,
        species: str,
        genome_version: str,
        sample_sheet: list[dict[str, Any]],
        comparisons: list[dict[str, Any]],
        library_type: str,
        project_name: str,
        extra_parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """[DEPRECATED] 将由统一固定工具替代，新集成请勿使用。校验 RNA-seq 参数和工作区数据，返回可提交的 prepared_params。"""
        payload = locals()
        payload["extra_parameters"] = extra_parameters or {}
        return await prepare("rna_seq", payload)

    @mcp.tool()
    async def rna_seq_submit(
        prepared_params: dict[str, Any], user_confirmed: bool = False
    ) -> dict[str, Any]:
        """[DEPRECATED] 将由统一固定工具替代，新集成请勿使用。提交经过预检的 RNA-seq 任务；必须先完成平台网页确认。"""

        if user_confirmed:
            return {"success": False, "summary": "拒绝 user_confirmed 布尔自证；请在平台网页批准预检确认记录。"}
        if not prepared_params.get("confirmation_id"):
            return _needs_confirmation("rna_seq", prepared_params)
        return await submit("rna_seq", prepared_params)

    @mcp.tool()
    async def rna_seq_status(task_id: str) -> dict[str, Any]:
        """[DEPRECATED] 将由统一固定工具替代，新集成请勿使用。查询 RNA-seq 任务状态和进度。

        # :param task_id: 任务唯一标识符
        # :return: JSON 格式的任务状态

        # 示例:
            await rna_seq_status("task_123456")
            # 返回任务当前状态
        """
        return await status("rna_seq", task_id)

    @mcp.tool()
    async def rna_seq_results(
        task_id: str, result_types: list[str] | None = None
    ) -> dict[str, Any]:
        """[DEPRECATED] 将由统一固定工具替代，新集成请勿使用。获取 RNA-seq 结果摘要、差异基因统计和产物清单。"""

        return await results("rna_seq", task_id, result_types)

    @mcp.tool()
    async def atac_seq_prepare(
        raw_data_path: str,
        species: str,
        genome_version: str,
        sample_sheet: list[dict[str, Any]],
        comparisons: list[dict[str, Any]],
        library_type: str,
        project_name: str,
        extra_parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """[DEPRECATED] 将由统一固定工具替代，新集成请勿使用。校验 ATAC-seq 参数和工作区数据，返回可提交的 prepared_params。"""

        payload = locals()
        payload["extra_parameters"] = extra_parameters or {}
        return await prepare("atac_seq", payload)

    @mcp.tool()
    async def atac_seq_submit(
        prepared_params: dict[str, Any], user_confirmed: bool = False
    ) -> dict[str, Any]:
        """[DEPRECATED] 将由统一固定工具替代，新集成请勿使用。提交经过预检的 ATAC-seq 任务；必须先完成平台网页确认。"""

        if user_confirmed:
            return {"success": False, "summary": "拒绝 user_confirmed 布尔自证；请在平台网页批准预检确认记录。"}
        if not prepared_params.get("confirmation_id"):
            return _needs_confirmation("atac_seq", prepared_params)
        return await submit("atac_seq", prepared_params)

    @mcp.tool()
    async def atac_seq_status(task_id: str) -> dict[str, Any]:
        """[DEPRECATED] 按 task_id 查询 ATAC-seq 任务当前状态及平台提供的进度信息；这是旧版流程专用入口，新集成优先使用 cygnusx_get_task_progress。"""

        return await status("atac_seq", task_id)

    @mcp.tool()
    async def atac_seq_results(
        task_id: str, result_types: list[str] | None = None
    ) -> dict[str, Any]:
        """[DEPRECATED] 将由统一固定工具替代，新集成请勿使用。获取 ATAC-seq 结果摘要和产物清单。"""

        return await results("atac_seq", task_id, result_types)

    @mcp.tool()
    async def list_available_pipelines() -> dict[str, Any]:
        """列出当前平台可通过 MCP 调用的完整分析流程。"""

        try:
            pipelines = await api.list_available_pipelines()
            return {"success": True, "pipelines": pipelines}
        except CygnusXAPIError as error:
            return _failure(error)

    @mcp.tool()
    async def check_workspace_data(analysis_type: str, data_path: str) -> dict[str, Any]:
        """检查当前 API Key 所属用户工作区内的数据完整性。"""

        try:
            return await api.check_workspace_data(analysis_type, data_path)
        except CygnusXAPIError as error:
            return _failure(error)

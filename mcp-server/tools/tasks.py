"""Task management tools."""

from fastmcp import FastMCP

from client.api_client import CygnusXAPIClient, CygnusXAPIError
from core.config import settings


def register(mcp: FastMCP, api: CygnusXAPIClient) -> None:
    @mcp.tool()
    async def cygnusx_list_tasks(status: str = "") -> dict:
        try:
            data = await api.list_tasks(status=status or None)
            return {"success": True, "summary": "任务列表", "data": data}
        except CygnusXAPIError as exc:
            return {"success": False, "summary": f"获取任务列表失败: {exc.detail}"}

    @mcp.tool()
    async def cygnusx_get_task(task_id: str) -> dict:
        try:
            data = await api.get_task(task_id)
            return {"success": True, "summary": f"任务 {task_id}", "data": data}
        except CygnusXAPIError as exc:
            return {"success": False, "summary": f"获取任务失败: {exc.detail}"}

    @mcp.tool()
    async def cygnusx_get_task_progress(task_id: str) -> dict:
        try:
            data = await api.get_task(task_id)
            status = data.get("status", "unknown")
            return {
                "success": True,
                "summary": f"状态: {status} | 进度: {data.get('progress', 0):.0%}",
                "data": {
                    "status": status,
                    "progress": data.get("progress", 0),
                    "is_done": status in {"success", "failed", "cancelled"},
                },
            }
        except CygnusXAPIError as exc:
            return {"success": False, "summary": f"查询进度失败: {exc.detail}"}

    @mcp.tool()
    async def cygnusx_get_task_logs(task_id: str, lines: int = 50) -> dict:
        try:
            data = await api.get_task(task_id)
            logs = data.get("logs", [])
            recent = logs[-max(1, min(lines, settings.max_log_lines)) :]
            return {"success": True, "summary": "任务日志", "data": {"logs": recent}}
        except CygnusXAPIError as exc:
            return {"success": False, "summary": f"获取任务日志失败: {exc.detail}"}

    @mcp.tool()
    async def cygnusx_cancel_task(
        task_id: str, confirmation_id: str = "", user_confirmed: bool = False
    ) -> dict:
        if user_confirmed:
            return {"success": False, "summary": "拒绝 user_confirmed 布尔自证；请使用服务端 confirmation_id。"}
        if not confirmation_id:
            confirmation = await api.create_tool_confirmation(
                "cygnusx_cancel_task", {"task_id": task_id}
            )
            return {
                "success": True,
                "needs_confirmation": True,
                "summary": "请在平台网页批准取消确认记录后携带 confirmation_id 重试。",
                "data": {"task_id": task_id, "confirmation": confirmation},
            }
        try:
            data = await api.cancel_task(task_id, confirmation_id)
            return {"success": True, "summary": "任务已取消", "data": data}
        except CygnusXAPIError as exc:
            return {"success": False, "summary": f"取消失败: {exc.detail}"}

    @mcp.tool()
    async def cygnusx_get_task_dag(task_id: str) -> dict:
        try:
            data = await api.get_task_dag(task_id)
            return {"success": True, "summary": "任务 DAG", "data": data}
        except CygnusXAPIError as exc:
            return {"success": False, "summary": f"获取 DAG 失败: {exc.detail}"}

"""Workspace file browsing tools."""

from fastmcp import FastMCP

from client.api_client import CygnusXAPIClient, CygnusXAPIError
from core.config import settings


def register(mcp: FastMCP, api: CygnusXAPIClient) -> None:
    @mcp.tool()
    async def list_workspace_files(path: str = "", pattern: str = "") -> dict:
        try:
            data = await api.list_workspace_files(path=path or None, pattern=pattern or None)
            return {"success": True, "summary": "工作区文件列表", "data": data}
        except CygnusXAPIError as exc:
            return {"success": False, "summary": f"列出工作区文件失败: {exc.detail}"}

    @mcp.tool()
    async def search_workspace_files(query: str, limit: int = 50) -> dict:
        try:
            data = await api.search_workspace_files(query=query, limit=limit)
            return {"success": True, "summary": "工作区搜索结果", "data": data}
        except CygnusXAPIError as exc:
            return {"success": False, "summary": f"搜索工作区文件失败: {exc.detail}"}

    @mcp.tool()
    async def cygnusx_list_files(directory: str = "") -> dict:
        try:
            data = await api.list_files(directory=directory or None)
            return {"success": True, "summary": "文件列表", "data": data}
        except CygnusXAPIError as exc:
            return {"success": False, "summary": f"获取文件列表失败: {exc.detail}"}

    @mcp.tool()
    async def cygnusx_get_file_tree() -> dict:
        try:
            data = await api.get_file_tree()
            return {"success": True, "summary": "文件树", "data": data}
        except CygnusXAPIError as exc:
            return {"success": False, "summary": f"获取文件树失败: {exc.detail}"}

    @mcp.tool()
    async def cygnusx_list_directories() -> dict:
        try:
            data = await api.list_directories()
            return {"success": True, "summary": "目录列表", "data": data}
        except CygnusXAPIError as exc:
            return {"success": False, "summary": f"获取目录失败: {exc.detail}"}

    @mcp.tool()
    async def cygnusx_get_task_outputs(task_id: str) -> dict:
        try:
            data = await api.get_task(task_id)
            return {
                "success": True,
                "summary": "任务输出",
                "data": {
                    "work_dir": data.get("work_dir", ""),
                    "result_path": data.get("result_path", ""),
                    "task": data,
                },
            }
        except CygnusXAPIError as exc:
            return {"success": False, "summary": f"获取任务输出失败: {exc.detail}"}

    @mcp.tool()
    async def cygnusx_read_file_content(file_path: str, max_lines: int = 50) -> dict:
        try:
            data = await api.preview_file(
                file_path, max_lines=max(1, min(max_lines, settings.max_file_preview_lines))
            )
            return {"success": True, "summary": "文件内容", "data": data}
        except CygnusXAPIError as exc:
            return {"success": False, "summary": f"读取文件失败: {exc.detail}"}

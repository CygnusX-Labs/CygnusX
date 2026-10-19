"""Unified Run monitoring and plan confirmation tools."""

from fastmcp import FastMCP

from client.api_client import CygnusXAPIClient, CygnusXAPIError


def register(mcp: FastMCP, api: CygnusXAPIClient) -> None:
    @mcp.tool()
    async def cygnusx_list_runs(project_slug: str = "", status: str = "") -> dict:
        """列出当前 API 身份可访问的 Run；可按 project_slug 和 status 过滤，返回平台 Run 记录及匹配总数摘要。"""
        try:
            data = await api.list_runs(project_slug or None, status or None)
            return {"success": True, "summary": f"共 {len(data)} 个 Run", "data": data}
        except CygnusXAPIError as exc:
            return {"success": False, "summary": f"获取 Run 失败: {exc.detail}"}

    @mcp.tool()
    async def cygnusx_get_run_status(run_id: str) -> dict:
        """按 run_id 查询平台 Run 记录；返回记录中的当前状态及关联 task_id（若有），不提交或修改任务。"""
        try:
            data = await api.get_run(run_id)
            return {"success": True, "summary": f"Run 状态: {data.get('status')}", "data": data}
        except CygnusXAPIError as exc:
            return {"success": False, "summary": f"获取 Run 状态失败: {exc.detail}"}

    @mcp.tool()
    async def cygnusx_get_run_logs(run_id: str, limit: int = 200) -> dict:
        """按 run_id 读取平台持久化事件日志；limit 默认 200 并限制在 1–500，data 返回事件列表及平台提供的事件元数据。"""
        try:
            data = await api.get_run_events(run_id, max(1, min(limit, 500)))
            return {"success": True, "summary": f"共 {len(data.get('events', []))} 条事件", "data": data}
        except CygnusXAPIError as exc:
            return {"success": False, "summary": f"获取 Run 事件失败: {exc.detail}"}

    @mcp.tool()
    async def cygnusx_verify_artifact(run_id: str) -> dict:
        """按 run_id 查询已登记的产物及平台返回的校验摘要（包括可用的 checksum）；此工具读取平台记录，不自行重算文件完整性。"""
        try:
            data = await api.get_run_artifacts(run_id)
            return {"success": True, "summary": f"共 {len(data.get('artifacts', []))} 个产物", "data": data}
        except CygnusXAPIError as exc:
            return {"success": False, "summary": f"查询产物失败: {exc.detail}"}

    @mcp.tool()
    async def cygnusx_confirm_run_plan(
        run_id: str, confirmation_id: str = "", user_confirmed: bool = False
    ) -> dict:
        """确认指定 run_id 的计划属于有副作用操作：首次调用创建待网页审批记录；仅在人类批准后携带服务端 confirmation_id 重试才会确认并进入任务队列。user_confirmed 布尔值不能授权。"""
        if user_confirmed:
            return {"success": False, "summary": "拒绝 user_confirmed 布尔自证；请使用服务端 confirmation_id。"}
        if not confirmation_id:
            confirmation = await api.create_tool_confirmation(
                "cygnusx_confirm_run_plan", {"run_id": run_id}
            )
            return {
                "success": True,
                "needs_confirmation": True,
                "summary": "请在平台网页批准 Run 确认记录后携带 confirmation_id 重试。",
                "data": {"run_id": run_id, "confirmation": confirmation},
            }
        try:
            data = await api.confirm_run(run_id, confirmation_id)
            return {"success": True, "summary": "Run 已确认并进入任务队列", "data": data}
        except CygnusXAPIError as exc:
            return {"success": False, "summary": f"确认 Run 失败: {exc.detail}"}

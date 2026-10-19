"""分析提交工具"""

from fastmcp import FastMCP

from client.api_client import CygnusXAPIClient, CygnusXAPIError


def register(mcp: FastMCP, api: CygnusXAPIClient) -> None:

    @mcp.tool()
    async def cygnusx_submit_analysis(
        flow_id: str,
        name: str = "",
        parameters: dict | None = None,
        sample_sheet: list[dict] | None = None,
        comparisons: list[dict] | None = None,
        confirmation_id: str = "",
        user_confirmed: bool = False,
    ) -> dict:
        """提交分析任务到平台。需要服务端 confirmation_id。"""
        if user_confirmed:
            return {"success": False, "summary": "拒绝 user_confirmed 布尔自证；请使用服务端 confirmation_id。"}
        if not confirmation_id:
            confirmation = await api.create_tool_confirmation(
                "cygnusx_submit_analysis",
                {
                    "flow_id": flow_id,
                    "name": name or f"{flow_id} analysis",
                    "parameters": parameters or {},
                    "sample_sheet": sample_sheet or [],
                    "comparisons": comparisons or [],
                    "execution_mode": "local",
                    "idempotency_key": None,
                },
            )
            return {
                "success": True,
                "needs_confirmation": True,
                "summary": (
                    f"即将提交分析任务:\n"
                    f"  流程: {flow_id}\n"
                    f"  名称: {name or '(自动生成)'}\n"
                    f"  样本数: {len(sample_sheet) if sample_sheet else 0}\n"
                    f"  比较组: {len(comparisons) if comparisons else 0}\n"
                    "请在平台网页批准确认记录后携带 confirmation_id 重试。"
                ),
                "data": {
                    "flow_id": flow_id,
                    "name": name,
                    "parameters": parameters,
                    "sample_sheet": sample_sheet,
                    "comparisons": comparisons,
                    "confirmation": confirmation,
                },
            }

        payload = {
            "flow_id": flow_id,
            "name": name or f"{flow_id} analysis",
            "parameters": parameters or {},
            "sample_sheet": sample_sheet or [],
            "comparisons": comparisons or [],
            "execution_mode": "local",
            "idempotency_key": None,
        }
        payload["confirmation_id"] = confirmation_id

        try:
            result = await api.submit_task(payload)
            task_id = result.get("id", "?")
            return {
                "success": True,
                "summary": (
                    f"分析任务已提交!\n"
                    f"  任务 ID: {task_id}\n"
                    f"  状态: {result.get('status', 'queued')}\n"
                    f"使用 cygnusx_get_task_progress 监控进度。"
                ),
                "data": result,
                "next_steps": [
                    f"调用 cygnusx_get_task_progress(task_id='{task_id}') 监控进度",
                    "任务完成后调用 cygnusx_get_task_outputs 查看结果",
                ],
            }
        except CygnusXAPIError as e:
            return {"success": False, "summary": f"提交失败: {e.detail}"}

    @mcp.tool()
    async def cygnusx_prepare(flow_id: str, arguments: dict) -> dict:
        """预检任意已开放分析流程的参数（固定工具，不随流程数变化）。

        对 flow_id 与 arguments 做全量服务端校验（参数类型/枚举、样本表、
        比较组、资源约束），通过后冻结参数快照并创建待确认记录（默认 30 分钟有效）。
        流程特定参数一律放入 arguments 对象，字段以 cygnusx_get_flow_detail
        返回的契约为准。任务不会立即提交——须用户在平台网页确认后，再由
        cygnusx_submit 凭 confirmation_id 提交。

        :param flow_id: 流程 ID（先调 cygnusx_list_flows / cygnusx_get_flow_detail 确认已开放）
        :param arguments: 该流程的完整参数对象
        :return: JSON 格式预检结果，含 valid / errors / confirmation_id / expires_at

        示例:
            await cygnusx_prepare("rna_seq", {"task_name": "demo", "species": "human", ...})
        """
        try:
            result = await api.prepare_flow(flow_id, arguments)
        except CygnusXAPIError as e:
            return {"success": False, "summary": f"预检失败: {e.detail}"}
        if not result.get("valid"):
            errors = result.get("errors") or []
            lines = [f"- {e.get('field', '?')}: {e.get('message', '')}" for e in errors]
            return {
                "success": False,
                "summary": "参数校验未通过:\n" + "\n".join(lines),
                "data": result,
            }
        confirmation_id = result.get("confirmation_id", "")
        return {
            "success": True,
            "summary": (
                f"预检通过: {result.get('flow_name', flow_id)}"
                f"（样本 {result.get('sample_count', 0)} 个，比较组 {result.get('comparison_count', 0)} 个）。\n"
                f"确认记录: {confirmation_id}（{result.get('expires_at', '?')} 前有效）\n"
                "请在平台网页确认后调用 cygnusx_submit 提交。"
            ),
            "data": result,
            "next_steps": [
                "提示用户在平台网页确认该分析任务",
                f"用户确认后调用 cygnusx_submit(confirmation_id='{confirmation_id}')",
            ],
        }

    @mcp.tool()
    async def cygnusx_submit(confirmation_id: str, user_confirmed: bool = False) -> dict:
        """提交已预检并经由用户在平台网页确认的分析任务（固定工具）。

        仅接受服务端确认记录 ID：服务端校验归属、有效期与消费状态，原子单次
        消费防并发重放；同一 confirmation_id 重复调用幂等返回既有 task_id，
        不新建任务。严禁用布尔值自证已确认。

        :param confirmation_id: cygnusx_prepare 返回、且已由用户在平台网页批准的确认记录 ID
        :return: JSON 格式提交结果，含 task_id / status / task_url

        示例:
            await cygnusx_submit("3f8a2b...-....-....")
        """
        if user_confirmed:
            return {"success": False, "summary": "拒绝 user_confirmed 布尔自证；请使用服务端 confirmation_id。"}
        if not confirmation_id:
            return {"success": False, "summary": "缺少 confirmation_id；请先调用 cygnusx_prepare。"}
        try:
            result = await api.submit_flow_confirmation(confirmation_id)
        except CygnusXAPIError as e:
            return {"success": False, "summary": f"提交失败: {e.detail}"}
        task_id = result.get("task_id", "?")
        return {
            "success": True,
            "summary": (
                f"分析任务已提交!\n  任务 ID: {task_id}\n  状态: {result.get('status', 'queued')}"
            ),
            "data": result,
            "next_steps": [
                f"调用 cygnusx_get_task_progress(task_id='{task_id}') 监控进度",
                "任务完成后调用 cygnusx_get_task_logs / cygnusx_get_task 查看结果",
            ],
        }

    @mcp.tool()
    async def cygnusx_preview_analysis(
        flow_id: str,
        parameters: dict | None = None,
        sample_sheet: list[dict] | None = None,
    ) -> dict:
        """对 flow_id 执行只读浅预检：检查必填 parameters 是否提供及所需 sample_sheet 是否非空，返回缺项或可继续提交的提示；不验证完整类型/枚举约束、不创建任务也不提交分析。"""

        try:
            flow = await api.get_flow(flow_id)
            flow_params = flow.get("parameters", [])
            required = [
                p.get("name", p.get("key"))
                for p in flow_params
                if p.get("required", False)
            ]
            provided = set((parameters or {}).keys())
            missing = [r for r in required if r not in provided]

            issues = []
            if missing:
                issues.append(f"缺少必填参数: {', '.join(missing)}")
            if not sample_sheet and flow.get("sample_sheet"):
                issues.append("该流程需要样本表 (sample_sheet)")

            if issues:
                return {
                    "success": False,
                    "summary": "参数验证未通过:\n" + "\n".join(f"- {i}" for i in issues),
                    "data": {"missing_params": missing},
                }
            return {
                "success": True,
                "summary": f"参数验证通过，可以提交 {flow_id} 分析。",
                "data": {"flow_id": flow_id, "valid": True},
            }
        except CygnusXAPIError as e:
            return {"success": False, "summary": f"验证失败: {e.detail}"}

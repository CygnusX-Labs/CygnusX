"""数据下载工具"""

from fastmcp import FastMCP

from client.api_client import OmicHubAPIClient, OmicHubAPIError


def register(mcp: FastMCP, api: OmicHubAPIClient) -> None:

    @mcp.tool()
    async def omichub_submit_download(
        source: str,
        accession: str = "",
        object_uri: str = "",
        provider: str = "",
        user_confirmed: bool = False,
    ) -> dict:
        """提交数据下载任务。支持 EBI/SRA 数据库下载和云存储下载。

        Args:
            source: 下载来源 - "ebi" (SRA/ENA) 或 "cloud_storage"
            accession: EBI/SRA 登录号 (如 PRJNA123456, SRR123456)，source=ebi 时必填
            object_uri: 云存储对象路径，source=cloud_storage 时必填
            provider: 云存储提供商 (aliyun/volc/huawei)，source=cloud_storage 时必填
            user_confirmed: 设为 True 确认提交
        """
        if not user_confirmed:
            desc = accession if source == "ebi" else f"{provider}://{object_uri}"
            return {
                "success": True,
                "needs_confirmation": True,
                "summary": f"即将提交下载任务: [{source}] {desc}\n请确认后设置 user_confirmed=True。",
                "data": {"source": source, "accession": accession, "object_uri": object_uri},
            }

        payload: dict = {"source": source}
        if source == "ebi":
            payload["accession"] = accession
        else:
            payload["object_uri"] = object_uri
            payload["provider"] = provider

        try:
            result = await api.submit_download(payload)
            task_id = result.get("id", "?")
            return {
                "success": True,
                "summary": f"下载任务已提交! 任务 ID: {task_id}",
                "data": result,
                "next_steps": [
                    f"调用 omichub_get_download_progress(task_id='{task_id}') 查看下载进度",
                ],
            }
        except OmicHubAPIError as e:
            return {"success": False, "summary": f"提交下载失败: {e.detail}"}

    @mcp.tool()
    async def omichub_list_downloads() -> dict:
        """列出用户的数据下载任务。"""
        try:
            data = await api.list_downloads()
            tasks = data.get("tasks", data) if isinstance(data, dict) else data
            lines = []
            for t in (tasks if isinstance(tasks, list) else []):
                lines.append(
                    f"- [{t.get('status', '?')}] {t.get('name', t.get('id', '?'))} "
                    f"(progress={t.get('progress', 0):.0%})"
                )
            return {
                "success": True,
                "summary": f"下载任务:\n" + "\n".join(lines) if lines else "暂无下载任务",
                "data": data,
            }
        except OmicHubAPIError as e:
            return {"success": False, "summary": f"获取下载列表失败: {e.detail}"}

    @mcp.tool()
    async def omichub_get_download_progress(task_id: str) -> dict:
        """获取下载任务的逐 run 进度（下载/解压/压缩各阶段）。"""
        try:
            data = await api.get_download_progress(task_id)
            runs = data.get("runs", [])
            lines = []
            for r in runs[:20]:
                lines.append(
                    f"- {r.get('run', '?')}: {r.get('stage', '?')} "
                    f"({r.get('progress', 0):.0%})"
                )
            overall = data.get("overall_progress", 0)
            return {
                "success": True,
                "summary": f"总进度: {overall:.0%}\n" + "\n".join(lines),
                "data": data,
            }
        except OmicHubAPIError as e:
            return {"success": False, "summary": f"获取下载进度失败: {e.detail}"}

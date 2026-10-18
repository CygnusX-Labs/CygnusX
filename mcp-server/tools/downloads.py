"""数据下载工具 — 公共数据库（SRA/GEO）高速下载 + 多云存储下载 + 直链下载"""

from typing import Literal

from client.api_client import CygnusXAPIClient, CygnusXAPIError
from fastmcp import FastMCP


def register(mcp: FastMCP, api: CygnusXAPIClient) -> None:

    @mcp.tool()
    async def cygnusx_submit_download(
        source: str = "sra",
        accession: str = "",
        download_method: Literal["aws", "ftp"] = "aws",
        multithreads: int = 4,
        aws_threads: int = 8,
        cloud_provider: str = "",
        object_uri: str = "",
        recursive: bool = True,
        links: list[str] | None = None,
        target_directory: str = "",
        dry_run: bool = False,
        confirmation_id: str = "",
        user_confirmed: bool = False,
    ) -> dict:
        """提交数据下载任务，产物落到用户工作区 downloads 目录（可选子目录）。

        支持三类来源（source）：
        1. "sra"（默认）— 公共数据库高速下载，走 EBIDownload 引擎：
           - 提交单个 ENA/SRA 登录号：项目号（PRJNA/PRJEB 开头，如 PRJNA1285930）、
             测序 run（SRR/ERR/DRR 开头）；GSE/GSM 需先经数据集解析；
           - download_method: "aws"（推荐，SRA 公共镜像）/ "ftp"；
           - multithreads: 并发下载 run 数（1-32），aws_threads: 单文件 AWS 并发线程（1-64）；
           - dry_run=True 可先试跑验证登录号，不实际下载。
        2. "cloud_storage" — 云服务商对象存储高速下载：
           - cloud_provider: "aliyun"（oss://）/ "volc"（tos://）/ "huawei"（obs://）；
           - object_uri 必须以对应前缀开头，如 oss://bucket/path；recursive 控制是否递归目录。
        3. "direct_link" — HTTP/HTTPS/FTP 直链批量下载：
           - links 传下载链接列表（禁止内网地址）。

        :param source: 下载来源："sra"（公共数据库）/"cloud_storage"（云存储）/"direct_link"（直链）
        :param accession: 公共数据库登录号（PRJNA…/PRJEB…/SRR…/ERR…/DRR…），source="sra" 时必填
        :param download_method: SRA 下载方式 "aws"（默认，最快）/"ftp"，仅 source="sra" 有效
        :param multithreads: 并发下载 run 数，默认 4
        :param aws_threads: 单文件 AWS 并发线程数，默认 8
        :param cloud_provider: 云商 "aliyun"/"volc"/"huawei"，source="cloud_storage" 时必填
        :param object_uri: 对象路径（oss:// / tos:// / obs:// 前缀），source="cloud_storage" 时必填
        :param recursive: 云存储目录是否递归下载，默认 True
        :param links: HTTP/HTTPS/FTP 下载链接列表，source="direct_link" 时必填
        :param target_directory: 下载到用户根目录下的子目录（如 "project_x"），留空=downloads 目录
        :param dry_run: True 时仅模拟下载（仅 SRA），用于校验登录号
        :param user_confirmed: 设为 True 确认提交（提交任务前必须经用户确认）
        :return: JSON 格式结果，含 success、summary、data、next_steps

        示例:
            await cygnusx_submit_download("sra", "SRR12345", "aws", aws_threads=16)
            # 提交 SRR12345 的 AWS 高速下载任务
        """
        if user_confirmed:
            return {"success": False, "summary": "拒绝 user_confirmed 布尔自证；请使用服务端 confirmation_id。"}
        normalized_links = [link.strip() for link in (links or []) if link and link.strip()]
        normalized_object_uri = object_uri.strip()
        if not confirmation_id:
            if source == "sra":
                desc = f"{accession}（{download_method} 高速下载）"
            elif source == "cloud_storage":
                desc = f"{cloud_provider}: {object_uri}"
            else:
                desc = f"{len(links or [])} 个直链"
            target = f" -> downloads/{target_directory}" if target_directory else " -> downloads"
            confirmation_payload = {
                "source": source,
                "links": normalized_links,
                "download_threads": 4,
                "overwrite_policy": "auto_rename",
                "accession": accession,
                "download_method": download_method,
                "multithreads": multithreads,
                "aws_threads": aws_threads,
                "cloud_provider": cloud_provider or None,
                "object_uri": normalized_object_uri,
                "recursive": recursive,
                "target_directory": target_directory,
                "dry_run": dry_run,
            }
            return {
                "success": True,
                "needs_confirmation": True,
                "summary": (
                    f"即将提交下载任务: [{source}] {desc}{target}\n"
                    "请在平台网页批准服务端确认记录后携带 confirmation_id 重试。"
                ),
                "data": {
                    "source": source,
                    "accession": accession,
                    "object_uri": object_uri,
                    "confirmation": await api.create_tool_confirmation(
                        "cygnusx_submit_download",
                        confirmation_payload,
                    ),
                },
            }

        payload: dict = {
            "source": source,
            "accession": accession,
            "download_method": download_method,
            "multithreads": multithreads,
            "aws_threads": aws_threads,
            "dry_run": dry_run,
        }
        if source == "sra":
            payload["accession"] = accession
            payload["download_method"] = download_method
            payload["multithreads"] = multithreads
            payload["aws_threads"] = aws_threads
            payload["dry_run"] = dry_run
        elif source == "cloud_storage":
            payload["cloud_provider"] = cloud_provider
            payload["object_uri"] = normalized_object_uri
            payload["recursive"] = recursive
        else:
            payload["links"] = normalized_links
        payload.update(
            {
                "links": normalized_links,
                "download_threads": 4,
                "overwrite_policy": "auto_rename",
                "cloud_provider": cloud_provider or None,
                "object_uri": normalized_object_uri,
                "recursive": recursive,
                "target_directory": target_directory,
            }
        )
        payload["confirmation_id"] = confirmation_id

        try:
            result = await api.submit_download(payload)
            task_id = result.get("id", "?")
            return {
                "success": True,
                "summary": (
                    f"下载任务已提交! 任务 ID: {task_id}\n"
                    f"产物目录: 用户 downloads/{target_directory or ''}（完成后自动登记到数据管理）"
                ),
                "data": result,
                "next_steps": [
                    f"调用 cygnusx_get_download_progress(task_id='{task_id}') 查看逐 run 下载进度",
                    "也可用 cygnusx_list_downloads 查看全部下载任务状态",
                ],
            }
        except CygnusXAPIError as e:
            return {"success": False, "summary": f"提交下载失败: {e.detail}"}

    @mcp.tool()
    async def cygnusx_list_downloads() -> dict:
        """列出用户的数据下载任务（名称、状态、进度、产物目录）。

        :return: JSON 格式结果，含 success、summary、data

        示例:
            await cygnusx_list_downloads()
            # 返回所有下载任务列表
        """
        try:
            data = await api.list_downloads()
            tasks = data.get("items", []) if isinstance(data, dict) else data
            lines = []
            for t in (tasks if isinstance(tasks, list) else []):
                progress = t.get("progress") or 0
                lines.append(
                    f"- [{t.get('status', '?')}] {t.get('name', t.get('id', '?'))} "
                    f"(progress={progress:.0%}, id={t.get('id', '?')})"
                )
            return {
                "success": True,
                "summary": "下载任务:\n" + "\n".join(lines) if lines else "暂无下载任务",
                "data": data,
            }
        except CygnusXAPIError as e:
            return {"success": False, "summary": f"获取下载列表失败: {e.detail}"}

    @mcp.tool()
    async def cygnusx_get_download_progress(task_id: str) -> dict:
        """获取下载任务的逐 run 分阶段进度（下载/解压/压缩）。

        返回每个 SRR run 的 stage（downloading/extracting/compressing/completed/failed）
        与总进度百分比；source="unavailable" 表示任务尚未开始运行或进度接口暂不可用。

        :param task_id: 下载任务 ID
        :return: JSON 格式进度详情，含 success、summary、data、overall_percent

        示例:
            await cygnusx_get_download_progress("download_123")
            # 返回任务进度：总进度 75.3%，SRR123: downloading (60.2%), SRR456: completed (100%)
        """
        try:
            data = await api.get_download_progress(task_id)
            runs = data.get("runs") or {}
            lines = []
            for run_id, r in list(runs.items())[:20]:
                percent = r.get("overall_percent", 0)
                lines.append(f"- {run_id}: {r.get('stage', '?')} ({percent:.1f}%)")
            overall = data.get("overall_percent", 0)
            source = data.get("source", "progress_api")
            if source == "unavailable" and not runs:
                return {
                    "success": True,
                    "summary": "进度暂不可用（任务排队中或进度接口未就绪），请稍后再查。",
                    "data": data,
                }
            return {
                "success": True,
                "summary": f"总进度: {overall:.1f}%\n" + "\n".join(lines),
                "data": data,
            }
        except CygnusXAPIError as e:
            return {"success": False, "summary": f"获取下载进度失败: {e.detail}"}

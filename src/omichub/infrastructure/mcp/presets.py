"""MCP 预设服务注册表 — 内置 MCP（平台操作 / 生信工具箱）

内置服务（transport=builtin）在进程内执行，无需外部进程，便于开箱即用。
真实 stdio/sse MCP 由 MCPClient 通过 Python MCP SDK 接入。
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from omichub.application.schemas.tool_invocation import ToolInvocationContext
from omichub.application.services.tool_bridge_service import get_tool_bridge_service
from omichub.infrastructure.mcp.pipeline_preset import (
    OMICHUB_PIPELINES_SERVER_ID,
    OMICHUB_PIPELINES_SERVER_NAME,
    build_pipeline_preset,
)

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


# ====================== 平台操作工具 (builtin) ======================

OMICHUB_PLATFORM_SERVER_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "omichub-platform.builtin")

WORKSPACE_FILES_SYSTEM_PROMPT_SUFFIX = """## 工作区文件工具

你拥有当前会话用户工作区的只读文件工具：
- `list_workspace_files(path?, pattern?)`：列出目录直接子项；`path` 为空时列根目录，`pattern` 支持 `*.csv` 等 glob。
- `search_workspace_files(query, limit?)`：从工作区根目录递归按文件名模糊搜索。
- `find_session_uploads(session_id?)`：按会话 ID 检索该聊天窗口中用户上传过的文件；`session_id` 留空表示当前会话。
- 找到文件后，将返回的 `file_id` 直接交给已有的 `workspace_read_file(file_id)` 读取或分析。

强制行为：
- 用户询问“工作区里有什么文件 / 有哪些数据文件”时，必须先调用 `list_workspace_files` 获取真实结果，禁止声称没有浏览文件的工具。
- 用户明确要求寻找某个文件时，必须先调用 `search_workspace_files` 获取真实结果。
- 需要找回本会话之前上传的数据文件时，优先调用 `find_session_uploads`（当前会话 ID 自动生效），而不是漫无目的地全局搜索。
- 回答时用列表展示名称、类型和修改时间；找到文件后询问用户希望对哪个文件执行什么操作。
- 文件工具仅限当前用户工作区且只读；不得尝试绝对路径、`..` 或其他用户目录。

数据缺失时的行为（所有绘图/分析任务通用）：
- 用户要求绘图或分析，但对话中没有提供任何数据（无附件、无 file_id、用户也未指明工作区中的具体文件）时，禁止自行全局搜索猜测数据。
- 此时直接回复用户，开头固定使用“📤 需要您提供数据：”，简要说明需要什么数据（格式、必要列/字段），并引导用户上传文件或告知工作区中的具体文件路径。
- 只有在用户提供了附件、file_id，或明确指定了工作区文件时，才继续执行绘图/分析。

多选项澄清的交互形式（所有任务通用）：
- 需要用户在多个选项/方向/方案中做选择时，若当前环境提供 `ask_user` 工具，**必须**调用
  `ask_user` 并通过 `options` 给出可一键点击的选项（弹窗选择），禁止用纯文本罗列
  “选项 1/2/3”让用户手动回复编号；问题要具体、选项互斥且覆盖主要分支。
- 没有 `ask_user` 工具的普通会话中，才允许用编号列表呈现选项，且每个选项一句话说清。
"""


async def _platform_list_tasks(
    arguments: dict[str, Any], user_id: str | None = None, **_kw: Any
) -> dict[str, Any]:
    from omichub.application.services.task_service import TaskService
    from omichub.infrastructure.database.session import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        service = TaskService(db)
        result = await service.list_tasks(user_id or "anonymous", status=arguments.get("status"))
        tasks = result.tasks if hasattr(result, "tasks") else []
        return {
            "tasks": [
                {"id": str(t.id), "name": t.name, "flow_id": t.flow_id, "status": t.status, "progress": t.progress}
                for t in tasks[:30]
            ]
        }


async def _platform_get_task(
    arguments: dict[str, Any], user_id: str | None = None, **_kw: Any
) -> dict[str, Any]:
    from omichub.application.services.task_service import TaskService
    from omichub.infrastructure.database.session import get_session_factory

    task_id = arguments.get("task_id", "")
    factory = get_session_factory()
    async with factory() as db:
        service = TaskService(db)
        t = await service.get_task(uuid.UUID(task_id), user_id or "anonymous")
        return {
            "id": str(t.id), "name": t.name, "flow_id": t.flow_id,
            "status": t.status, "progress": t.progress,
            "work_dir": t.work_dir, "error_message": t.error_message,
            "created_at": str(t.created_at), "started_at": str(t.started_at),
        }


async def _platform_sandbox_execute(
    arguments: dict[str, Any], user_id: str | None = None, **_kw: Any
) -> dict[str, Any]:
    from omichub.application.services.sandbox_service import SandboxService
    from omichub.infrastructure.database.session import get_session_factory

    code = arguments.get("code", "")
    factory = get_session_factory()
    async with factory() as db:
        service = SandboxService(db)
        uid = uuid.UUID(user_id) if user_id else uuid.UUID(int=0)
        session = await service.create_session(uid, "python")
        stdout_parts: list[str] = []
        stderr_parts: list[str] = []
        error = None
        async for event in service.execute_code(uid, session.id, code, 300):
            etype = event.get("type")
            if etype == "stdout":
                stdout_parts.append(event.get("data", ""))
            elif etype == "stderr":
                stderr_parts.append(event.get("data", ""))
            elif etype == "error":
                error = event.get("detail")
        await db.commit()
        return {
            "stdout": "".join(stdout_parts)[-3000:],
            "stderr": "".join(stderr_parts)[-1000:],
            "error": error,
            "session_id": str(session.id),
        }


async def _platform_list_flows(arguments: dict[str, Any], **_kw: Any) -> dict[str, Any]:
    from omichub.application.services.flow_service import FlowService

    service = FlowService()
    result = service.list_flows(category=arguments.get("category"))
    items = result.items if hasattr(result, "items") else []
    return {
        "flows": [
            {"id": f.meta.id, "name": f.meta.name, "category": f.meta.category, "version": f.meta.version}
            for f in items
        ]
    }


async def _platform_read_file(
    arguments: dict[str, Any], user_id: str | None = None, **_kw: Any
) -> dict[str, Any]:
    from omichub.core.config import get_settings

    settings = get_settings()
    file_path = arguments.get("file_path", "")
    max_lines = int(arguments.get("max_lines", 50))
    user_root = Path(settings.storage_path) / "users" / (user_id or "anonymous")
    target = (user_root / file_path).resolve()

    if not str(target).startswith(str(user_root.resolve())):
        return {"error": "路径越权"}
    if not target.is_file():
        return {"error": "文件不存在"}

    lines: list[str] = []
    try:
        with open(target, errors="replace") as f:
            for i, line in enumerate(f):
                if i >= max_lines:
                    break
                lines.append(line.rstrip("\n"))
    except OSError as e:
        return {"error": str(e)}

    return {"path": file_path, "lines": lines, "truncated": len(lines) >= max_lines}


# ====================== 工作区文件感知（builtin，按用户隔离，只读） ======================
# 对应《星尘 AI 工作区文件感知 + @ 引用》阶段 1：
#   workspace_list_files / workspace_read_file / workspace_get_file_info
# 权限硬限定为当前登录用户的工作区根目录；默认只读，不暴露任何写/删除能力。

# 可直接返回内容预览的文本类扩展名
_TEXT_SUFFIXES = frozenset(
    {
        ".txt", ".md", ".csv", ".tsv", ".json", ".yaml", ".yml", ".log",
        ".vcf", ".gff", ".gtf", ".bed", ".sam", ".fasta", ".fa", ".fna",
        ".py", ".r", ".sh", ".xml", ".html", ".tsv.gz", ".csv.gz",
    }
)

# 二进制 / 测序原始数据：只回元数据，绝不读内容
_BINARY_ONLY_SUFFIXES = frozenset(
    {
        ".bam", ".cram", ".bai", ".crai", ".fastq", ".fq", ".fastq.gz", ".fq.gz",
        ".h5ad", ".h5", ".rds", ".rdata", ".loom", ".bw", ".bigwig", ".2bit",
        ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z",
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".tiff",
        ".pdf", ".db", ".sqlite",
    }
)

# read_file 默认内容上限（100KB，超出截断并标注）
_DEFAULT_READ_MAX_BYTES = 100 * 1024


def _is_text_file(name: str) -> bool:
    lower = name.lower()
    return any(lower.endswith(suf) for suf in _TEXT_SUFFIXES)


def _human_size(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f}MB"
    if size >= 1024:
        return f"{size / 1024:.1f}KB"
    return f"{size}B"


async def _resolve_workspace_file(
    user_id: str, file_id: str, db: Any
) -> tuple[Path | None, dict[str, Any]]:
    """把工作区文件引用解析为物理路径 + 元数据。

    支持两种 file_id：
      - 文件中心记录（UUID，引用形如 file://{uuid}）；
      - 聊天上传文件（32 位 hex，引用形如 upload://{hex}）。
    强制按 user_id 做归属校验，拒绝路径逃逸。返回 (path, metadata)；
    path 为 None 时表示解析失败，metadata 含 error 说明。
    """
    from omichub.infrastructure.config.storage_config import get_user_chat_upload_dir
    from omichub.infrastructure.database.repositories.file_repository import (
        FileRepositoryImpl,
    )

    fid = (file_id or "").strip()
    # 兼容 file://uuid、upload://hex，以及被二次包裹的 upload://file://uuid。
    # 显式 upload://  scheme 直接走聊天上传通道：32 位 hex 的聊天上传 id
    # 也能被 uuid.UUID() 解析，误判会错路由到文件中心分支导致"文件不存在"。
    explicit_upload_scheme = False
    for _ in range(3):
        if fid.startswith("file://"):
            fid = fid[len("file://"):]
        elif fid.startswith("upload://"):
            fid = fid[len("upload://"):]
            explicit_upload_scheme = True
        else:
            break
    fid = fid.strip()
    if not fid or ".." in fid or fid.startswith("/"):
        return None, {"error": f"非法 file_id: {file_id}"}

    # 1) 文件中心记录（UUID）——仓储层强制 user_id 过滤防水平越权
    try:
        file_uuid = uuid.UUID(fid)
    except ValueError:
        file_uuid = None

    if file_uuid is not None and not explicit_upload_scheme:
        from omichub.application.services.file_service import FileService

        repo = FileRepositoryImpl(db)
        data_file = await repo.get_by_id(uuid.UUID(user_id), file_uuid)
        if data_file is not None:
            service = FileService(db)
            target = await service.get_file_path(uuid.UUID(user_id), file_uuid)  # 已做路径越权校验
            try:
                target.resolve().relative_to(service.user_workspace_root(uuid.UUID(user_id)).resolve())
            except ValueError:
                return None, {"error": "文件不在当前用户工作区内"}
            meta = {
                "file_id": fid,
                "ref": f"file://{fid}",
                "name": data_file.original_name,
                "size": data_file.size,
                "size_human": _human_size(data_file.size),
                "file_type": (
                    data_file.file_type.value
                    if hasattr(data_file.file_type, "value")
                    else str(data_file.file_type)
                ),
                "directory": getattr(data_file, "directory", "") or "",
                "created_at": (
                    data_file.created_at.isoformat() if getattr(data_file, "created_at", None) else None
                ),
            }
            return target, meta
        # 文件中心未命中：可能是裸 hex 的聊天上传 id，继续走聊天上传分支兜底

    # 2) 聊天上传文件（hex id，落盘名可能带扩展名，用前缀 glob 匹配）
    upload_dir = get_user_chat_upload_dir(user_id)
    candidates = sorted(upload_dir.glob(f"{fid}*"), key=lambda p: (len(p.suffix), p.name))
    if not candidates:
        return None, {"error": f"文件不存在: {fid}"}
    target = candidates[0]
    try:
        target.resolve().relative_to(upload_dir.resolve())
    except ValueError:
        return None, {"error": "路径越权"}
    stat = target.stat()
    meta = {
        "file_id": fid,
        "ref": f"upload://{fid}",
        "name": target.name,
        "size": stat.st_size,
        "size_human": _human_size(stat.st_size),
        "file_type": "chat_upload",
        "directory": "workspace/chat-uploads",
        "created_at": None,
    }
    return target, meta


async def _workspace_list_files(
    arguments: dict[str, Any],
    user_id: str | None = None,
    context: ToolInvocationContext | None = None,
    **_kw: Any,
) -> dict[str, Any]:
    """兼容旧工具名，委托规范的 ``list_workspace_files`` 实现。"""
    result = await _list_workspace_files(arguments, user_id=user_id, context=context)
    result["files"] = [
        {**item, "file_id": f"file://{item['file_id']}"}
        for item in result["items"]
        if item["type"] == "file"
    ]
    result["directories"] = [
        item["relative_path"] for item in result["items"] if item["type"] == "folder"
    ]
    return result


async def _list_workspace_files(
    arguments: dict[str, Any],
    user_id: str | None = None,
    context: ToolInvocationContext | None = None,
) -> dict[str, Any]:
    """列出当前用户工作区目录的文件和文件夹。"""
    from omichub.application.services.file_service import FileService
    from omichub.infrastructure.database.session import get_session_factory

    uid = uuid.UUID(user_id) if user_id else None
    if uid is None:
        return {"error": "无法识别当前用户"}
    if context is not None:
        result = await FileService(context.db).list_workspace_files(
            uid,
            path=arguments.get("path"),
            pattern=arguments.get("pattern"),
        )
    else:
        factory = get_session_factory()
        async with factory() as db:
            result = await FileService(db).list_workspace_files(
                uid,
                path=arguments.get("path"),
                pattern=arguments.get("pattern"),
            )

    lines = []
    for item in result["items"]:
        if item["type"] == "folder":
            lines.append(f"- [文件夹] {item['name']}/ · 修改于 {item['modified_at']}")
        else:
            lines.append(
                f"- {item['name']} · {_human_size(int(item['size']))} · "
                f"修改于 {item['modified_at']} · file_id={item['file_id']}"
            )
    scope = result["path"] or "工作区根目录"
    result["summary"] = (
        f"{scope} 下共 {result['total']} 项：\n" + "\n".join(lines)
        if lines
        else f"{scope} 为空"
    )
    result["hint"] = "可将文件项的 file_id 直接交给 workspace_read_file 读取或分析。"
    return result


async def _search_workspace_files(
    arguments: dict[str, Any],
    user_id: str | None = None,
    context: ToolInvocationContext | None = None,
) -> dict[str, Any]:
    """按文件名模糊搜索当前用户工作区的统一文件索引。"""
    from omichub.application.services.file_service import FileService
    from omichub.infrastructure.database.session import get_session_factory

    uid = uuid.UUID(user_id) if user_id else None
    if uid is None:
        return {"error": "无法识别当前用户"}
    query = str(arguments.get("query") or "").strip()
    try:
        limit = max(1, min(int(arguments.get("limit", 50)), 50))
    except (TypeError, ValueError):
        limit = 50

    if context is not None:
        listing = await FileService(context.db).search_files(uid, query=query, limit=limit)
    else:
        factory = get_session_factory()
        async with factory() as db:
            listing = await FileService(db).search_files(uid, query=query, limit=limit)

    items = [
        {
            "file_id": str(file.id),
            "name": file.original_name,
            "relative_path": file.path,
            "modified_at": file.modified_at.isoformat(),
        }
        for file in listing.items
    ]
    lines = [
        f"- {item['name']} · {item['relative_path']} · 修改于 {item['modified_at']} · "
        f"file_id={item['file_id']}"
        for item in items
    ]
    return {
        "query": query,
        "items": items,
        "total": len(items),
        "summary": (
            f"找到 {len(items)} 个匹配文件：\n" + "\n".join(lines)
            if lines
            else f"未找到名称包含“{query}”的文件"
        ),
        "hint": "可将匹配项的 file_id 直接交给 workspace_read_file 读取或分析。",
    }


async def _find_session_uploads(
    arguments: dict[str, Any],
    user_id: str | None = None,
    context: ToolInvocationContext | None = None,
) -> dict[str, Any]:
    """按会话 ID 检索该聊天窗口中上传过的文件。

    聊天上传文件名内嵌会话短标记（``.s{session_id前8位}``），本工具按标记
    在 chat-uploads 目录中匹配；session_id 缺省时取当前调用上下文中的会话 ID。
    """
    from omichub.infrastructure.config.storage_config import get_user_chat_upload_dir

    session_id = str(arguments.get("session_id") or "").strip()
    if not session_id and context is not None:
        session_id = (context.session_id or "").strip()
    short = session_id[:8]
    if not short:
        return {"error": "缺少 session_id，且当前调用上下文无会话信息"}
    if not user_id:
        return {"error": "无法识别当前用户"}

    upload_dir = get_user_chat_upload_dir(user_id)
    marker = f".s{short}"
    items: list[dict[str, Any]] = []
    if upload_dir.is_dir():
        for path in sorted(upload_dir.iterdir()):
            if not path.is_file() or marker not in path.name:
                continue
            fid = path.name.split(".", 1)[0]
            stat = path.stat()
            items.append(
                {
                    "file_id": fid,
                    "ref": f"upload://{fid}",
                    "name": path.name,
                    "size": stat.st_size,
                    "size_human": _human_size(stat.st_size),
                    "session_id": session_id,
                }
            )
    lines = [f"- {item['name']} · {item['size_human']} · file_id={item['ref']}" for item in items]
    if not items:
        # 跨会话兜底：本（或指定）会话没有标记上传时，列出该用户最近上传的文件，
        # 覆盖"上一个聊天窗口上传的数据在新窗口要继续用"的场景；
        # 老文件（无会话标记）也能在这里被找回。
        try:
            recent = sorted(
                (p for p in upload_dir.iterdir() if p.is_file()),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )[:10]
        except OSError:
            recent = []
        for path in recent:
            fid = path.name.split(".", 1)[0]
            stat = path.stat()
            items.append(
                {
                    "file_id": fid,
                    "ref": f"upload://{fid}",
                    "name": path.name,
                    "size": stat.st_size,
                    "size_human": _human_size(stat.st_size),
                    "session_id": None,
                }
            )
        if items:
            lines = [f"- {item['name']} · {item['size_human']} · file_id={item['ref']}" for item in items]
            return {
                "session_id": session_id,
                "items": items,
                "total": len(items),
                "fallback": "recent_uploads",
                "summary": (
                    f"会话 {session_id} 下没有检索到上传文件；"
                    f"以下是您最近上传的 {len(items)} 个文件（含其它会话）：\n" + "\n".join(lines)
                ),
                "hint": "可将 file_id（upload://…）直接交给 workspace_read_file 读取或分析。",
            }
    return {
        "session_id": session_id,
        "items": items,
        "total": len(items),
        "summary": (
            f"会话 {session_id} 上传过 {len(items)} 个文件：\n" + "\n".join(lines)
            if items
            else f"会话 {session_id} 下没有检索到上传文件，也没有可回溯的历史上传"
        ),
        "hint": "可将 file_id（upload://…）直接交给 workspace_read_file 读取或分析。",
    }


async def _workspace_get_file_info(
    arguments: dict[str, Any], user_id: str | None = None, **_kw: Any
) -> dict[str, Any]:
    """返回工作区文件的元数据（不读内容）。"""
    from omichub.infrastructure.database.session import get_session_factory

    file_id = arguments.get("file_id", "")
    if not user_id:
        return {"error": "无法识别当前用户"}
    factory = get_session_factory()
    async with factory() as db:
        target, meta = await _resolve_workspace_file(user_id, file_id, db)
    if target is None:
        return meta
    meta["exists"] = target.is_file()
    meta["is_text"] = _is_text_file(meta["name"])
    meta["summary"] = (
        f"{meta['name']}（{meta['size_human']}，{meta['file_type']}，"
        f"{'文本' if meta['is_text'] else '二进制'}）"
    )
    return meta


async def _workspace_read_file(
    arguments: dict[str, Any], user_id: str | None = None, **_kw: Any
) -> dict[str, Any]:
    """读取工作区文本文件内容预览。

    - 文本类：返回前 max_bytes（默认 100KB）内容，超出截断并标注；
    - 二进制类（BAM/CRAM/FASTQ 等）：只返回元数据，不读内容，引导走分析流程。
    """
    from omichub.infrastructure.database.session import get_session_factory

    file_id = arguments.get("file_id", "")
    try:
        max_bytes = int(arguments.get("max_bytes", _DEFAULT_READ_MAX_BYTES))
    except (TypeError, ValueError):
        max_bytes = _DEFAULT_READ_MAX_BYTES
    max_bytes = max(1, min(max_bytes, 1024 * 1024))  # 上限 1MB，防撑爆上下文

    if not user_id:
        return {"error": "无法识别当前用户"}
    factory = get_session_factory()
    async with factory() as db:
        target, meta = await _resolve_workspace_file(user_id, file_id, db)
    if target is None:
        return meta
    if not target.is_file():
        return {"error": "文件已被移除", **meta}

    name = meta["name"]
    # 二进制 / 测序原始数据：只回元数据
    if not _is_text_file(name) or name.lower().endswith(tuple(_BINARY_ONLY_SUFFIXES)):
        meta["content"] = None
        meta["truncated"] = False
        meta["summary"] = (
            f"{name} 为二进制/测序数据（{meta['size_human']}），不直接读取内容。"
            "请使用相应分析流程处理，或用 workspace_get_file_info 查看元数据。"
        )
        return meta

    size = target.stat().st_size
    truncated = size > max_bytes
    try:
        with open(target, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read(max_bytes)
    except OSError as e:
        return {"error": f"读取失败: {e}", **meta}

    meta["content"] = content
    meta["truncated"] = truncated
    meta["summary"] = (
        f"文件 {name}（{meta['size_human']}）内容预览"
        + (f"，已截断至前 {max_bytes} 字节" if truncated else "")
    )
    return meta


PLATFORM_PRESET_TOOLS = [
    {
        "name": "platform_list_tasks",
        "description": "列出用户的分析任务（状态、进度）",
        "inputSchema": {
            "type": "object",
            "properties": {"status": {"type": "string", "description": "过滤状态"}},
        },
    },
    {
        "name": "platform_get_task",
        "description": "获取任务详情（状态、进度、工作目录、错误）",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        },
    },
    {
        "name": "platform_list_flows",
        "description": "列出可用的分析流程",
        "inputSchema": {
            "type": "object",
            "properties": {"category": {"type": "string"}},
        },
    },
    {
        "name": "platform_sandbox_execute",
        "description": "在沙箱中执行代码（mambaforge 环境，预装 scanpy/Seurat 等）",
        "inputSchema": {
            "type": "object",
            "properties": {"code": {"type": "string", "description": "Python 代码"}},
            "required": ["code"],
        },
    },
    {
        "name": "platform_read_file",
        "description": "读取用户目录下分析结果文件（前 N 行）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "相对路径"},
                "max_lines": {"type": "integer", "default": 50},
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "list_workspace_files",
        "description": (
            "列出当前会话用户工作区指定目录的直接子项，返回 file_id、名称、文件/文件夹类型、"
            "大小、相对路径和修改时间。用户询问工作区有什么文件时必须调用。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "工作区内相对目录，留空表示根目录；禁止绝对路径和 ..",
                },
                "pattern": {
                    "type": "string",
                    "description": "可选 glob 过滤，如 *.csv、sample_*.fastq.gz",
                },
            },
        },
    },
    {
        "name": "search_workspace_files",
        "description": (
            "从当前会话用户工作区根目录递归按文件名模糊搜索，返回 file_id、名称、相对路径和修改时间。"
            "用户要求寻找某个数据文件时必须调用。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "文件名搜索词"},
                "limit": {
                    "type": "integer",
                    "default": 50,
                    "minimum": 1,
                    "maximum": 50,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "workspace_list_files",
        "description": (
            "兼容旧版名称；列出当前用户工作区某目录下的文件与子目录。"
            "新调用优先使用 list_workspace_files。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "相对目录路径，空串=工作区根目录（如 raw_data、results、enrichment）",
                },
                "pattern": {"type": "string", "description": "可选 glob 过滤，如 *.csv"},
            },
        },
    },
    {
        "name": "workspace_read_file",
        "description": (
            "按 file_id 读取工作区文本文件内容预览（默认前 100KB，超出截断）；"
            "二进制/测序文件（BAM/CRAM/FASTQ 等）只返回元数据。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_id": {
                    "type": "string",
                    "description": "文件 ID，形如 file://{uuid} 或 upload://{hex}（来自列表或 @ 引用）",
                },
                "max_bytes": {"type": "integer", "default": 102400, "description": "最多读取字节数"},
            },
            "required": ["file_id"],
        },
    },
    {
        "name": "find_session_uploads",
        "description": (
            "按会话 ID 检索该聊天窗口中用户上传过的文件（聊天上传文件名内嵌会话标记）。"
            "session_id 留空时默认使用当前会话。需要找回本会话之前上传的数据文件时调用。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "聊天会话 ID（UUID），留空表示当前会话",
                },
            },
        },
    },
    {
        "name": "workspace_get_file_info",
        "description": "按 file_id 返回工作区文件的元数据（名称、大小、类型、目录、创建时间），不读内容。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_id": {
                    "type": "string",
                    "description": "文件 ID，形如 file://{uuid} 或 upload://{hex}",
                },
            },
            "required": ["file_id"],
        },
    },
]

PLATFORM_HANDLERS = {
    "platform_list_tasks": _platform_list_tasks,
    "platform_get_task": _platform_get_task,
    "platform_list_flows": _platform_list_flows,
    "platform_sandbox_execute": _platform_sandbox_execute,
    "platform_read_file": _platform_read_file,
    "list_workspace_files": _list_workspace_files,
    "search_workspace_files": _search_workspace_files,
    "workspace_list_files": _workspace_list_files,
    "workspace_read_file": _workspace_read_file,
    "workspace_get_file_info": _workspace_get_file_info,
    "find_session_uploads": _find_session_uploads,
}


# 预设服务定义
PRESET_SERVERS: list[dict[str, Any]] = [
    {
        "name": "omichub-platform",
        "description": "平台操作 MCP - 任务管理、流程查询、沙箱执行、结果读取",
        "transport": "builtin",
        "tools": PLATFORM_PRESET_TOOLS,
        "handlers": PLATFORM_HANDLERS,
    },
    build_pipeline_preset(),
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
    if name == OMICHUB_PIPELINES_SERVER_NAME:
        return build_pipeline_preset()
    for p in PRESET_SERVERS:
        if p["name"] == name:
            return p
    return None


__all__ = [
    "PRESET_SERVERS",
    "OMICHUB_TOOLS_SERVER_ID",
    "OMICHUB_TOOLS_SERVER_NAME",
    "OMICHUB_PLATFORM_SERVER_ID",
    "WORKSPACE_FILES_SYSTEM_PROMPT_SUFFIX",
    "OMICHUB_PIPELINES_SERVER_ID",
    "OMICHUB_PIPELINES_SERVER_NAME",
    "PLATFORM_PRESET_TOOLS",
    "PLATFORM_HANDLERS",
    "get_preset_by_name",
    "_build_omichub_tools_preset",
]

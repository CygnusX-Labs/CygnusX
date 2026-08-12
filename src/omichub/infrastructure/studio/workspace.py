"""OmicStudio 工作区宿主磁盘直读 —— 沙盒容器未运行时的回退路径。

工作区经 bind-mount 同时挂在宿主与容器 /workspace，两侧内容天然一致；
容器停止时 Studio API 直接读宿主目录，返回与 sandbox-agent /files/* 同构的 payload，
路径一律经 paths 守卫，与容器内规则一致。

P1 数据不搬家：input/ 下软链指向容器内平台只读挂载 /data/platform/<用户相对路径>
（宿主侧表现为悬空软链，属预期）；读路径经 resolve_workspace_read_path 翻译到
宿主 {storage_path}/users/{user_id} 下读取，写路径仍严格限工作区内。
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path
from typing import Any

from omichub.core.exceptions import BusinessError, NotFoundError
from omichub.infrastructure.studio.paths import (
    PLATFORM_CONTAINER_MOUNT,
    PathEscapeError,
    relative_workspace_path,
    resolve_workspace_path,
    resolve_workspace_read_path,
)

DEFAULT_READ_LIMIT = 200  # 与 sandbox-agent 一致的分页默认行数
MAX_READ_LIMIT = 2000
OUTPUT_DIR = "output"  # 产物约定目录（相对工作区根）
INPUT_DIR = "input"  # 平台数据软链目录（相对工作区根）


def _file_meta(p: Path) -> dict[str, Any]:
    st = p.stat()
    return {
        "name": p.name,
        "type": "dir" if p.is_dir() else "file",
        "size": st.st_size,
        "mtime": st.st_mtime,
    }


def disk_list_files(
    workspace: Path, path: str = "", platform_host_root: Path | None = None
) -> dict[str, Any]:
    """目录列表（相对工作区根），返回 {path, entries:[{name,type,size,mtime}]}。

    platform_host_root 传入 {storage_path}/users/{user_id} 时，input/ 软链指向的
    平台数据目录也可列出（只读语义）。
    """
    resolved = resolve_workspace_read_path(path or ".", root=workspace, platform_host_root=platform_host_root)
    target = resolved.path
    if not target.exists():
        raise NotFoundError(f"路径不存在: {path}")
    if not target.is_dir():
        raise BusinessError(f"不是目录: {path}")
    entries = [_file_meta(p) for p in sorted(target.iterdir(), key=lambda x: x.name)]
    # 平台挂载内路径无法相对工作区表达，回显用户输入路径
    display = path if resolved.via_platform else relative_workspace_path(target, workspace)
    return {"path": display, "entries": entries}


def disk_read_file(
    workspace: Path,
    path: str,
    offset: int = 0,
    limit: int = DEFAULT_READ_LIMIT,
    platform_host_root: Path | None = None,
) -> dict[str, Any]:
    """分页读取文本文件，返回 {content, total_lines, truncated}（默认前 200 行）。"""
    target = resolve_workspace_read_path(
        path, root=workspace, platform_host_root=platform_host_root
    ).path
    if not target.is_file():
        raise NotFoundError(f"文件不存在: {path}")
    try:
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        raise BusinessError(f"读取失败: {e}") from e
    limit = min(limit, MAX_READ_LIMIT)
    total = len(lines)
    page = lines[offset : offset + limit]
    return {
        "content": "\n".join(page),
        "total_lines": total,
        "truncated": offset + limit < total,
    }


def disk_list_artifacts(workspace: Path) -> list[dict[str, Any]]:
    """递归扫描 output/ 产物目录，返回 [{path, size, mtime}]（path 相对工作区根）。"""
    out_dir = resolve_workspace_path(OUTPUT_DIR, root=workspace)
    artifacts: list[dict[str, Any]] = []
    if not out_dir.is_dir():
        return artifacts
    for p in sorted(out_dir.rglob("*")):
        if not p.is_file():
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        artifacts.append(
            {"path": relative_workspace_path(p, workspace), "size": st.st_size, "mtime": st.st_mtime}
        )
    return artifacts


def resolve_artifact_path(workspace: Path, path: str) -> Path:
    """把产物路径（相对工作区根，如 output/plot.png）解析为绝对路径（下载用）。

    先按工作区规则归一化，再强制落在 output/ 产物目录内，越界抛 PathEscapeError。
    """
    resolved = resolve_workspace_path(path, root=workspace)
    out_dir = resolve_workspace_path(OUTPUT_DIR, root=workspace)
    if resolved != out_dir and out_dir not in resolved.parents:
        raise PathEscapeError(f"路径越出产物目录: {path}")
    return resolved


# ===== 平台数据软链（数据不搬家，P1） =====


def platform_user_rel(storage_rel: str, user_id: str) -> str:
    """把相对平台存储根的路径（users/{uid}/raw/x.csv）折算为平台挂载内相对路径。

    沙盒只挂载当前用户目录 {storage_path}/users/{user_id} 到 /data/platform（多租户
    隔离红线：绝不可整根挂载，否则沙盒内代码可读全部用户数据），故软链目标必须
    先剥掉 users/{user_id}/ 前缀；不在该用户目录下的路径一律拒绝。
    """
    rel = Path(storage_rel)
    if rel.is_absolute() or ".." in rel.parts:
        raise PathEscapeError(f"非法平台存储路径: {storage_rel}")
    prefix = Path("users") / user_id
    parts = rel.parts
    if len(parts) <= len(prefix.parts) or parts[: len(prefix.parts)] != prefix.parts:
        raise PathEscapeError(f"平台路径不属于当前用户: {storage_rel}")
    return Path(*parts[len(prefix.parts) :]).as_posix()


def link_platform_file(
    workspace: Path,
    mount_rel: str,
    display_name: str | None = None,
    *,
    idempotent: bool = False,
) -> str:
    """在 workspace/input 下创建指向平台只读挂载的软链，返回链接名。

    - mount_rel：平台挂载（/data/platform）内相对路径，即 platform_user_rel 的结果；
    - 软链目标为容器内路径 /data/platform/<mount_rel>，宿主侧通常显示为悬空软链，
      属预期（宿主读取经 resolve_workspace_read_path 翻译，容器内经只读挂载直读）；
    - 重名自动加 " (2)" 后缀；链接名强制取 basename，防路径注入；
    - idempotent=True 时，若 input/ 下已有指向同一平台路径的软链则直接复用其名，
      避免同一文件在多轮对话中被重复引入生成 "name (2)/(3)" 冗余链接。默认 False
      以保持 datahub_import 等既有工具的原始去重语义，仅聊天附件自动挂载链路启用。
    """
    input_dir = workspace / INPUT_DIR
    input_dir.mkdir(parents=True, exist_ok=True)
    target = f"{PLATFORM_CONTAINER_MOUNT}/{mount_rel}"
    if idempotent:
        # 宿主侧软链悬空，必须用 lexists + readlink 按目标比对，不能靠 exists
        for entry in sorted(input_dir.iterdir(), key=lambda p: p.name):
            if not os.path.islink(entry):
                continue
            with contextlib.suppress(OSError):
                if os.readlink(entry) == target:
                    return entry.name
    name = Path(display_name or Path(mount_rel).name).name
    if not name:
        raise BusinessError("链接名不能为空")
    candidate = name
    n = 1
    stem, suffix = os.path.splitext(name)
    # 注意用 lexists：宿主侧软链悬空，exists 会漏判已有链接
    while os.path.lexists(input_dir / candidate):
        n += 1
        candidate = f"{stem} ({n}){suffix}"
    (input_dir / candidate).symlink_to(target)
    return candidate


def link_platform_directory(
    workspace: Path,
    mount_rel: str,
    display_name: str | None = None,
    *,
    idempotent: bool = False,
) -> str:
    """Create a controlled read-only directory reference under ``workspace/input``.

    The link points at the same per-user ``/data/platform`` mount as file references;
    it never copies source data and session cleanup therefore only removes the link.
    """
    return link_platform_file(
        workspace,
        mount_rel,
        display_name,
        idempotent=idempotent,
    )


def list_input_links(workspace: Path) -> list[str]:
    """列出 input/ 下已引入的平台数据链接名（含宿主侧悬空的软链）。"""
    input_dir = workspace / INPUT_DIR
    if not input_dir.is_dir():
        return []
    return sorted(os.listdir(input_dir))

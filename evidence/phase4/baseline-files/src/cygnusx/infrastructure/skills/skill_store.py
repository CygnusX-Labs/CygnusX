"""技能库磁盘存储 —— data/ai/skills/<skill_id>/ 标准文件夹

DB 行 = 技能索引（L1 元数据 + L2 正文缓存 prompt 列）；
磁盘文件夹 = 技能内容真相源（L3 references/scripts/assets 按需读取）。
"""

from __future__ import annotations

import shutil
from pathlib import Path

from cygnusx.core.config import get_settings
from cygnusx.infrastructure.skills.skillmd import (
    ParsedSkill,
    SkillParseError,
    render_skill_md,
    split_frontmatter,
)

# L3 资源单文件读取上限（超过则拒绝回灌上下文）
MAX_RESOURCE_READ_BYTES = 200 * 1024


def skills_root() -> Path:
    return Path(get_settings().skills_dir)


def skill_roots() -> tuple[Path, ...]:
    """返回统一只读 Skill 根目录，首目录仍是平台写入真相源。"""
    configured = skills_root()
    candidates = (
        configured,
        Path("data/ai/skill_marketplace"),
        Path(".agents/skills"),
    )
    roots: list[Path] = []
    seen: set[Path] = set()
    for root in candidates:
        resolved = root.resolve()
        if resolved not in seen:
            roots.append(resolved)
            seen.add(resolved)
    return tuple(roots)


def _safe_skill_dir(skill_id: str) -> Path:
    """skill_id → 目录，拒绝路径穿越"""
    if not skill_id or "/" in skill_id or "\\" in skill_id or ".." in skill_id:
        raise ValueError(f"非法 skill_id: {skill_id!r}")
    root = skills_root()
    return (root / skill_id).resolve()


def _read_skill_dir(skill_id: str) -> Path | None:
    """按注册顺序查找 Skill，读取方不感知其物理目录。"""
    if not skill_id or "/" in skill_id or "\\" in skill_id or ".." in skill_id:
        return None
    for root in skill_roots():
        target = (root / skill_id).resolve()
        if target.is_dir() and (target / "SKILL.md").is_file():
            return target
    return None


def list_skill_metadata() -> list[dict[str, object]]:
    """扫描所有已注册根目录的 frontmatter，不读取正文。"""
    entries: list[dict[str, object]] = []
    seen: set[str] = set()
    for root in skill_roots():
        if not root.is_dir():
            continue
        for skill_md in root.rglob("SKILL.md"):
            try:
                relative = skill_md.parent.relative_to(root)
                skill_id = "--".join(relative.parts)
                meta, _ = split_frontmatter(skill_md.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, SkillParseError, ValueError):
                continue
            if not skill_id or skill_id in seen:
                continue
            seen.add(skill_id)
            tags = meta.get("task_tags") or meta.get("tags") or []
            entrypoints = meta.get("entrypoints") or []
            entries.append(
                {
                    "skill_id": skill_id,
                    "name": str(meta.get("name") or skill_id),
                    "description": str(meta.get("description") or ""),
                    "category": str(meta.get("category") or "general"),
                    "frontmatter": {"task_tags": tags, "entrypoints": entrypoints},
                    "version": meta.get("version"),
                    "source": "disk",
                }
            )
    return entries


def write_skill_folder(parsed: ParsedSkill) -> Path:
    """将解析结果落盘为标准技能文件夹（覆盖写）"""
    target = _safe_skill_dir(parsed.skill_id)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=False)

    # SKILL.md 正文 + frontmatter
    (target / "SKILL.md").write_text(render_skill_md(parsed), encoding="utf-8")

    for entry in parsed.files:
        if entry.kind == "skill_md":
            continue
        rel = Path(entry.path)
        if rel.is_absolute() or ".." in rel.parts:
            continue
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if entry.content is not None:
            dest.write_text(entry.content, encoding="utf-8")
        # 二进制（content=None）不随预览传输，落盘时跳过——导入源保留原始副本
    return target


def rewrite_skill_md(parsed: ParsedSkill) -> bool:
    """仅重写已存在技能文件夹内的 SKILL.md（保留 scripts/references/assets）。

    供 DB 内容变更（更新/回滚）后同步磁盘用；文件夹不存在时跳过返回 False。
    """
    try:
        target = _safe_skill_dir(parsed.skill_id)
    except ValueError:
        return False
    if not target.is_dir():
        return False
    (target / "SKILL.md").write_text(render_skill_md(parsed), encoding="utf-8")
    return True


def read_skill_body(skill_id: str) -> str | None:
    """L2：读取技能 SKILL.md 正文（frontmatter 已剥离）"""
    try:
        target = _read_skill_dir(skill_id)
    except ValueError:
        return None
    if target is None:
        return None
    skill_md = target / "SKILL.md"
    if not skill_md.is_file():
        return None
    from cygnusx.infrastructure.skills.skillmd import SkillParseError, split_frontmatter

    try:
        _, body = split_frontmatter(skill_md.read_text(encoding="utf-8"))
        return body
    except (SkillParseError, UnicodeDecodeError):
        # 文件损坏时回退读全文，保证 use_skill 不空手而归
        try:
            return skill_md.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            return None


def read_skill_resource(skill_id: str, rel_path: str) -> tuple[bool, str, bytes | None]:
    """L3：按需读取技能文件夹内的资源文件。

    返回 (ok, message, content)。content 为原始字节，由调用方决定文本/base64。
    仅限 references/ 与 assets/ 目录（scripts 不进上下文——代码只执行不阅读）。
    """
    try:
        base = _read_skill_dir(skill_id)
    except ValueError as exc:
        return False, str(exc), None
    if base is None:
        return False, f"技能不存在: {skill_id}", None

    rel = rel_path.replace("\\", "/").lstrip("/")
    parts = rel.split("/")
    if not rel or ".." in parts:
        return False, "非法资源路径", None
    if parts[0] not in ("references", "assets"):
        return (
            False,
            "仅允许读取 references/ 与 assets/ 下的资源；脚本请用代码执行能力运行",
            None,
        )
    target = (base / rel).resolve()
    if not str(target).startswith(str(base)):
        return False, "资源路径越界", None
    if not target.is_file():
        return False, f"资源不存在: {rel}", None
    if target.stat().st_size > MAX_RESOURCE_READ_BYTES:
        return False, f"资源超过 {MAX_RESOURCE_READ_BYTES // 1024}KB 读取上限", None
    try:
        return True, "ok", target.read_bytes()
    except OSError as exc:
        return False, f"读取失败: {exc}", None


def list_skill_files(skill_id: str) -> list[str]:
    """列出技能文件夹内相对路径（L2 正文末尾的资源目录提示用）"""
    try:
        base = _read_skill_dir(skill_id)
    except ValueError:
        return []
    if base is None or not base.is_dir():
        return []
    return sorted(
        str(p.relative_to(base)).replace("\\", "/")
        for p in base.rglob("*")
        if p.is_file() and p.name != "SKILL.md"
    )


def remove_skill_folder(skill_id: str) -> None:
    try:
        target = _safe_skill_dir(skill_id)
    except ValueError:
        return
    if target.is_dir():
        shutil.rmtree(target, ignore_errors=True)

"""技能导入应用服务 —— 四入口统一"先解析预览、确认后入库"

入口：技能市场（仓库内置）/ GitHub 仓库或子目录 URL / 本地 zip 上传 / JSON 粘贴（兼容）。
解析产出 SkillImportPreviewDTO；确认后写 data/ai/skills/<skill_id>/ 文件夹 + skills 表。
"""

from __future__ import annotations

import io
import json
import re
import tarfile
import uuid
import zipfile
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omichub.application.schemas.skill import (
    SkillDTO,
    SkillImportPreviewDTO,
    SkillMarketplaceItemDTO,
    SkillUpdateCheckDTO,
)
from omichub.core.config import get_settings
from omichub.core.exceptions import BusinessError, NotFoundError
from omichub.infrastructure.database.models.skill import SkillModel
from omichub.infrastructure.skills.skillmd import (
    ParsedSkill,
    SkillParseError,
    parse_skill_folder,
    parsed_from_legacy_json,
)
from omichub.infrastructure.skills.skill_store import remove_skill_folder, write_skill_folder

# zip 解压总量护栏（防 zip bomb 打爆内存；技能包本身上限 1MiB）
MAX_ZIP_TOTAL_BYTES = 4 * 1024 * 1024
GITHUB_API = "https://api.github.com"
GITHUB_HEADERS = {"User-Agent": "OmicHub-SkillImporter", "Accept": "application/vnd.github+json"}
HTTP_TIMEOUT = 30.0


class SkillImportService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ---------- 解析入口（均产出预览，不落库） ----------

    async def parse_from_json(self, text: str) -> SkillImportPreviewDTO:
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SkillParseError(f"JSON 解析失败: {exc}") from exc
        if not isinstance(obj, dict):
            raise SkillParseError("JSON 配置必须是对象")
        parsed = parsed_from_legacy_json(obj)
        parsed.source_type = "json"
        return self._preview(parsed, source_type="json")

    async def parse_from_zip(self, data: bytes) -> SkillImportPreviewDTO:
        files: dict[str, bytes] = {}
        total = 0
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for info in zf.infolist():
                    name = info.filename
                    if info.is_dir() or name.startswith("/") or ".." in name.split("/"):
                        continue
                    total += info.file_size
                    if total > MAX_ZIP_TOTAL_BYTES:
                        raise SkillParseError("zip 解压后总量超过 4MB 上限")
                    files[name] = zf.read(info)
        except zipfile.BadZipFile as exc:
            raise SkillParseError("不是有效的 zip 文件") from exc
        parsed = parse_skill_folder(files, source_type="zip")
        return self._preview(parsed, source_type="zip")

    async def parse_from_github(self, url: str) -> SkillImportPreviewDTO:
        files, source_ref, source_commit = await self._fetch_github(url.strip())
        parsed = parse_skill_folder(files, source_type="github", source_ref=source_ref)
        return self._preview(
            parsed, source_type="github", source_ref=source_ref, source_commit=source_commit
        )

    # ---------- 市场 ----------

    async def list_marketplace(self) -> list[SkillMarketplaceItemDTO]:
        market_dir = Path(get_settings().skill_marketplace_dir)
        items: list[SkillMarketplaceItemDTO] = []
        if market_dir.is_dir():
            for folder in sorted(market_dir.iterdir()):
                skill_md = folder / "SKILL.md"
                if not folder.is_dir() or not skill_md.is_file():
                    continue
                try:
                    parsed = self._read_folder(folder)
                except SkillParseError:
                    continue
                items.append(
                    SkillMarketplaceItemDTO(
                        # 市场以文件夹名为安装键（frontmatter 无显式 skill_id 时
                        # 派生 ID 可能是中文名，与文件夹名不一致）
                        skill_id=folder.name,
                        name=parsed.name,
                        description=parsed.description,
                        icon=parsed.icon,
                        category=parsed.category,
                        version=parsed.version,
                        author=parsed.author,
                        has_scripts=parsed.has_scripts,
                        installed=await self._exists(folder.name),
                    )
                )
        return items

    async def install_marketplace(self, skill_id: str, overwrite: bool = False) -> SkillDTO:
        market_dir = Path(get_settings().skill_marketplace_dir)
        folder = (market_dir / skill_id).resolve()
        if (
            not str(folder).startswith(str(market_dir.resolve()))
            or not (folder / "SKILL.md").is_file()
        ):
            raise NotFoundError(f"市场技能 '{skill_id}' 不存在")
        parsed = self._read_folder(folder)
        preview = self._preview(
            parsed, source_type="market", source_ref=f"builtin://{skill_id}"
        )
        preview.skill_id = skill_id  # 文件夹名为规范键，保证 DB/磁盘/市场三处一致
        return await self.confirm_import(preview, overwrite=overwrite)

    # ---------- 确认入库 ----------

    async def confirm_import(
        self, preview: SkillImportPreviewDTO, overwrite: bool = False
    ) -> SkillDTO:
        parsed = ParsedSkill.from_preview_dict(preview.model_dump())
        existing = await self._get_model(parsed.skill_id)
        if existing and not overwrite:
            raise BusinessError(
                f"技能 '{parsed.skill_id}' 已存在（可开启覆盖导入以升级到新版本）"
            )

        write_skill_folder(parsed)

        if existing:
            existing.name = parsed.name
            existing.description = parsed.description
            existing.prompt = parsed.body
            existing.icon = parsed.icon
            existing.category = parsed.category
            existing.version = parsed.version or None
            existing.author = parsed.author or None
            existing.source_type = preview.source_type
            existing.source_ref = preview.source_ref or None
            existing.source_commit = preview.source_commit or None
            existing.has_scripts = parsed.has_scripts
            existing.frontmatter = parsed.frontmatter or None
            model = existing
        else:
            model = SkillModel(
                id=uuid.uuid4(),
                skill_id=parsed.skill_id,
                name=parsed.name,
                description=parsed.description,
                prompt=parsed.body,
                icon=parsed.icon,
                category=parsed.category,
                is_active=True,
                is_builtin=False,
                version=parsed.version or None,
                author=parsed.author or None,
                source_type=preview.source_type,
                source_ref=preview.source_ref or None,
                source_commit=preview.source_commit or None,
                has_scripts=parsed.has_scripts,
                frontmatter=parsed.frontmatter or None,
            )
            self._db.add(model)
        await self._db.flush()
        from omichub.application.services.skill_service import SkillService, _snapshot_skill

        # 版本留档：覆盖升级为 import 快照；新装技能不经 create_skill，也在此留首版
        await _snapshot_skill(
            self._db,
            model,
            source="import",
            changelog="导入覆盖升级" if existing else "导入技能",
        )
        await self._db.flush()
        return SkillService._to_dto(model)

    async def delete_skill_folder(self, skill_id: str) -> None:
        """删除技能时同步清理磁盘文件夹（由 SkillService.delete_skill 调用）"""
        remove_skill_folder(skill_id)

    # ---------- 检查更新 ----------

    async def check_update(self, skill_id: str) -> SkillUpdateCheckDTO:
        model = await self._get_model(skill_id)
        if model is None:
            raise NotFoundError(f"技能 '{skill_id}' 不存在")
        current_commit = model.source_commit or ""
        if model.source_type != "github" or not model.source_ref:
            return SkillUpdateCheckDTO(
                has_update=False,
                current_version=model.version or "",
                current_commit=current_commit,
                source_ref=model.source_ref or "",
                message="该技能来源不支持自动检查更新",
            )
        info = _parse_github_url(model.source_ref)
        if info is None:
            return SkillUpdateCheckDTO(
                has_update=False,
                current_version=model.version or "",
                current_commit=current_commit,
                source_ref=model.source_ref or "",
                message="无法解析来源 URL",
            )
        owner, repo, branch, _sub = info
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=GITHUB_HEADERS) as client:
                resp = await client.get(
                    f"{GITHUB_API}/repos/{owner}/{repo}/commits",
                    params={"sha": branch or "HEAD", "per_page": 1},
                )
                resp.raise_for_status()
                latest = (resp.json() or [{}])[0].get("sha", "")
        except httpx.HTTPError as exc:
            raise BusinessError(f"查询上游更新失败: {exc}") from exc
        has_update = bool(latest) and bool(current_commit) and latest != current_commit
        return SkillUpdateCheckDTO(
            has_update=has_update,
            current_version=model.version or "",
            current_commit=current_commit,
            latest_commit=latest[:12],
            source_ref=model.source_ref,
            message="发现上游新提交，可重新导入升级" if has_update else "已是最新",
        )

    # ---------- 内部工具 ----------

    def _preview(
        self,
        parsed: ParsedSkill,
        *,
        source_type: str,
        source_ref: str = "",
        source_commit: str = "",
    ) -> SkillImportPreviewDTO:
        data = parsed.to_preview_dict()
        return SkillImportPreviewDTO(
            **{k: v for k, v in data.items() if k != "source_type"},
            source_type=source_type,
            source_ref=source_ref,
            source_commit=source_commit,
        )

    async def _exists(self, skill_id: str) -> bool:
        return await self._get_model(skill_id) is not None

    async def _get_model(self, skill_id: str) -> SkillModel | None:
        result = await self._db.execute(
            select(SkillModel).where(SkillModel.skill_id == skill_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _read_folder(folder: Path) -> ParsedSkill:
        files: dict[str, bytes] = {}
        total = 0
        base = folder.resolve()
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            rel = str(path.relative_to(base)).replace("\\", "/")
            size = path.stat().st_size
            total += size
            if total > MAX_ZIP_TOTAL_BYTES:
                raise SkillParseError("技能文件夹超过 4MB 上限")
            files[rel] = path.read_bytes()
        return parse_skill_folder(files)

    async def _fetch_github(
        self, url: str
    ) -> tuple[dict[str, bytes], str, str]:
        """拉取 GitHub 技能文件夹。返回 (files, source_ref, source_commit)"""
        info = _parse_github_url(url)
        if info is None:
            raise SkillParseError(
                "无法识别的 GitHub 链接，支持：仓库主页 / tree 分支或子目录 / blob 指向 SKILL.md / raw 文件"
            )
        owner, repo, branch, subpath = info
        source_ref = f"https://github.com/{owner}/{repo}"

        # 单文件：blob/raw 直指 SKILL.md
        if subpath and subpath.lower().endswith("skill.md"):
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{subpath}"
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=GITHUB_HEADERS) as client:
                resp = await client.get(raw_url)
                if resp.status_code == 404:
                    raise SkillParseError(f"文件不存在: {raw_url}")
                resp.raise_for_status()
                content = resp.content
            commit = await self._latest_commit(owner, repo, branch)
            return {"SKILL.md": content}, source_ref, commit

        # 文件夹：codeload tar.gz 整仓解压后按子路径过滤
        use_branch = branch or await self._default_branch(owner, repo)
        tar_url = f"https://codeload.github.com/{owner}/{repo}/tar.gz/refs/heads/{use_branch}"
        async with httpx.AsyncClient(timeout=60.0, headers=GITHUB_HEADERS) as client:
            resp = await client.get(tar_url)
            if resp.status_code == 404:
                raise SkillParseError(f"仓库或分支不存在: {owner}/{repo}@{use_branch}")
            resp.raise_for_status()
            blob = resp.content

        files = _extract_tar_subdir(blob, subpath)
        if not files:
            where = f"{subpath}/" if subpath else "仓库根目录"
            raise SkillParseError(f"{where} 下未找到技能文件（需包含 SKILL.md）")
        commit = await self._latest_commit(owner, repo, use_branch)
        if subpath:
            source_ref = f"{source_ref}/tree/{use_branch}/{subpath}"
        return files, source_ref, commit

    @staticmethod
    async def _default_branch(owner: str, repo: str) -> str:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=GITHUB_HEADERS) as client:
            resp = await client.get(f"{GITHUB_API}/repos/{owner}/{repo}")
            if resp.status_code == 404:
                raise SkillParseError(f"仓库不存在: {owner}/{repo}")
            resp.raise_for_status()
            return str(resp.json().get("default_branch") or "main")

    @staticmethod
    async def _latest_commit(owner: str, repo: str, branch: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=GITHUB_HEADERS) as client:
                resp = await client.get(
                    f"{GITHUB_API}/repos/{owner}/{repo}/commits",
                    params={"sha": branch or "HEAD", "per_page": 1},
                )
                resp.raise_for_status()
                data = resp.json()
                return str((data or [{}])[0].get("sha", ""))[:12]
        except httpx.HTTPError:
            return ""


_GITHUB_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)"
    r"(?:\.git)?(?:/(?P<kind>tree|blob)/(?P<branch>[^/\s]+)(?P<sub>/[^\s]*)?)?/?$",
    re.IGNORECASE,
)
_RAW_URL_RE = re.compile(
    r"^(?:https?://)?raw\.githubusercontent\.com/(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+)"
    r"/(?P<branch>[^/\s]+)(?P<sub>/[^\s]+)$",
    re.IGNORECASE,
)


def _parse_github_url(url: str) -> tuple[str, str, str, str] | None:
    """→ (owner, repo, branch, subpath)，branch/subpath 可能为空串"""
    url = url.strip().rstrip("/")
    m = _RAW_URL_RE.match(url)
    if m:
        return m["owner"], m["repo"], m["branch"], m["sub"].lstrip("/")
    m = _GITHUB_URL_RE.match(url + ("/" if url.endswith(".git") else ""))
    if not m:
        return None
    kind = (m["kind"] or "").lower()
    branch = m["branch"] or ""
    sub = (m["sub"] or "").strip("/")
    if kind == "" and (branch or sub):
        return None
    return m["owner"], m["repo"], branch, sub


def _extract_tar_subdir(blob: bytes, subpath: str) -> dict[str, bytes]:
    """从 codeload tar.gz 中提取 {repo}-{branch}/[subpath]/ 下的文件"""
    files: dict[str, bytes] = {}
    total = 0
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        root_prefix = ""
        for member in tar.getmembers():
            if not member.isfile():
                continue
            name = member.name
            if ".." in name.split("/") or name.startswith("/"):
                continue
            if not root_prefix:
                root_prefix = name.split("/", 1)[0] + "/"
            rel = name[len(root_prefix):] if name.startswith(root_prefix) else name
            if subpath:
                if not rel.startswith(f"{subpath}/"):
                    continue
                rel = rel[len(subpath) + 1:]
            if not rel:
                continue
            total += member.size
            if total > MAX_ZIP_TOTAL_BYTES:
                raise SkillParseError("仓库目标目录超过 4MB 上限")
            extracted = tar.extractfile(member)
            if extracted is not None:
                files[rel] = extracted.read()
    return files

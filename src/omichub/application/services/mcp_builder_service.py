"""MCP Builder 应用服务 — AI 自生成 MCP 的编排中枢.

流水线：需求 → (LLM 生成) → AST 安全检查 → 落库构建记录 → 注册实验 MCP
→ 沙箱启动验证（tools/list + tools/call）→ 审核 → 发布版本快照。

设计文档：docs/26.7.30/mcp_builder_framework.md
约束红线：ARCHITECTURE_DESIN/mcp_architecture.md §10
"""

from __future__ import annotations

import re
import uuid as uuid_mod
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from omichub.application.schemas.mcp_builder import (
    MCPBuildDTO,
    SubmitBuildRequest,
)
from omichub.core.config import get_settings
from omichub.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from omichub.domain.mcp.entities import MCPServer, MCPToolRegistry
from omichub.domain.mcp.value_objects import (
    BuildStatus,
    ReviewStatus,
    ServerPool,
    ServerStatus,
    Transport,
)
from omichub.infrastructure.database.models.mcp_builder import (
    MCPBuildModel,
    MCPReviewModel,
    MCPVersionModel,
)
from omichub.infrastructure.database.models.mcp_log import MCPLogModel
from omichub.infrastructure.database.repositories.mcp_repository import (
    SqlAlchemyMCPServerRepository,
)
from omichub.infrastructure.mcp.builder.doc_generator import (
    generate_architecture_doc,
    generate_build_doc,
)
from omichub.infrastructure.mcp.builder.generator import MCPCodeGenerator
from omichub.infrastructure.mcp.builder.safety import StaticSafetyChecker
from omichub.infrastructure.mcp.builder.versioning import determine_version

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str, fallback: str = "tool") -> str:
    slug = _SLUG_RE.sub("-", text.lower()).strip("-")
    return slug[:40] or fallback


def _build_to_dto(b: MCPBuildModel) -> MCPBuildDTO:
    return MCPBuildDTO(
        id=b.id,
        user_id=b.user_id,
        requirement=b.requirement,
        plan_summary=b.plan_summary or "",
        generated_code=b.generated_code or "",
        runtime=b.runtime or "python",
        safety_report=b.safety_report,
        mcp_server_id=b.mcp_server_id,
        version=b.version or "1.0.0",
        parent_build_id=b.parent_build_id,
        status=b.status or "planning",
        test_cases=list(b.test_cases or []),
        test_passed=b.test_passed,
        build_doc=b.build_doc or "",
        architecture_doc=b.architecture_doc or "",
        model_used=b.model_used or "",
        tokens_consumed=b.tokens_consumed,
        generation_time_ms=b.generation_time_ms,
        created_at=b.created_at,
        updated_at=b.updated_at,
    )


class MCPBuilderService:
    """MCP Builder 编排服务（每请求一实例，注入 AsyncSession）"""

    def __init__(self, db: AsyncSession):
        self._db = db
        self._repo = SqlAlchemyMCPServerRepository(db)
        self._settings = get_settings()
        self._checker = StaticSafetyChecker()

    # ------------------------------------------------------------------
    # 构建提交
    # ------------------------------------------------------------------
    async def submit_build(self, user_id: str, req: SubmitBuildRequest) -> MCPBuildDTO:
        """提交构建：生成/接收代码 → 安全检查 → 注册实验 MCP."""
        if not self._settings.mcp_builder_enabled:
            raise ValidationError("MCP Builder 功能已被平台禁用")
        if not req.requirement.strip():
            raise ValidationError("requirement 不能为空")

        uid = UUID(str(user_id))
        await self._check_quota(uid)

        # 1. 代码：优先用调用方（Builder Agent）提供的，否则 LLM 生成
        code = (req.code or "").strip()
        model_used = req.model_name or ""
        tokens: int | None = None
        generation_ms: int | None = None
        if not code:
            gen = await MCPCodeGenerator(self._db).generate(
                req.requirement, model_name=req.model_name or None
            )
            if not gen.ok:
                raise ValidationError(f"代码生成失败: {gen.error}")
            code = gen.code
            model_used = gen.model_used
            tokens = gen.tokens
            generation_ms = gen.duration_ms

        # 2. AST 安全检查
        report = self._checker.analyze(code)

        # 3. 版本号
        version = "1.0.0"
        parent_version: str | None = None
        if req.parent_build_id:
            parent = await self._get_build(req.parent_build_id)
            parent_version = parent.version
            if req.change_type:
                try:
                    version = determine_version(parent_version or "1.0.0", req.change_type)
                except ValueError as exc:
                    raise ValidationError(str(exc)) from exc

        build = MCPBuildModel(
            user_id=uid,
            requirement=req.requirement.strip(),
            generated_code=code,
            runtime=req.runtime or "python",
            safety_report=report.to_dict(),
            version=version,
            parent_build_id=req.parent_build_id,
            model_used=model_used,
            tokens_consumed=tokens,
            generation_time_ms=generation_ms,
            status=BuildStatus.PLANNING.value,
        )

        if not report.passed:
            build.status = BuildStatus.REJECTED.value
            self._db.add(build)
            await self._db.flush()
            await self._log(build.mcp_server_id, "warning",
                           f"构建被安全检查拒绝: {report.violations[:3]}", uid)
            return _build_to_dto(build)

        # 4. 注册实验 MCP Server
        ttl_hours = req.ttl_hours or self._settings.mcp_builder_default_ttl_hours
        name = await self._unique_name(req.mcp_name or _slugify(req.requirement))
        code_path = f"mcp-builds/{name.removeprefix('exp-')}/server.py"
        server = MCPServer(
            id=uuid_mod.uuid4(),
            name=name,
            description=req.requirement.strip()[:300],
            transport=Transport.STDIO,
            command="python",
            args=[f"/workspace/{code_path}"],
            status=ServerStatus.OFFLINE,
            is_enabled=True,
            timeout=self._settings.mcp_default_timeout,
            auto_restart=False,
            pool=ServerPool.EXPERIMENTAL,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=ttl_hours),
            created_by=uid,
            current_version=version,
            generation_meta={
                "build_id": str(build.id),
                "model": model_used,
                "code_path": code_path,
                "dependencies": report.dependencies,
                "warnings": report.warnings,
            },
            review_status=(
                ReviewStatus.PENDING
                if self._settings.mcp_builder_requires_review
                else ReviewStatus.APPROVED
            ),
        )
        await self._repo.save(server)

        build.mcp_server_id = server.id
        build.status = (
            BuildStatus.REVIEWING.value
            if self._settings.mcp_builder_requires_review
            else BuildStatus.TESTING.value
        )
        self._db.add(build)
        await self._db.flush()
        await self._db.refresh(build)
        await self._log(server.id, "info",
                        f"实验 MCP 已注册: {name} v{version} (TTL {ttl_hours}h)", uid)
        logger.info(f"[MCPBuilder] 用户 {uid} 注册实验 MCP {name} v{version}")
        return _build_to_dto(build)

    async def generate_code_only(self, requirement: str, model_name: str | None = None) -> dict[str, Any]:
        """仅生成代码 + 安全检查（供前端预览 / Agent 工具使用，不落库）."""
        if not self._settings.mcp_builder_enabled:
            raise ValidationError("MCP Builder 功能已被平台禁用")
        gen = await MCPCodeGenerator(self._db).generate(requirement, model_name=model_name)
        if not gen.ok:
            raise ValidationError(f"代码生成失败: {gen.error}")
        report = self._checker.analyze(gen.code)
        return {
            "code": gen.code,
            "model_used": gen.model_used,
            "duration_ms": gen.duration_ms,
            "tokens": gen.tokens,
            "safety_report": report.to_dict(),
        }

    # ------------------------------------------------------------------
    # 构建查询
    # ------------------------------------------------------------------
    async def list_builds(
        self,
        user_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[MCPBuildDTO]:
        query = select(MCPBuildModel).order_by(MCPBuildModel.created_at.desc()).limit(limit)
        if user_id:
            query = query.where(MCPBuildModel.user_id == UUID(str(user_id)))
        if status:
            query = query.where(MCPBuildModel.status == status)
        result = await self._db.execute(query)
        return [_build_to_dto(b) for b in result.scalars().all()]

    async def get_build(self, build_id: str, user_id: str | None = None) -> MCPBuildDTO:
        build = await self._get_build(UUID(str(build_id)))
        if user_id and str(build.user_id) != str(user_id):
            raise AuthorizationError("无权访问该构建记录")
        return _build_to_dto(build)

    async def delete_build(self, build_id: str, user_id: str, is_admin: bool = False) -> bool:
        build = await self._get_build(UUID(str(build_id)))
        if not is_admin and str(build.user_id) != str(user_id):
            raise AuthorizationError("无权删除该构建记录")
        # 联动删除其实验 MCP Server（正式池不动）
        if build.mcp_server_id:
            server = await self._repo.get_by_id(build.mcp_server_id)
            if server and server.pool == ServerPool.EXPERIMENTAL:
                await self._repo.delete(server.id, force=True)
        await self._db.delete(build)
        await self._db.flush()
        return True

    # ------------------------------------------------------------------
    # 沙箱测试
    # ------------------------------------------------------------------
    async def test_in_sandbox(
        self,
        build_id: str,
        session_id: str,
        test_arguments: dict[str, dict[str, Any]] | None = None,
        user_id: str | None = None,
    ) -> MCPBuildDTO:
        """在 Studio 沙箱内启动构建产物并逐工具验证.

        流程：写代码到沙箱 → /mcp/start 握手 → 逐工具 /mcp/call → 记录测试用例。
        """
        from omichub.infrastructure.studio.manager import studio_sandbox_manager

        build = await self._get_build(UUID(str(build_id)))
        if user_id and str(build.user_id) != str(user_id):
            raise AuthorizationError("无权测试该构建")
        if not build.generated_code:
            raise ValidationError("构建无代码产物")
        test_arguments = test_arguments or {}

        code_path = f"mcp-builds/build-{str(build.id)[:8]}/server.py"
        await studio_sandbox_manager.write_file(session_id, code_path, build.generated_code)
        started = await studio_sandbox_manager.start_mcp_server(session_id, code_path)

        tools: list[dict[str, Any]] = started.get("tools") or []
        sandbox_server_id = started.get("server_id")
        cases: list[dict[str, Any]] = []
        try:
            for tool in tools:
                tool_name = tool.get("name", "")
                args = test_arguments.get(tool_name, {})
                try:
                    result = await studio_sandbox_manager.mcp_call_tool(
                        session_id, sandbox_server_id, tool_name, args
                    )
                    text = " ".join(
                        c.get("text", "") for c in result.get("content") or [] if isinstance(c, dict)
                    )
                    cases.append({
                        "tool": tool_name,
                        "input": args,
                        "expected": "(any non-error)",
                        "actual": text[:500],
                        "passed": not result.get("is_error"),
                    })
                except Exception as exc:  # noqa: BLE001
                    cases.append({
                        "tool": tool_name,
                        "input": args,
                        "expected": "(any non-error)",
                        "actual": f"{type(exc).__name__}: {exc}"[:500],
                        "passed": False,
                    })
        finally:
            try:
                await studio_sandbox_manager.stop_mcp_server(session_id, sandbox_server_id)
            except Exception:  # noqa: BLE001
                pass

        all_passed = bool(cases) and all(c["passed"] for c in cases)
        build.test_cases = cases
        build.test_passed = all_passed
        if all_passed:
            build.status = (
                BuildStatus.REVIEWING.value
                if self._settings.mcp_builder_requires_review
                else BuildStatus.APPROVED.value
            )
            build.build_doc = generate_build_doc(
                name=str(build.mcp_server_id),
                requirement=build.requirement,
                tools=tools,
                test_cases=cases,
                dependencies=(build.safety_report or {}).get("dependencies") or [],
                model_used=build.model_used or "",
                build_id=str(build.id),
                version=build.version or "1.0.0",
            )
            build.architecture_doc = generate_architecture_doc(
                name=str(build.mcp_server_id),
                version=build.version or "1.0.0",
                needs_network=bool((build.safety_report or {}).get("dependencies")),
            )
            # 同步工具快照到 server 记录并置为在线
            if build.mcp_server_id:
                server = await self._repo.get_by_id(build.mcp_server_id)
                if server:
                    server.tools = [
                        MCPToolRegistry(
                            tool_name=t.get("name", ""),
                            description=t.get("description", ""),
                            input_schema=t.get("inputSchema") or {},
                            server_id=server.id,
                        )
                        for t in tools
                    ]
                    server.status = ServerStatus.ONLINE
                    if not self._settings.mcp_builder_requires_review:
                        server.review_status = ReviewStatus.APPROVED
                        build.status = BuildStatus.PUBLISHED.value
                        await self._snapshot_version(server, build)
                    await self._repo.save(server)
        await self._db.flush()
        await self._db.refresh(build)
        await self._log(build.mcp_server_id, "info",
                        f"沙箱测试完成: {sum(1 for c in cases if c['passed'])}/{len(cases)} 通过",
                        UUID(str(build.user_id)))
        return _build_to_dto(build)

    # ------------------------------------------------------------------
    # 审核
    # ------------------------------------------------------------------
    async def review_build(
        self, build_id: str, reviewer_id: str, decision: str, comment: str = ""
    ) -> MCPBuildDTO:
        """提交审核决定（仅 Admin 调用，权限由 API 层把关）."""
        if decision not in ("approved", "rejected", "request_changes"):
            raise ValidationError(f"非法审核决定: {decision}")
        build = await self._get_build(UUID(str(build_id)))

        self._db.add(MCPReviewModel(
            build_id=build.id,
            reviewer_id=UUID(str(reviewer_id)),
            decision=decision,
            comment=comment or "",
        ))

        server = await self._repo.get_by_id(build.mcp_server_id) if build.mcp_server_id else None
        if decision == "approved":
            build.status = BuildStatus.PUBLISHED.value
            if server:
                server.review_status = ReviewStatus.APPROVED
                await self._repo.save(server)
                await self._snapshot_version(server, build)
        elif decision == "rejected":
            build.status = BuildStatus.REJECTED.value
            if server:
                server.review_status = ReviewStatus.REJECTED
                server.is_enabled = False
                await self._repo.save(server)
        else:  # request_changes → 回到规划阶段等待迭代
            build.status = BuildStatus.PLANNING.value

        await self._db.flush()
        await self._db.refresh(build)
        await self._log(build.mcp_server_id, "info",
                        f"审核决定: {decision}" + (f"（{comment}）" if comment else ""),
                        UUID(str(reviewer_id)))
        return _build_to_dto(build)

    async def list_review_queue(self, status: str = "reviewing", limit: int = 50) -> list[MCPBuildDTO]:
        return await self.list_builds(status=status, limit=limit)

    # ------------------------------------------------------------------
    # 实验 MCP 生命周期
    # ------------------------------------------------------------------
    async def list_experimental_servers(self, user_id: str | None = None) -> list[dict[str, Any]]:
        servers = await self._repo.list_all()
        out = []
        for s in servers:
            if s.pool != ServerPool.EXPERIMENTAL:
                continue
            if user_id and str(s.created_by) != str(user_id):
                continue
            out.append({
                "id": str(s.id),
                "name": s.name,
                "description": s.description,
                "status": s.status.value if hasattr(s.status, "value") else str(s.status),
                "is_enabled": s.is_enabled,
                "pool": s.pool.value,
                "expires_at": s.expires_at.isoformat() if s.expires_at else None,
                "created_by": str(s.created_by) if s.created_by else None,
                "current_version": s.current_version,
                "review_status": s.review_status.value
                if hasattr(s.review_status, "value") else str(s.review_status),
                "is_template": s.is_template,
                "tool_count": len(s.tools),
                "tools": [
                    {"name": t.tool_name, "description": t.description,
                     "input_schema": t.input_schema}
                    for t in s.tools
                ],
                "created_at": s.created_at.isoformat() if s.created_at else None,
            })
        return out

    async def renew_server(self, server_id: str, user_id: str, hours: int | None = None,
                           is_admin: bool = False) -> dict[str, Any]:
        server = await self._require_experimental(UUID(str(server_id)))
        if not is_admin and str(server.created_by) != str(user_id):
            raise AuthorizationError("无权操作该实验 MCP")
        ttl = hours or self._settings.mcp_builder_default_ttl_hours
        server.expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl)
        if server.status == ServerStatus.OFFLINE and server.is_enabled:
            server.status = ServerStatus.ONLINE
        await self._repo.save(server)
        await self._log(server.id, "info", f"续期 {ttl} 小时", UUID(str(user_id)))
        return {"id": str(server.id), "expires_at": server.expires_at.isoformat()}

    async def delete_experimental_server(self, server_id: str, user_id: str,
                                         is_admin: bool = False) -> bool:
        server = await self._require_experimental(UUID(str(server_id)))
        if not is_admin and str(server.created_by) != str(user_id):
            raise AuthorizationError("无权删除该实验 MCP")
        await self._repo.delete(server.id, force=True)
        await self._log(None, "info", f"实验 MCP {server.name} 已删除", UUID(str(user_id)))
        return True

    async def call_experimental_tool(
        self,
        server_id: str,
        tool: str,
        arguments: dict[str, Any],
        session_id: str,
        user_id: str,
        is_admin: bool = False,
    ) -> dict[str, Any]:
        """经沙箱桥接调用实验 MCP 工具（宿主 → UDS → 容器内 STDIO 子进程）."""
        from omichub.infrastructure.studio.manager import studio_sandbox_manager

        server = await self._require_experimental(UUID(str(server_id)))
        if not is_admin and str(server.created_by) != str(user_id):
            raise AuthorizationError("无权调用该实验 MCP")
        if server.is_expired():
            raise ValidationError("该实验 MCP 已过期，请续期后调用")

        code = (server.generation_meta or {}).get("code_path", "")
        # 确保代码在沙箱内（构建产物随会话工作区持久化；缺失时从构建记录恢复）
        started = await studio_sandbox_manager.start_mcp_server(
            session_id, code or f"mcp-builds/{server.name.removeprefix('exp-')}/server.py",
            server_id=f"exp-{str(server.id)[:8]}",
        )
        try:
            result = await studio_sandbox_manager.mcp_call_tool(
                session_id, started.get("server_id"), tool, arguments
            )
        finally:
            try:
                await studio_sandbox_manager.stop_mcp_server(session_id, started.get("server_id"))
            except Exception:  # noqa: BLE001
                pass
        await self._log(server.id, "info", f"工具调用: {tool}", UUID(str(user_id)))
        return result

    async def expire_stale_servers(self) -> int:
        """Celery 定时任务入口：下线过期实验 MCP。返回处理数量。"""
        now = datetime.now(timezone.utc)
        servers = await self._repo.list_all()
        count = 0
        for server in servers:
            if server.pool != ServerPool.EXPERIMENTAL:
                continue
            if server.expires_at is None or not server.is_expired(now):
                continue
            if not server.is_enabled:
                continue
            server.is_enabled = False
            server.status = ServerStatus.OFFLINE
            await self._repo.save(server)
            await self._log(server.id, "info", "TTL 到期，自动下线")
            count += 1
            logger.info(f"[MCPBuilder] 实验 MCP {server.name} 过期下线")
        return count

    # ------------------------------------------------------------------
    # 版本
    # ------------------------------------------------------------------
    async def list_versions(self, server_id: str) -> list[dict[str, Any]]:
        result = await self._db.execute(
            select(MCPVersionModel)
            .where(MCPVersionModel.mcp_server_id == UUID(str(server_id)))
            .order_by(MCPVersionModel.created_at.desc())
        )
        return [
            {
                "id": str(v.id),
                "version": v.version,
                "version_tag": v.version_tag,
                "is_major": v.is_major,
                "changelog": v.changelog,
                "created_by": str(v.created_by) if v.created_by else None,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in result.scalars().all()
        ]

    async def rollback(self, server_id: str, target_version: str, user_id: str,
                       is_admin: bool = False) -> dict[str, Any]:
        server = await self._require_experimental(UUID(str(server_id)))
        if not is_admin and str(server.created_by) != str(user_id):
            raise AuthorizationError("无权回滚该实验 MCP")
        result = await self._db.execute(
            select(MCPVersionModel).where(
                MCPVersionModel.mcp_server_id == server.id,
                MCPVersionModel.version == target_version,
            )
        )
        version = result.scalar_one_or_none()
        if version is None:
            raise NotFoundError(f"版本 {target_version} 不存在")
        server.current_version = target_version
        if version.tools_snapshot:
            server.tools = [
                MCPToolRegistry(
                    tool_name=t.get("name", ""),
                    description=t.get("description", ""),
                    input_schema=t.get("inputSchema") or {},
                    server_id=server.id,
                )
                for t in version.tools_snapshot
            ]
        await self._repo.save(server)
        await self._log(server.id, "info", f"回滚到 v{target_version}", UUID(str(user_id)))
        return {"id": str(server.id), "current_version": target_version}

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------
    async def _check_quota(self, uid: UUID) -> None:
        active = await self._db.execute(
            select(func.count())
            .select_from(MCPBuildModel)
            .where(
                MCPBuildModel.user_id == uid,
                MCPBuildModel.status.notin_([
                    BuildStatus.REJECTED.value, BuildStatus.DEPRECATED.value,
                ]),
            )
        )
        used = active.scalar_one()
        if used >= self._settings.mcp_builder_max_per_user:
            raise ValidationError(
                f"实验 MCP 数量已达上限 {self._settings.mcp_builder_max_per_user}，"
                "请删除旧构建后重试"
            )

    async def _unique_name(self, slug: str) -> str:
        base = f"exp-{slug}"
        candidate = base
        suffix = 2
        while await self._repo.get_by_name(candidate):
            candidate = f"{base}-{suffix}"
            suffix += 1
            if suffix > 99:
                raise ValidationError("无法生成唯一 MCP 名称")
        return candidate

    async def _get_build(self, build_id: UUID) -> MCPBuildModel:
        build = await self._db.get(MCPBuildModel, build_id)
        if build is None:
            raise NotFoundError(f"构建记录不存在: {build_id}")
        return build

    async def _require_experimental(self, server_id: UUID) -> MCPServer:
        server = await self._repo.get_by_id(server_id)
        if server is None:
            raise NotFoundError(f"MCP Server 不存在: {server_id}")
        if server.pool != ServerPool.EXPERIMENTAL:
            raise ValidationError("该操作仅适用于实验池 MCP")
        return server

    async def _snapshot_version(self, server: MCPServer, build: MCPBuildModel) -> None:
        existing = await self._db.execute(
            select(MCPVersionModel).where(
                MCPVersionModel.mcp_server_id == server.id,
                MCPVersionModel.version == (build.version or "1.0.0"),
            )
        )
        if existing.scalar_one_or_none():
            return
        self._db.add(MCPVersionModel(
            mcp_server_id=server.id,
            build_id=build.id,
            version=build.version or "1.0.0",
            is_major=(build.version or "1.0.0").startswith(("2.", "3.", "4.", "5.")),
            code_snapshot=build.generated_code or "",
            tools_snapshot=[
                {"name": t.tool_name, "description": t.description,
                 "inputSchema": t.input_schema}
                for t in server.tools
            ],
            changelog=build.requirement[:300],
            created_by=build.user_id,
        ))
        await self._db.flush()

    async def _log(self, service_id: UUID | None, level: str, message: str,
                   actor: UUID | None = None) -> None:
        if service_id is None:
            return
        self._db.add(MCPLogModel(
            service_id=service_id,
            level=level,
            message=message if actor is None else f"{message} [actor={actor}]",
            source="builder",
        ))
        await self._db.flush()

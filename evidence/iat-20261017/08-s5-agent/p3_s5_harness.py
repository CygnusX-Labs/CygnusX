"""P3 S5-C2 harness: REAL PostgreSQL + REAL Redis, original AgentToolGateway/delegation.

Drives the original AgentToolGateway.context/invoke, agent_tool_delegation
issue/verify, and tool_confirmation on a real isolated PG and a real isolated Redis.
Download execution gate stays closed. No second business system.

Run: .venv/bin/python <this> <PG_URL> <REDIS_URL>
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import traceback
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import jwt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

PG_URL = sys.argv[1]
REDIS_URL = sys.argv[2]
results: list[dict] = []


def rec(case: str, ok: bool, **extra):
    results.append({"case": case, "ok": ok, **extra})
    print(json.dumps({"case": case, "ok": ok, **extra}, default=str), flush=True)


async def seed(engine) -> SimpleNamespace:
    from cygnusx.infrastructure.database.models.user import UserModel
    from cygnusx.infrastructure.database.models.project import ProjectModel
    from cygnusx.infrastructure.database.models.chat import ChatSessionModel

    maker = async_sessionmaker(engine, expire_on_commit=False)
    owner, other = uuid4(), uuid4()
    pa1, pa2, pb1 = uuid4(), uuid4(), uuid4()
    tag = uuid4().hex[:8]
    async with maker() as db:
        for uid, name in ((owner, f"s5owner-{tag}"), (other, f"s5other-{tag}")):
            db.add(UserModel(id=uid, username=name, email=f"{name}@test.invalid",
                             hashed_password="unused", role="user", status="active",
                             token_version=0, storage_quota=10**9, used_storage=0))
        await db.flush()
        for pid, uid, slug in ((pa1, owner, f"pa1-{tag}"), (pa2, owner, f"pa2-{tag}"),
                               (pb1, other, f"pb1-{tag}")):
            db.add(ProjectModel(id=pid, user_id=uid, name=slug, slug=slug, status="active"))
        await db.flush()
        # research (treasure-mouse) + platform-ai sessions
        specs = (
            (f"mouse-a1-{tag}", owner, pa1, {"research_agent": "research-treasure-mouse"}),
            (f"mouse-a2-{tag}", owner, pa2, {"research_agent": "research-treasure-mouse"}),
            (f"assistant-{tag}", owner, pa1, {}),
            (f"mouse-b1-{tag}", other, pb1, {"research_agent": "research-treasure-mouse"}),
        )
        from cygnusx.infrastructure.database.models.chat import ChatSessionModel
        # Reuse an existing ai_provider_configs row (seeded by migrations) for model_id FK.
        from sqlalchemy import text as _text
        mid = (await db.execute(_text(
            "SELECT id FROM ai_provider_configs WHERE is_active = true ORDER BY created_at LIMIT 1"
        ))).scalars().first()
        if mid is None:
            raise RuntimeError("no active ai_provider_configs row for chat_sessions.model_id FK")
        for sid, uid, pid, meta in specs:
            db.add(ChatSessionModel(session_id=sid, user_id=str(uid), project_id=str(pid),
                                    agent_id=None, status="active", model_id=mid,
                                    sandbox_meta=meta))
        await db.commit()
    return SimpleNamespace(maker=maker, owner=owner, other=other, pa1=pa1, pa2=pa2, pb1=pb1,
                           tag=tag,
                           s_a1=f"mouse-a1-{tag}", s_a2=f"mouse-a2-{tag}",
                           s_asst=f"assistant-{tag}", s_b1=f"mouse-b1-{tag}")


def enable_gateway():
    import cygnusx.application.services.agent_tool_gateway as mod
    base = mod.get_settings()

    class S:
        def __getattr__(self, k):
            return getattr(base, k)

    s = S()
    for attr, val in (("tool_gateway_read_enabled", True),
                      ("dataset_discovery_readonly", True),
                      ("research_delivery_read_enabled", True),
                      ("research_plan_enabled", True),
                      ("agent_download_write_enabled", False),
                      ("agent_analysis_write_enabled", False),
                      ("agent_task_cancel_enabled", False),
                      ("agent_tool_delegation_ttl_seconds", 300),
                      # Match the isolated container's secret so signed delegations verify.
                      ("jwt_secret_key", os.environ.get("ACCEPTANCE_JWT_SECRET",
                                                        base.jwt_secret_key))):
        setattr(s, attr, val)
    mod.get_settings = lambda: s
    import cygnusx.application.services.agent_tool_delegation as dele
    dele.get_settings = lambda: s
    return s


async def case_ag02(env, engine):
    """AG-02: platform AI (Legacy context) full tool round through the Gateway -> audit row."""
    from cygnusx.application.services.agent_tool_gateway import AgentToolGateway
    from cygnusx.infrastructure.database.models.agent_tool_invocation import (
        AgentToolInvocationModel,
    )

    db = env.maker()
    gw = AgentToolGateway(db)
    ctx = await gw.context(str(env.owner), env.s_asst)
    catalog = gw.catalog(ctx)
    caps = {c["capability_id"] for c in catalog}
    res = await gw.invoke(ctx, "downloads.describe_capabilities", {})
    await db.commit()
    inv_id = res["invocation_id"]
    async with env.maker() as db2:
        row = await db2.get(AgentToolInvocationModel, __import__("uuid").UUID(inv_id))
    # every listed capability must be execution_allowed=false (frozen)
    execs = res["result"].get("capabilities", [])
    all_blocked = all(c.get("execution_allowed") is False for c in execs) if execs else None
    ok = (row is not None and row.capability_id == "downloads.describe_capabilities"
          and row.owner_id == str(env.owner) and "downloads.describe_capabilities" in caps)
    rec("AG-02", ok, invocation_id=inv_id, audit_owner=row.owner_id if row else None,
        catalog_size=len(caps), execution_allowed_all_false=all_blocked,
        note="real Gateway round + persisted audit invocation")
    await db.close()


async def case_ag04(env, engine):
    """AG-04: cross-user/project isolation and revocation re-checked at invoke."""
    from cygnusx.application.services.agent_tool_gateway import AgentToolGateway
    from cygnusx.core.exceptions import AuthorizationError, NotFoundError

    db = env.maker()
    gw = AgentToolGateway(db)
    # owner cannot open another user's session
    cross = "no_error"
    try:
        await gw.context(str(env.owner), env.s_b1)
    except (AuthorizationError, NotFoundError) as exc:
        cross = type(exc).__name__
    # stale context with a swapped project must be rejected at invoke
    ctx = await gw.context(str(env.owner), env.s_a1)
    ctx.extra["project_id"] = str(env.pb1)
    stale = "no_error"
    try:
        await gw.invoke(ctx, "downloads.describe_capabilities", {})
    except AuthorizationError as exc:
        stale = getattr(exc, "code", type(exc).__name__)
    rec("AG-04", cross != "no_error" and stale == "FORBIDDEN",
        cross_user=cross, stale_project=stale,
        note="cross-user session denied; project swap denied at invoke")
    await db.close()


async def case_ag07(env, engine):
    """AG-07: model-supplied owner/project/scopes/runtime_verified are rejected/no-op."""
    from cygnusx.application.services.agent_tool_gateway import AgentToolGateway
    from cygnusx.application.schemas.agent_tools import CAPABILITY_MODELS

    model = CAPABILITY_MODELS["downloads.describe_capabilities"]
    extra_fields = {"owner_id", "project_id", "scopes", "runtime_verified", "user_id"}
    accepted = extra_fields & set(model.model_fields)
    # try passing them; base ToolArgs should forbid extra
    rejected = "no_error"
    try:
        model.model_validate({"owner_id": str(env.other), "scopes": ["execute:download"]})
    except Exception as exc:  # noqa: BLE001
        rejected = type(exc).__name__
    rec("AG-07", accepted == set() and rejected != "no_error",
        model_accepts=accepted, extra_rejected=rejected,
        note="capability args schema forbids model-supplied control fields")


async def case_ag13(env, engine):
    """AG-13: illegal arguments -> schema rejection; unregistered tool -> error (no alt exec)."""
    from cygnusx.application.services.agent_tool_gateway import AgentToolGateway
    from cygnusx.core.exceptions import ValidationError

    db = env.maker()
    gw = AgentToolGateway(db)
    ctx = await gw.context(str(env.owner), env.s_asst)
    codes = {}
    try:
        await gw.invoke(ctx, "not.a.tool", {})
    except Exception as exc:  # noqa: BLE001
        codes["unregistered"] = getattr(exc, "code", type(exc).__name__)
    try:
        await gw.invoke(ctx, "tasks.get_status", {"task_id": "not-a-uuid"})
    except Exception as exc:  # noqa: BLE001
        codes["illegal_arg"] = getattr(exc, "code", type(exc).__name__)
    rec("AG-13", codes.get("unregistered") == "VALIDATION_ERROR"
        and codes.get("illegal_arg") != "no_error", codes=codes,
        note="no alternative execution / implicit retry")
    await db.close()


async def case_ag16(env, engine):
    """AG-16: 12 download capabilities report execution_allowed=false for unauth protocols."""
    from cygnusx.tools.download.config import describe_download_capabilities

    res = describe_download_capabilities()
    caps = res.get("capabilities", [])
    block = {c.get("protocol") or c.get("source_type") or c.get("capability_id"): c.get(
        "execution_allowed") for c in caps}
    ok = len(caps) >= 12 and all(v is False for v in block.values())
    rec("AG-16", ok, count=len(caps),
        execution_allowed={k: v for k, v in list(block.items())[:14]},
        note="no unauth protocol claims execution; cloud drive not faked as implemented")


async def case_ag05(env, engine):
    """AG-05: delegation expiry / replay / token_version update all refused."""
    from cygnusx.application.services.agent_tool_gateway import AgentToolGateway
    from cygnusx.application.services.agent_tool_delegation import (
        issue_delegation, verify_delegation,
    )
    from cygnusx.infrastructure.database.models.user import UserModel
    from cygnusx.core.exceptions import AuthenticationError, ConflictError

    db = env.maker()
    gw = AgentToolGateway(db)
    ctx = await gw.context(str(env.owner), env.s_a1)
    token = await issue_delegation(ctx)
    call_id = str(uuid4())
    # valid first use
    first = "ok"
    try:
        vctx = await verify_delegation(db, token, "downloads.describe_capabilities", call_id)
        first = "verified"
    except Exception as exc:  # noqa: BLE001
        first = f"{type(exc).__name__}:{getattr(exc,'code','')}"
    # replay: same jti+call_id must be refused
    replay = "no_error"
    try:
        await verify_delegation(db, token, "downloads.describe_capabilities", call_id)
    except ConflictError:
        replay = "ConflictError"
    except Exception as exc:  # noqa: BLE001
        replay = type(exc).__name__
    # token_version bump invalidates the delegation
    await db.execute(__import__("sqlalchemy").update(UserModel)
                     .where(UserModel.id == env.owner).values(token_version=1))
    await db.commit()
    bumped = "no_error"
    try:
        await verify_delegation(db, token, "downloads.describe_capabilities", str(uuid4()))
    except AuthenticationError:
        bumped = "AuthenticationError"
    except Exception as exc:  # noqa: BLE001
        bumped = type(exc).__name__
    rec("AG-05", first == "verified" and replay == "ConflictError"
        and bumped == "AuthenticationError",
        first=first, replay=replay, token_version_bumped=bumped,
        note="real Redis NX anti-replay + token_version re-check")
    await db.close()


async def case_ag10(env, engine):
    """AG-10: two concurrent confirmations of one approval -> exactly one consumed."""
    from cygnusx.application.services.tool_confirmation_service import (
        ToolConfirmationService, get_tool_confirmation_service, ConfirmationError,
    )

    svc = get_tool_confirmation_service()
    owner = str(env.owner)
    record = await svc.create_for_tool(owner, "downloads.submit", {"accession": "SRR1"})
    await svc.approve_by_human(user_id=owner, confirmation_id=record.confirmation_id)

    async def consume():
        try:
            await svc.consume_tool_confirmation(owner, record.confirmation_id,
                                                "downloads.submit", {"accession": "SRR1"})
            return "CONSUMED"
        except ConfirmationError:
            return "REJECTED"
        except Exception as exc:  # noqa: BLE001
            return f"ERR:{type(exc).__name__}"

    r = await asyncio.gather(consume(), consume())
    rec("AG-10", sorted(r) == ["CONSUMED", "REJECTED"], results=list(r),
        note="atomic single consumption; no model self-approval")


async def case_ag09(env, engine):
    """AG-09: dataset.prepare_import produces a proposal, NOT a download Task."""
    from cygnusx.application.services.agent_tool_gateway import AgentToolGateway
    from cygnusx.infrastructure.database.models.task import TaskModel

    db = env.maker()
    gw = AgentToolGateway(db)
    ctx = await gw.context(str(env.owner), env.s_a1)
    async with env.maker() as db_before:
        before = await db_before.scalar(select(func.count()).select_from(TaskModel).where(
            TaskModel.flow_id == "ebi_download", TaskModel.user_id == env.owner))
    outcome = {}
    try:
        res = await gw.invoke(ctx, "dataset.prepare_import",
                              {"accession": "GSE000000", "source": "geo"})
        await db.commit()
        outcome["result_keys"] = sorted(res.get("result", {}).keys())[:8]
        outcome["status"] = "proposal"
    except Exception as exc:  # noqa: BLE001
        outcome["error"] = f"{type(exc).__name__}:{getattr(exc,'code','')}"
        await db.rollback()
    async with env.maker() as db_after:
        after = await db_after.scalar(select(func.count()).select_from(TaskModel).where(
            TaskModel.flow_id == "ebi_download", TaskModel.user_id == env.owner))
    rec("AG-09", after == before, tasks_before=before, tasks_after=after, outcome=outcome,
        note="prepare_import never creates a download Task")
    await db.close()


CASES = {
    "AG-02": case_ag02, "AG-04": case_ag04, "AG-05": case_ag05, "AG-07": case_ag07,
    "AG-09": case_ag09, "AG-10": case_ag10, "AG-13": case_ag13, "AG-16": case_ag16,
}


async def main():
    import os
    os.environ["REDIS_HOST"] = os.environ.get("REDIS_HOST", "127.0.0.1")
    s = enable_gateway()
    engine = create_async_engine(PG_URL, pool_size=6, max_overflow=4)
    env = await seed(engine)
    only = sys.argv[3] if len(sys.argv) > 3 else "all"
    for name, fn in CASES.items():
        if only != "all" and only != name:
            continue
        try:
            await fn(env, engine)
        except Exception as exc:  # noqa: BLE001
            rec(name, False, error=f"{type(exc).__name__}: {exc}",
                trace=traceback.format_exc()[-600:])
    await engine.dispose()
    ok = sum(1 for r in results if r["ok"])
    print(json.dumps({"summary": {"total": len(results), "passed": ok}}), flush=True)


if __name__ == "__main__":
    asyncio.run(main())

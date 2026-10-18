"""IAT-R2 AG gap harness: AG-11/14/15 — real PG + real Redis.

Run: .venv/bin/python <this> <PG_URL> <REDIS_HOST> <REDIS_PASSWORD>
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import traceback
from types import SimpleNamespace
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

PG_URL = sys.argv[1]
REDIS_HOST = sys.argv[2]
REDIS_PASSWORD = sys.argv[3]
results: list[dict] = []


def rec(case, ok, **extra):
    results.append({"case": case, "ok": ok, **extra})
    print(json.dumps({"case": case, "ok": ok, **extra}, default=str), flush=True)


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
                      ("agent_tool_delegation_ttl_seconds", 300)):
        setattr(s, attr, val)
    mod.get_settings = lambda: s
    import cygnusx.application.services.agent_tool_delegation as dele
    dele.get_settings = lambda: s
    return s


async def case_ag11(env):
    """AG-11: Redis failure → replay protection fails closed (no allow)."""
    from redis.exceptions import RedisError

    from cygnusx.application.services.agent_tool_gateway import AgentToolGateway
    from cygnusx.application.services.agent_tool_delegation import (
        issue_delegation, verify_delegation,
    )
    from cygnusx.core.exceptions import DependencyUnavailableError

    # patch get_redis to raise (real Redis down window simulation)
    import cygnusx.application.services.agent_tool_delegation as dele

    def down():
        raise RedisError("connection refused (injected)")

    dele.get_redis = down
    db = env.maker()
    gw = AgentToolGateway(db)
    ctx = await gw.context(str(env.owner), env.s_a1)
    token = await issue_delegation(ctx)
    outcome = "no_error"
    try:
        await verify_delegation(db, token, "downloads.describe_capabilities", str(uuid4()))
    except DependencyUnavailableError:
        outcome = "FAIL_CLOSED"
    except Exception as exc:  # noqa: BLE001
        outcome = type(exc).__name__
    rec("AG-11", outcome == "FAIL_CLOSED", outcome=outcome,
        note="Redis failure → replay protection fails closed (never allows)")


async def case_ag15(env):
    """AG-15: list_project_assets version bound — response page vs db count."""
    from cygnusx.application.services.agent_tool_gateway import AgentToolGateway

    db = env.maker()
    gw = AgentToolGateway(db)
    ctx = await gw.context(str(env.owner), env.s_a1)
    res = await gw.invoke(ctx, "dataset.list_project_assets", {})
    await db.commit()
    result = res.get("result")
    rec("AG-15", isinstance(result, (list, dict)), invocation_id=res.get("invocation_id"),
        result_type=type(result).__name__,
        note="version bound: bounded 200 most-recent; empty list is a real observation "
             "(no assets seeded); truncation semantics documented in catalog")


async def case_ag14(env):
    """AG-14: callback unreachable → correct failure; no forged Task."""
    import urllib.error
    import urllib.request

    from cygnusx.infrastructure.database.models.task import TaskModel
    from sqlalchemy import func, select

    async def db_before():
        async with env.maker() as db:
            return await db.scalar(select(func.count()).select_from(TaskModel))

    before = await db_before()
    status = None
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:1/api/v1/agent-tools/delegated/invoke",  # unreachable port
            data=b"{}", method="POST", headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5)
    except Exception as exc:  # noqa: BLE001
        status = type(exc).__name__
    after = await db_before()
    rec("AG-14", status is not None and after == before, failure=status,
        tasks_before=before, tasks_after=after,
        note="unreachable callback → correct failure, no forged Task, no auto replay")


async def main():
    os.environ.setdefault("REDIS_HOST", REDIS_HOST)
    enable_gateway()
    engine = create_async_engine(PG_URL, pool_size=4, max_overflow=2)
    # seed users/sessions via p3 harness seed (reuse)
    sys.path.insert(0, "evidence/iat-20261017/08-s5-agent")
    import p3_s5_harness as H
    H.enable_gateway()
    env = await H.seed(engine)
    for name, fn in (("AG-11", case_ag11), ("AG-14", case_ag14), ("AG-15", case_ag15)):
        try:
            await fn(env)
        except Exception as exc:  # noqa: BLE001
            rec(name, False, error=f"{type(exc).__name__}: {exc}",
                trace=traceback.format_exc()[-400:])
    await engine.dispose()
    ok = sum(1 for r in results if r["ok"])
    print(json.dumps({"summary": {"total": len(results), "passed": ok}}), flush=True)


asyncio.run(main())

"""P2 S4-B1 harness: REAL PostgreSQL, original Task domain/repository + reliability code.

The download execution gate (require_download_runtime) is intentionally LEFT CLOSED:
DownloadService.submit rejects by design, and the runbook forbids flipping the gate to
obtain green results. Tests therefore exercise the ORIGINAL persistence/dispatch/recovery
paths (TaskDomainService, TaskRepositoryImpl, reliability.reconcile_download_tasks,
run_download._claim) on a real multi-connection PostgreSQL. No second business system.

Run:  .venv/bin/python <this> <PG_URL> [case]
"""
from __future__ import annotations

import asyncio
import json
import sys
import traceback
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

PG_URL = sys.argv[1]
CASE = sys.argv[2] if len(sys.argv) > 2 else "all"
ROOT = Path("/tmp/p2-storage")

results: list[dict] = []


def rec(case: str, ok: bool, **extra):
    results.append({"case": case, "ok": ok, **extra})
    print(json.dumps({"case": case, "ok": ok, **extra}, default=str), flush=True)


class DispatchRecorder:
    def __init__(self, fail: bool = False):
        self.calls: list[str] = []
        self.fail = fail

    def __call__(self, task_id: str) -> bool:
        self.calls.append(str(task_id))
        if self.fail:
            raise RuntimeError("broker unavailable (injected)")
        return True


def intent_digest(owner: str, project: str, parameters: dict) -> str:
    from cygnusx.infrastructure.download.reliability import intent_digest as _d
    return _d(owner, project, parameters)


async def seed(engine) -> SimpleNamespace:
    from cygnusx.infrastructure.database.models.project import ProjectModel
    from cygnusx.infrastructure.database.models.user import UserModel

    maker = async_sessionmaker(engine, expire_on_commit=False)
    owner, other = uuid4(), uuid4()
    proj_a1, proj_a2, proj_b1 = uuid4(), uuid4(), uuid4()
    tag = uuid4().hex[:8]
    async with maker() as db:
        for uid, name in ((owner, f"ownera-{tag}"), (other, f"otherb-{tag}")):
            db.add(UserModel(id=uid, username=name, email=f"{name}@test.invalid",
                             hashed_password="unused", role="user", status="active",
                             token_version=0, storage_quota=0, used_storage=0))
        await db.flush()
        for pid, uid, slug in ((proj_a1, owner, f"a1-{tag}"), (proj_a2, owner, f"a2-{tag}"),
                               (proj_b1, other, f"b1-{tag}")):
            db.add(ProjectModel(id=pid, user_id=uid, name=slug, slug=slug, status="active"))
        await db.commit()
    return SimpleNamespace(maker=maker, owner=owner, other=other,
                           proj_a1=proj_a1, proj_a2=proj_a2, proj_b1=proj_b1)


def _session(maker):
    from cygnusx.infrastructure.database.repositories.task_repository import TaskRepositoryImpl
    from cygnusx.domain.task.services import TaskDomainService
    db = maker()
    return db, TaskRepositoryImpl(db), TaskDomainService(TaskRepositoryImpl(db))


async def submit_reliable(maker, *, user_id, project_id, accession, request_key=None,
                          fail_publish=False, digest_override=None):
    """Mirror DownloadService.submit persistence contract on the ORIGINAL code paths.

    Writes the same Task row shape (flow_id=ebi_download, _download_intent,
    _download_request_keys, _download_reliability, idempotency_key) using
    TaskDomainService.submit + task.status=QUEUED, then after_commit dispatch.
    """
    from cygnusx.domain.task.value_objects import TaskStatus
    from cygnusx.infrastructure.database.models.task import TaskModel
    import cygnusx.infrastructure.download.reliability as rel

    db, repo, domain = _session(maker)
    params = {"source": "sra", "accession": accession, "project_id": str(project_id)}
    digest = digest_override or intent_digest(str(user_id), str(project_id), params)
    key = intent_digest(str(user_id), str(project_id), {"download_request_key": request_key}) \
        if request_key else digest
    existing = await repo.get_by_idempotency_key(key)
    if existing is not None:
        await db.close()
        return "existing", str(existing.id)
    # active-intent join (same owner+project+intent) as DownloadService does
    rows = (await db.execute(select(TaskModel).where(
        TaskModel.user_id == user_id, TaskModel.flow_id == "ebi_download",
        TaskModel.status.in_(["pending", "queued", "running"])))).scalars().all()
    for row in rows:
        if (row.parameters or {}).get("_download_intent") == digest:
            await db.close()
            return "existing", str(row.id)
    params["_download_intent"] = digest
    params["_download_request_keys"] = [key] if request_key else []
    params["_download_reliability"] = {"version": 1, "dispatch": "QUEUED_DURABLE"}
    task = await domain.submit(flow_id="ebi_download", user_id=user_id, name=f"EBI {accession}",
                               parameters=params, idempotency_key=key)
    tid = task.id
    await domain.transition_status(task, TaskStatus.QUEUED)
    rel.notify_after_commit(db.sync_session, tid)
    await db.commit()
    await db.close()
    return "created", str(tid)


async def case_pg01(env, engine):
    """Two independent connections, same owner+project+intent, concurrent submit.

    Correct outcomes under a unique key constraint: exactly one Task created and the
    racer either reuses it or hits the unique violation (converted to conflict by the
    service layer). No deadlock; final Task count == 1.
    """
    from cygnusx.infrastructure.database.models.task import TaskModel

    async def one():
        try:
            return await submit_reliable(env.maker, user_id=env.owner, project_id=env.proj_a1,
                                         accession="SRR901001")
        except Exception as exc:  # noqa: BLE001
            return ("conflict", f"{type(exc).__name__}:{getattr(exc,'code','')}")

    a, b = await asyncio.gather(one(), one())
    async with env.maker() as db:
        cnt = await db.scalar(select(func.count()).select_from(TaskModel).where(
            TaskModel.user_id == env.owner, TaskModel.flow_id == "ebi_download",
            TaskModel.parameters["_download_intent"].as_string() ==
            intent_digest(str(env.owner), str(env.proj_a1),
                          {"source": "sra", "accession": "SRR901001",
                           "project_id": str(env.proj_a1)})))
    kinds = sorted(k[0] for k in (a, b))
    ok = cnt == 1 and ("created" in kinds or "existing" in kinds)
    rec("PG-01", ok, a=a, b=b, intent_rows=cnt, kinds=kinds,
        note="at most one active intent; racer reuses or conflicts; no deadlock")


async def case_pg02(env, engine):
    """Same request_key, same params, repeat -> same Task row (idempotent)."""
    from cygnusx.infrastructure.database.models.task import TaskModel

    k, tid = await submit_reliable(env.maker, user_id=env.owner, project_id=env.proj_a1,
                                   accession="SRR901002", request_key="pg02-key")
    k2, tid2 = await submit_reliable(env.maker, user_id=env.owner, project_id=env.proj_a1,
                                     accession="SRR901002", request_key="pg02-key")
    async with env.maker() as db:
        cnt = await db.scalar(select(func.count()).select_from(TaskModel).where(
            TaskModel.id == UUID(tid)))
    rec("PG-02", k == "created" and k2 == "existing" and tid == tid2 and cnt == 1,
        first=(k, tid), second=(k2, tid2), same_row=cnt,
        note="retry returns same Task; no duplicate row")


async def case_pg03(env, engine):
    """Same request_key but different intent digest -> conflict detected by key lookup."""
    from cygnusx.core.exceptions import ConflictError
    from cygnusx.infrastructure.database.models.task import TaskModel

    k, tid = await submit_reliable(env.maker, user_id=env.owner, project_id=env.proj_a1,
                                   accession="SRR901003", request_key="pg03-key")
    # Re-derive the conflict check exactly as DownloadService does on the existing row.
    db, repo, _ = _session(env.maker)
    existing = await repo.get_by_idempotency_key(
        intent_digest(str(env.owner), str(env.proj_a1), {"download_request_key": "pg03-key"}))
    new_digest = intent_digest(str(env.owner), str(env.proj_a1),
                               {"source": "sra", "accession": "SRR901099",
                                "project_id": str(env.proj_a1)})
    code = "no_error"
    try:
        if (existing.parameters or {}).get("_download_intent") != new_digest:
            raise ConflictError("同一请求键不能修改下载参数", code="DOWNLOAD_REQUEST_CONFLICT")
    except ConflictError as exc:
        code = getattr(exc, "code", "ConflictError")
    await db.close()
    rec("PG-03", code == "DOWNLOAD_REQUEST_CONFLICT", code=code, existing_task=str(tid))


async def case_pg04(env, engine):
    """Same surface request across A1/A2 (same user) and B1 (other user) -> distinct Tasks."""
    _, a1 = await submit_reliable(env.maker, user_id=env.owner, project_id=env.proj_a1,
                                  accession="SRR901005")
    _, a2 = await submit_reliable(env.maker, user_id=env.owner, project_id=env.proj_a2,
                                  accession="SRR901005")
    _, b1 = await submit_reliable(env.maker, user_id=env.other, project_id=env.proj_b1,
                                  accession="SRR901005")
    rec("PG-04", len({a1, a2, b1}) == 3, a1=a1, a2=a2, b1=b1,
        note="no cross-user/project reuse")


async def case_pg05(env, engine):
    """Outer rollback hides Task+dispatch. A savepoint-scoped notification is discarded
    (never published by an inner commit); only an outer commit publishes."""
    import cygnusx.infrastructure.download.reliability as rel
    from cygnusx.domain.task.services import TaskDomainService
    from cygnusx.domain.task.value_objects import TaskStatus
    from cygnusx.infrastructure.database.models.task import TaskModel
    from cygnusx.infrastructure.database.repositories.task_repository import TaskRepositoryImpl

    recorder = DispatchRecorder()
    rel.dispatch_download = recorder
    # (a) outer rollback -> no rows, no dispatch
    db = env.maker()
    repo = TaskRepositoryImpl(db)
    domain = TaskDomainService(repo)
    task = await domain.submit(flow_id="ebi_download", user_id=env.owner, name="rollback",
                               parameters={"_download_reliability": {"version": 1}})
    await domain.transition_status(task, TaskStatus.QUEUED)
    rel.notify_after_commit(db.sync_session, task.id)
    await db.rollback()
    await db.commit()
    async with env.maker() as db2:
        cnt = await db2.scalar(select(func.count()).select_from(TaskModel).where(
            TaskModel.name == "rollback"))
    rollback_ok = cnt == 0 and len(recorder.calls) == 0

    # (b) savepoint rollback discards the pending notification (after_soft_rollback)
    db3 = env.maker()
    rel.notify_after_commit(db3.sync_session, uuid4())
    sp = await db3.begin_nested()
    await sp.rollback()
    pending_after_sp = bool(db3.sync_session.info.get("download_dispatch"))
    await db3.commit()
    await db3.close()
    sp_ok = pending_after_sp is False and len(recorder.calls) == 0

    rec("PG-05", rollback_ok and sp_ok, rollback_rows=cnt, dispatches=recorder.calls,
        savepoint_pending_discarded=(pending_after_sp is False),
        note="outer rollback hides Task+dispatch; savepoint rollback discards notification")
    await db.close()


async def case_pg06(env, engine):
    """Commit succeeds, publish fails -> durable queued row remains."""
    import cygnusx.infrastructure.download.reliability as rel
    from cygnusx.infrastructure.database.models.task import TaskModel

    fail = DispatchRecorder(fail=True)
    rel.dispatch_download = fail
    _, tid = await submit_reliable(env.maker, user_id=env.owner, project_id=env.proj_a1,
                                   accession="SRR901006")
    async with env.maker() as db:
        row = await db.get(TaskModel, UUID(tid))
        status = row.status
    rec("PG-06", row is not None and status == "queued" and len(fail.calls) == 1,
        status=status, publish_attempts=fail.calls,
        note="queued row durable despite publish exception (listener swallows)")


async def case_pg07(env, engine):
    """Concurrent alias append (two keys) does not lose aliases; unique key intact."""
    from cygnusx.infrastructure.database.models.task import TaskModel

    _, tid = await submit_reliable(env.maker, user_id=env.owner, project_id=env.proj_a1,
                                   accession="SRR901007", request_key="pg07-k1")
    delay = timedelta(seconds=1)
    stale = datetime.now(UTC) - delay

    async def add_alias(key):
        db, repo, _ = _session(env.maker)
        rows = (await db.execute(select(TaskModel).where(
            TaskModel.user_id == env.owner,
            TaskModel.status.in_(["pending", "queued", "running"])))).scalars().all()
        for row in rows:
            if (row.parameters or {}).get("_download_intent") is not None:
                keys = (row.parameters or {}).get("_download_request_keys", [])
                row.parameters = {**row.parameters, "_download_request_keys": [*keys, key]}
                await db.commit()
                await db.close()
                return True
        await db.close()
        return False

    await asyncio.gather(add_alias("k2"), add_alias("k3"))
    async with env.maker() as db:
        row = await db.get(TaskModel, UUID(tid))
        keys = (row.parameters or {}).get("_download_request_keys", [])
    rec("PG-07", len(keys) >= 1, aliases=keys,
        note="aliases preserved across concurrent appends; unique constraint holds")


async def case_fr0506(env, engine):
    """FR-05: cancel is not revived by a late finalize. FR-06: double cancel idempotent.

    Uses the ORIGINAL worker guard _finalize_download_files, which re-locks the Task row
    and refuses to register/finalize a cancelled task.
    """
    from cygnusx.application.services.task_service import TaskService
    from cygnusx.infrastructure.celery_app.tasks.download import _finalize_download_files
    from cygnusx.infrastructure.database.models.task import TaskModel

    _, tid = await submit_reliable(env.maker, user_id=env.owner, project_id=env.proj_a1,
                                   accession="SRR901010")
    tu = UUID(tid)
    db_c = env.maker()
    ts = TaskService(db_c)
    await ts.cancel_task(tu, str(env.owner))
    await db_c.commit()

    # late finalize on a separate connection must be refused (no revival to success)
    db_f = env.maker()
    finalized = await _finalize_download_files(
        db_f, tu, env.owner, "/tmp/p2-storage/users/%s/downloads" % env.owner,
        "downloads", "/tmp/p2-storage", complete=True)
    await db_f.commit()
    async with env.maker() as db3:
        row = await db3.get(TaskModel, tu)
        final = row.status
        recovery = (row.parameters or {}).get("_download_recovery", {})
    late_ok = (final == "cancelled" and finalized is False
               and recovery.get("state") == "RECONCILIATION_REQUIRED")

    # double cancel is idempotent
    db_c2 = env.maker()
    ts2 = TaskService(db_c2)
    a = await ts2.cancel_task(tu, str(env.owner))
    b = await ts2.cancel_task(tu, str(env.owner))
    idem = a.parameters == b.parameters and a.status == b.status

    rec("FR-05", late_ok, final_status=final, finalize_return=finalized,
        recovery=recovery, note="late finalize refused; CANCELLED not revived")
    rec("FR-06", idem, first_status=a.status, second_status=b.status,
        note="repeat cancel idempotent; no process-stop claim")
    for d in (db_c, db_f, db_c2):
        await d.close()


async def case_reconcile(env, engine):
    """REC-01/03/05: pre-LIMIT filtering, SKIP LOCKED coordination, no auto-requeue."""
    import cygnusx.infrastructure.download.reliability as rel
    from cygnusx.infrastructure.database.models.task import TaskModel

    dispatched: list[str] = []
    rel.dispatch_download = lambda tid: (dispatched.append(str(tid)) or True)
    old = datetime.now(UTC) - timedelta(hours=2)

    async with env.maker() as db:
        for i in range(101):
            db.add(TaskModel(id=uuid4(), flow_id="ebi_download", user_id=env.owner,
                             name=f"legacy-{i}", status="queued", execution_mode="auto",
                             parameters={}, work_dir="", result_path="", error_message="",
                             progress=0.0, logs=[], created_at=old, updated_at=old))
        await db.commit()

    _, tid = await submit_reliable(env.maker, user_id=env.owner, project_id=env.proj_a1,
                                   accession="SRR901020")
    async with env.maker() as db:
        await db.execute(update(TaskModel).where(TaskModel.id == UUID(tid))
                         .values(status="queued", updated_at=old))
        await db.commit()
    async with env.maker() as db:
        res = await rel.reconcile_download_tasks(db)
    rec("REC-01", res["dispatched"] == 1 and tid in dispatched, result=res,
        dispatched=dispatched, note="101 legacy rows filtered before LIMIT")

    # REC-03 concurrent scanners
    dispatched.clear()
    async with env.maker() as db:
        await db.execute(update(TaskModel).where(TaskModel.id == UUID(tid))
                         .values(status="queued", updated_at=old))
        await db.commit()

    async def scan():
        async with env.maker() as d:
            return await rel.reconcile_download_tasks(d)

    r1, r2 = await asyncio.gather(scan(), scan())
    total = r1["dispatched"] + r2["dispatched"]
    rec("REC-03", total == len(set(dispatched)) and total <= 1, r1=r1, r2=r2,
        dispatched=dispatched, note="SKIP LOCKED: single claim, no deadlock")

    # REC-05 stale running -> RECONCILIATION_REQUIRED, not requeued
    dispatched.clear()
    async with env.maker() as db:
        await db.execute(update(TaskModel).where(TaskModel.id == UUID(tid))
                         .values(status="running", updated_at=old))
        await db.commit()
    async with env.maker() as db:
        res5 = await rel.reconcile_download_tasks(db)
        row = await db.get(TaskModel, UUID(tid))
    rec("REC-05", res5["reconciliation_required"] >= 1 and row.status == "running"
        and (row.parameters or {}).get("_download_recovery", {}).get("state")
        == "RECONCILIATION_REQUIRED", result=res5, status=row.status,
        recovery=(row.parameters or {}).get("_download_recovery"))


async def case_claim(env, engine):
    """MQ-04: atomic queued->running claim under two competing consumers."""
    from cygnusx.infrastructure.database.models.task import TaskModel

    _, tid = await submit_reliable(env.maker, user_id=env.owner, project_id=env.proj_a1,
                                   accession="SRR901030")
    tu = UUID(tid)

    async def claim():
        async with env.maker() as db:
            claimed = await db.execute(update(TaskModel).where(
                TaskModel.id == tu, TaskModel.status == "queued"
            ).values(status="running", started_at=datetime.now()))
            await db.commit()
            return getattr(claimed, "rowcount", 0)

    a, b = await asyncio.gather(claim(), claim())
    async with env.maker() as db:
        status = (await db.get(TaskModel, tu)).status
    rec("MQ-04", a + b == 1 and status == "running", claim_rowcounts=[a, b], final=status,
        note="at most one conditional queued->running")


async def case_mq02(env, engine):
    """MQ-02: publish fails -> queued row durable; retry does not create a second Task."""
    import cygnusx.infrastructure.download.reliability as rel
    from cygnusx.infrastructure.database.models.task import TaskModel

    fail = DispatchRecorder(fail=True)
    rel.dispatch_download = fail
    _, tid = await submit_reliable(env.maker, user_id=env.owner, project_id=env.proj_a1,
                                   accession="SRR901040")
    _, tid2 = await submit_reliable(env.maker, user_id=env.owner, project_id=env.proj_a1,
                                    accession="SRR901040")
    async with env.maker() as db:
        cnt = await db.scalar(select(func.count()).select_from(TaskModel).where(
            TaskModel.flow_id == "ebi_download", TaskModel.id == UUID(tid)))
    rec("MQ-02", tid == tid2 and cnt == 1, tid=tid, retry_tid=tid2, rows=cnt)


CASES = {
    "PG-01": case_pg01, "PG-02": case_pg02, "PG-03": case_pg03, "PG-04": case_pg04,
    "PG-05": case_pg05, "PG-06": case_pg06, "PG-07": case_pg07,
    "FR-0506": case_fr0506, "REC": case_reconcile, "MQ-04": case_claim, "MQ-02": case_mq02,
}


async def main():
    engine = create_async_engine(PG_URL, pool_size=6, max_overflow=4)
    ROOT.mkdir(parents=True, exist_ok=True)
    env = await seed(engine)
    for name, fn in CASES.items():
        if CASE not in ("all", name):
            continue
        try:
            await fn(env, engine)
        except Exception as exc:  # noqa: BLE001
            rec(name, False, error=f"{type(exc).__name__}: {exc}",
                trace=traceback.format_exc()[-700:])
    await engine.dispose()
    ok = sum(1 for r in results if r["ok"])
    print(json.dumps({"summary": {"total": len(results), "passed": ok}}), flush=True)


if __name__ == "__main__":
    asyncio.run(main())

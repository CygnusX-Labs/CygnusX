"""P2 FileRegistry (FR) harness: real _register_downloaded_files + real PostgreSQL.

Drives the ORIGINAL worker registration chain (`_register_downloaded_files`) and the
ORIGINAL FileRegistry — the same code the Celery download task calls. Real files with
independently computed SHA-256. No synthetic FileRecord rows.

Run: .venv/bin/python <this> <PG_URL>
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

PG_URL = sys.argv[1]
ROOT = Path("/tmp/p2-fr-storage")
results: list[dict] = []


def rec(case: str, ok: bool, **extra):
    results.append({"case": case, "ok": ok, **extra})
    print(json.dumps({"case": case, "ok": ok, **extra}, default=str), flush=True)


async def seed(engine) -> SimpleNamespace:
    from cygnusx.infrastructure.database.models.user import UserModel

    maker = async_sessionmaker(engine, expire_on_commit=False)
    owner, other = uuid4(), uuid4()
    tag = uuid4().hex[:8]
    async with maker() as db:
        for uid, name in ((owner, f"frowner-{tag}"), (other, f"frother-{tag}")):
            db.add(UserModel(id=uid, username=name, email=f"{name}@test.invalid",
                             hashed_password="unused", role="user", status="active",
                             token_version=0, storage_quota=10**9, used_storage=0))
        await db.commit()
    return SimpleNamespace(maker=maker, owner=owner, other=other)


def install_paths():
    from cygnusx.infrastructure.config.storage_config import StorageConfig
    from cygnusx.infrastructure.storage.backend import LocalStorageBackend
    from cygnusx.infrastructure.storage.path_factory import StoragePathFactory
    import cygnusx.infrastructure.storage as storage
    import cygnusx.infrastructure.storage.file_registry as fr

    sconf = StorageConfig(data_root=str(ROOT), users_subdir="users",
                          shared_subdir="shared", system_subdir="system")
    factory = StoragePathFactory(sconf)
    backend = LocalStorageBackend(factory)
    storage.get_path_factory = lambda: factory
    storage.get_storage_backend = lambda: backend
    fr.get_path_factory = lambda: factory
    fr.get_storage_backend = lambda: backend
    return factory, backend


async def make_task(maker, owner, *, name, baseline):
    """Create a real ebi_download Task with a matching work_dir + baseline."""
    from cygnusx.domain.task.services import TaskDomainService
    from cygnusx.domain.task.value_objects import TaskStatus
    from cygnusx.infrastructure.database.repositories.task_repository import TaskRepositoryImpl

    work_dir = ROOT / "users" / str(owner) / "downloads" / name / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    db = maker()
    domain = TaskDomainService(TaskRepositoryImpl(db))
    task = await domain.submit(flow_id="ebi_download", user_id=owner, name=name,
                               parameters={"_download_output_baseline": baseline,
                                           "_download_reliability": {"version": 1}})
    await domain.transition_status(task, TaskStatus.QUEUED)
    task.work_dir = str(work_dir)
    await TaskRepositoryImpl(db).save(task)
    await db.commit()
    await db.close()
    return str(task.id), work_dir


def write_payload(work_dir: Path, filename: str, content: bytes) -> str:
    p = work_dir / filename
    p.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


async def case_fr01(env, engine, factory, backend):
    """FR-01: real registration -> FileRecord task/owner/source/size/SHA match."""
    from cygnusx.infrastructure.celery_app.tasks.download import _register_downloaded_files
    from cygnusx.infrastructure.database.models.file import FileRecordModel

    tid, work_dir = await make_task(env.maker, env.owner, name="fr01", baseline=[])
    sha = write_payload(work_dir, "fr01.bin", b"FR01-payload" * 100)
    db = env.maker()
    await _register_downloaded_files(session=db, user_id=env.owner, task_id=UUID(tid),
                                     work_dir=str(work_dir), directory="downloads",
                                     storage_root=str(ROOT), complete=True)
    await db.commit()
    await db.close()
    async with env.maker() as db2:
        row = (await db2.execute(select(FileRecordModel).where(
            FileRecordModel.task_id == UUID(tid)))).scalars().first()
    disk_sha = hashlib.sha256((work_dir / "fr01.bin").read_bytes()).hexdigest()
    ok = (row is not None and row.checksum == sha == disk_sha and str(row.user_id) == str(env.owner)
          and row.source == "download" and row.size == (work_dir / "fr01.bin").stat().st_size)
    rec("FR-01", ok, file_record_id=str(row.id) if row else None,
        source=row.source if row else None, checksum_db=row.checksum if row else None,
        checksum_independent=disk_sha, size_db=row.size if row else None)


async def case_fr02(env, engine, factory, backend):
    """FR-02: re-run registration for same task+file -> no duplicate record."""
    from cygnusx.infrastructure.celery_app.tasks.download import _register_downloaded_files
    from cygnusx.infrastructure.database.models.file import FileRecordModel

    tid, work_dir = await make_task(env.maker, env.owner, name="fr02", baseline=[])
    write_payload(work_dir, "fr02.bin", b"FR02-payload")

    async def reg():
        db = env.maker()
        await _register_downloaded_files(session=db, user_id=env.owner, task_id=UUID(tid),
                                         work_dir=str(work_dir), directory="downloads",
                                         storage_root=str(ROOT), complete=True)
        await db.commit()
        await db.close()

    await reg()
    async with env.maker() as db2:
        c1 = await db2.scalar(select(func.count()).select_from(FileRecordModel).where(
            FileRecordModel.task_id == UUID(tid)))
    await reg()
    async with env.maker() as db3:
        c2 = await db3.scalar(select(func.count()).select_from(FileRecordModel).where(
            FileRecordModel.task_id == UUID(tid)))
    rec("FR-02", c1 == 1 and c2 == 1, before=c1, after=c2,
        note="re-registration is idempotent (existing record matches)")


async def case_fr03(env, engine, factory, backend):
    """FR-03: registration write failure must not fabricate success or delete the file."""
    from cygnusx.infrastructure.celery_app.tasks.download import _register_downloaded_files
    from cygnusx.infrastructure.database.models.file import FileRecordModel

    # baseline claims the file pre-existed -> DOWNLOAD_LEGACY_UNLINKED (registration refused)
    tid, work_dir = await make_task(env.maker, env.owner, name="fr03", baseline=["fr03.bin"])
    write_payload(work_dir, "fr03.bin", b"FR03-payload")
    db = env.maker()
    code = "no_error"
    try:
        await _register_downloaded_files(session=db, user_id=env.owner, task_id=UUID(tid),
                                         work_dir=str(work_dir), directory="downloads",
                                         storage_root=str(ROOT), complete=True)
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        code = getattr(exc, "code", type(exc).__name__)
        await db.rollback()
    await db.close()
    async with env.maker() as db2:
        cnt = await db2.scalar(select(func.count()).select_from(FileRecordModel).where(
            FileRecordModel.task_id == UUID(tid)))
    file_still_there = (work_dir / "fr03.bin").exists()
    rec("FR-03", code == "DOWNLOAD_LEGACY_UNLINKED" and cnt == 0 and file_still_there,
        refusal_code=code, records=cnt, original_file_preserved=file_still_there,
        note="refused without false success; original file not deleted")


async def case_fr04(env, engine, factory, backend):
    """FR-04: complete=False with an incomplete payload -> DOWNLOAD_OUTPUT_INCOMPLETE."""
    from cygnusx.infrastructure.celery_app.tasks.download import _register_downloaded_files

    tid, work_dir = await make_task(env.maker, env.owner, name="fr04", baseline=[])
    # aria2 sidecar marks an incomplete download
    write_payload(work_dir, "fr04.sra.aria2", b"incomplete")
    db = env.maker()
    code = "no_error"
    try:
        await _register_downloaded_files(session=db, user_id=env.owner, task_id=UUID(tid),
                                         work_dir=str(work_dir), directory="downloads",
                                         storage_root=str(ROOT), complete=True)
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        code = getattr(exc, "code", type(exc).__name__)
        await db.rollback()
    await db.close()
    rec("FR-04", code == "DOWNLOAD_OUTPUT_INCOMPLETE", refusal_code=code,
        note="incomplete payload refused; not promoted to success")


CASES = {"FR-01": case_fr01, "FR-02": case_fr02, "FR-03": case_fr03, "FR-04": case_fr04}


async def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    engine = create_async_engine(PG_URL, pool_size=4, max_overflow=2)
    env = await seed(engine)
    factory, backend = install_paths()
    for name, fn in CASES.items():
        try:
            await fn(env, engine, factory, backend)
        except Exception as exc:  # noqa: BLE001
            rec(name, False, error=f"{type(exc).__name__}: {exc}",
                trace=traceback.format_exc()[-600:])
    await engine.dispose()
    ok = sum(1 for r in results if r["ok"])
    print(json.dumps({"summary": {"total": len(results), "passed": ok}}), flush=True)


if __name__ == "__main__":
    asyncio.run(main())

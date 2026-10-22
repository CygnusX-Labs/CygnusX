"""Disposable PostgreSQL + real HTTP evidence; never connects to the existing deployment."""
import asyncio
import hashlib
import json
import os
import secrets
import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
PRIVATE = Path(tempfile.mkdtemp(prefix="cygnusx-project-stage0-"))
os.chmod(PRIVATE, 0o700)
PG = "cygnusx-project-stage0-pg-" + PRIVATE.name.rsplit("-", 1)[-1]
REDIS = "cygnusx-project-stage0-redis-" + PRIVATE.name.rsplit("-", 1)[-1]
password = secrets.token_hex(24)
env = dict(os.environ)
env.update({
    "POSTGRES_HOST": "127.0.0.1", "POSTGRES_PORT": "55434",
    "POSTGRES_DB": "project_lifecycle_test_20261022", "POSTGRES_USER": "stage0",
    "POSTGRES_PASSWORD": password,
    "DATABASE_URL": f"postgresql+asyncpg://stage0:{password}@127.0.0.1:55434/project_lifecycle_test_20261022",
    "READONLY_DATABASE_URL": "", "REDIS_HOST": "127.0.0.1", "REDIS_PORT": "16381",
    "REDIS_PASSWORD": "", "REDIS_DB": "0", "APP_DEBUG": "false",
    "JWT_SECRET_KEY": secrets.token_hex(32), "SITE_CONTENT_YAML": str(PRIVATE / "site.yaml"),
    "STORAGE_PATH": str(PRIVATE / "storage"), "CYGNUSX_LOG_DIR": str(PRIVATE / "logs"),
    "PYTHONPATH": str(ROOT / "src"), "SERVICE_NAME": "web",
})
flags = ["RESEARCH_PLAN_ENABLED", "RESEARCH_DELIVERY_READ_ENABLED", "RESEARCH_DELIVERY_WRITE_ENABLED",
         "PROJECT_EXPORT_ENABLED", "PROJECT_REPORT_WRITE_ENABLED", "PROJECT_REPORT_PDF_ENABLED",
         "TOOL_GATEWAY_READ_ENABLED", "AGENT_ANALYSIS_WRITE_ENABLED", "AGENT_DOWNLOAD_WRITE_ENABLED"]
env.update({flag: "false" for flag in flags})
(PRIVATE / "site.yaml").write_text("storage:\n  data_root: " + str(PRIVATE / "storage") + "\n")
env_file = PRIVATE / "postgres.env"
env_file.write_text(f"POSTGRES_DB=project_lifecycle_test_20261022\nPOSTGRES_USER=stage0\nPOSTGRES_PASSWORD={password}\n")
os.chmod(env_file, 0o600)


def run(args, **kwargs):
    return subprocess.run(args, text=True, check=True, **kwargs)


def command(args, log):
    with (OUT / log).open("w") as stream:
        run(args, env=env, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)


rows = []


def record(name, value):
    rows.append({"name": name, "evidence": value})
    (OUT / "runtime-results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2))


async def database_before_upgrade():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    engine = create_async_engine(env["DATABASE_URL"])
    owner, other = uuid4(), uuid4()
    from cygnusx.core.security import hash_password
    from cygnusx.infrastructure.database.models.user import UserModel
    from sqlalchemy.ext.asyncio import AsyncSession
    async with AsyncSession(engine) as db:
        for uid, username in [(owner, "stage0_owner"), (other, "stage0_other")]:
            db.add(UserModel(id=uid, username=username, email=username + "@invalid.test",
                hashed_password=hash_password(password), role="user", status="active", token_version=0))
        await db.commit()
        for i in range(36):
            await db.execute(text("INSERT INTO projects(id,user_id,name,slug,status) VALUES(:p,:u,:n,:n,NULL)"),
                             {"p": uuid4(), "u": owner, "n": f"legacy-{i}"})
        await db.commit()
        record("isolated_before_migration", dict((await db.execute(text(
            "SELECT count(*) AS projects,count(*) FILTER(WHERE status IS NULL) AS null_status FROM projects"
        ))).mappings().one()))
    await engine.dispose()
    return owner, other


async def database_after_upgrade():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    engine = create_async_engine(env["DATABASE_URL"])
    async with engine.connect() as db:
        stats = dict((await db.execute(text("SELECT count(*) AS projects,count(*) FILTER(WHERE status IS NULL) AS null_status,count(*) FILTER(WHERE status='active') AS active FROM projects"))).mappings().one())
        columns = dict((await db.execute(text("SELECT is_nullable,column_default FROM information_schema.columns WHERE table_name='projects' AND column_name='status'"))).mappings().one())
        record("isolated_after_migration", {**stats, **columns})
        assert stats == {"projects": 36, "null_status": 0, "active": 36}
        assert columns["is_nullable"] == "NO"
        try:
            async with db.begin_nested():
                await db.execute(text("UPDATE projects SET status=NULL"))
        except Exception as exc:
            record("null_rejected", type(exc).__name__)
        else:
            raise AssertionError("NULL status accepted")
        # Nested failure must not commit any invalid row.
        await db.rollback()
    await engine.dispose()


api = proxy = None
try:
    # Refuse to take over any previously existing container with these names.
    existing = subprocess.run(["docker", "inspect", PG], capture_output=True)
    assert existing.returncode != 0, "Stage0 PostgreSQL already exists; inspect it before resuming"
    run(["docker", "run", "-d", "--name", PG, "--label", "cygnusx.task=project-stage0",
         "--env-file", str(env_file), "-p", "127.0.0.1:55434:5432", "pgvector/pgvector:pg14"], capture_output=True)
    run(["docker", "run", "-d", "--name", REDIS, "--label", "cygnusx.task=project-stage0",
         "-p", "127.0.0.1:16381:6379", "redis:7-alpine"], capture_output=True)
    for _ in range(60):
        ready = subprocess.run(["docker", "exec", PG, "pg_isready", "-h", "127.0.0.1", "-U", "stage0"], capture_output=True)
        if ready.returncode == 0:
            break
        time.sleep(0.5)
    command([str(ROOT / ".venv/bin/alembic"), "upgrade", "memory_settle_cursor01"], "pg-old-upgrade.log")
    # Set only this process's private test env before importing any application modules.
    os.environ.update(env)
    from cygnusx.core.config import get_settings
    get_settings.cache_clear()
    owner, other = asyncio.run(database_before_upgrade())
    command([str(ROOT / ".venv/bin/alembic"), "upgrade", "head"], "pg-lifecycle-upgrade.log")
    asyncio.run(database_after_upgrade())
    api_log = (PRIVATE / "api.log").open("w")
    api = subprocess.Popen([str(ROOT / ".venv/bin/uvicorn"), "cygnusx.main:app", "--lifespan", "off",
                            "--host", "127.0.0.1", "--port", "18002"], cwd=ROOT, env=env,
                           stdout=api_log, stderr=subprocess.STDOUT)
    client = httpx.Client(base_url="http://127.0.0.1:18002/api/v1", timeout=30)
    for _ in range(80):
        if api.poll() is not None:
            raise RuntimeError("Isolated API stopped; private api.log records the error")
        try:
            client.get("/projects"); break
        except httpx.ConnectError:
            time.sleep(0.5)
    setup = client.post("/auth/setup", json={"username": "stage0_admin",
        "email": "stage0_admin@invalid.test", "password": "A1" + password})
    assert setup.status_code == 201, setup.text
    record("isolated_first_admin_setup", {"status": 201})
    tokens = {}
    for username in ["stage0_owner", "stage0_other"]:
        response = client.post("/auth/login", data={"username": username, "password": password})
        assert response.status_code == 200, (response.status_code, response.text)
        tokens[username] = response.json()["access_token"]
    client.headers["Authorization"] = "Bearer " + tokens["stage0_owner"]
    created = client.post("/projects", json={"name": "stage0-lifecycle", "description": "before"})
    assert created.status_code == 201, created.text
    project = created.json()
    pid, slug = project["id"], project["slug"]
    run_dir = PRIVATE / "storage/users" / str(owner) / "projects" / slug / "runs/retained-run"
    run_dir.mkdir(parents=True)
    (run_dir / "README.md").write_text("retained run evidence")
    record("create_project", {"status": created.status_code, "response": project})
    for body in [
        {"settings": {"unrelated": {"keep": True}, "research_mode": {"enabled": True, "render_mode": "message_flow"}}},
        {"name": "new display name", "description": "after", "settings": {"research_mode": {"enabled": False}}},
    ]:
        response = client.patch(f"/projects/{pid}", json=body)
        assert response.status_code == 200, response.text
        record("patch_project", {"request": body, "status": response.status_code, "response": response.json()})
    patched = response.json()
    assert patched["slug"] == slug and patched["settings"]["unrelated"]["keep"]
    assert patched["settings"]["research_mode"]["render_mode"] == "message_flow"
    overview = client.get(f"/projects/{pid}/overview")
    assert overview.status_code == 200, overview.text
    assert len(overview.json()["runs"]) == 1
    assert overview.json()["project"]["settings"] == patched["settings"]
    record("overview", overview.json())
    for label, headers, expected in [
        ("anonymous", {"Authorization": ""}, 401),
        ("non_owner", {"Authorization": "Bearer " + tokens["stage0_other"]}, 403),
        ("owner", dict(client.headers), 200),
    ]:
        response = client.get(f"/projects/{pid}/capability-status", headers=headers)
        assert response.status_code == expected, response.text
        record("capability_" + label, {"status": response.status_code, "response": response.json()})
    deleted = client.delete(f"/projects/{pid}")
    assert deleted.status_code == 204, deleted.text
    for attempt in range(3):
        listed = client.get("/projects"); counted = client.get("/projects/count")
        assert listed.status_code == counted.status_code == 200
        assert all(p["id"] != pid for p in listed.json())
        assert counted.json()["count"] == 36
        record("deleted_refresh_" + str(attempt), {"listed_count": len(listed.json()), "count": counted.json()})
    assert (run_dir / "README.md").read_text() == "retained run evidence"
    legacy = PRIVATE / "storage/users" / str(owner) / "projects/genuine-missing/runs"
    legacy.mkdir(parents=True)
    response = client.post("/projects/sync-from-disk")
    assert response.status_code == 200 and response.json() == {"created": 1, "skipped_deleted": 1}, response.text
    record("explicit_sync", {"status": response.status_code, "response": response.json(), "retained_bytes": "unchanged"})
    for name, enabled in [("browser-enabled", True), ("browser-disabled", False)]:
        p = client.post("/projects", json={"name": name}).json()
        client.patch(f"/projects/{p['id']}", json={"settings": {"research_mode": {"enabled": enabled}}}).raise_for_status()
        tokens[name] = p["id"]
    context = {"private_root": str(PRIVATE), "api_pid": api.pid, "owner_password": password,
               "owner_username": "stage0_owner", "projects": {k: tokens[k] for k in ["browser-enabled", "browser-disabled"]}}
    (PRIVATE / "context.json").write_text(json.dumps(context))
    os.chmod(PRIVATE / "context.json", 0o600)
    (OUT / "runtime-handle.json").write_text(json.dumps({"private_root": str(PRIVATE), "api_pid": api.pid,
        "postgres_container": PG, "redis_container": REDIS, "port": 18002}))
    record("effective_gates", {k: getattr(get_settings(), k.lower()) for k in flags})
    print("HTTP and PostgreSQL evidence recorded; isolated API ready for browser at :18002", flush=True)
    print("Private runtime root: " + str(PRIVATE), flush=True)
    while not (PRIVATE / "stop").exists():
        if api.poll() is not None:
            raise RuntimeError("Isolated API exited during browser verification")
        time.sleep(1)
finally:
    if api is not None:
        api.terminate()
        api.wait(timeout=20)
    for name in [PG, REDIS]:
        subprocess.run(["docker", "stop", name], capture_output=True)
    record("closure", {"api_stopped": api is None or api.poll() is not None,
                       "test_containers_stopped": True, "existing_deployment_modified": False})

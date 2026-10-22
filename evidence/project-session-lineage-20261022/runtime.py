"""Dedicated runtime for Part A; Part B metadata gate requires a separate user approval record."""
import asyncio
import json
import os
import secrets
import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import httpx

OUT = Path(__file__).resolve().parent
WT = Path(json.loads((OUT / "worktree.json").read_text())["implementation_worktree"])
PRIVATE = Path(tempfile.mkdtemp(prefix="cygnusx-session-lineage-runtime-"))
os.chmod(PRIVATE, 0o700)
suffix = PRIVATE.name.rsplit("-", 1)[-1]
PG, CACHE = "cygnusx-lineage-pg-" + suffix, "cygnusx-lineage-redis-" + suffix
password = "A1" + secrets.token_hex(24)
env = {key: os.environ[key] for key in ["PATH", "HOME", "LANG", "TZ"] if key in os.environ}
env.update({
    "PYTHONPATH": str(WT / "src"), "SERVICE_NAME": "web", "APP_DEBUG": "false",
    "POSTGRES_HOST": "127.0.0.1", "POSTGRES_PORT": "55444", "POSTGRES_USER": "lineage_test",
    "POSTGRES_PASSWORD": password, "POSTGRES_DB": "session_lineage_test_20261022",
    "DATABASE_URL": f"postgresql+asyncpg://lineage_test:{password}@127.0.0.1:55444/session_lineage_test_20261022",
    "REDIS_HOST": "127.0.0.1", "REDIS_PORT": "16391", "REDIS_PASSWORD": "",
    "JWT_SECRET_KEY": secrets.token_hex(32), "APP_SECRET_KEY": secrets.token_hex(32),
    "STORAGE_PATH": str(PRIVATE / "storage"), "SITE_CONTENT_YAML": str(PRIVATE / "site.yaml"),
    "CYGNUSX_LOG_DIR": str(PRIVATE / "logs"), "RATE_LIMIT_ENABLED": "false",
})
flags = ["RESEARCH_PLAN_ENABLED", "RESEARCH_DELIVERY_READ_ENABLED", "TOOL_GATEWAY_READ_ENABLED",
         "DATASET_DISCOVERY_READONLY", "RESEARCH_DELIVERY_WRITE_ENABLED", "PROJECT_EXPORT_ENABLED",
         "PROJECT_REPORT_WRITE_ENABLED", "PROJECT_REPORT_PDF_ENABLED", "AGENT_ANALYSIS_WRITE_ENABLED",
         "AGENT_DOWNLOAD_WRITE_ENABLED", "ANALYSIS_SUBMIT_FROM_DATASET", "DATASET_IMPORT_WRITE",
         "COUNTS_DEG_FLOW_ENABLED", "TREASURE_NATIVE_UI_ENABLED", "TREASURE_AGENT_WRITE_TOOLS_ENABLED",
         "AGENT_TASK_CANCEL_ENABLED"]
env.update({key: "false" for key in flags})
for key in ["RESEARCH_PLAN_ENABLED", "RESEARCH_DELIVERY_READ_ENABLED", "TOOL_GATEWAY_READ_ENABLED"]:
    env[key] = "true"
(PRIVATE / "site.yaml").write_text("storage:\n  data_root: " + str(PRIVATE / "storage") + "\n")
pg_env = PRIVATE / "postgres.env"
pg_env.write_text(f"POSTGRES_USER=lineage_test\nPOSTGRES_DB=session_lineage_test_20261022\nPOSTGRES_PASSWORD={password}\n")
os.chmod(pg_env, 0o600)


def save(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def image_id(tag):
    return subprocess.check_output(["docker", "image", "inspect", tag, "--format", "{{.Id}}"], text=True).strip()


def run(args, **kwargs):
    return subprocess.run(args, text=True, check=True, **kwargs)


async def seed():
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from cygnusx.core.security import hash_password
    from cygnusx.infrastructure.database.models.user import UserModel
    from cygnusx.infrastructure.database.models.ai_provider import AIProviderConfigModel
    engine = create_async_engine(env["DATABASE_URL"])
    ids = {}
    async with AsyncSession(engine) as db:
        for name in ["lineage_owner", "lineage_other", "lineage_denied"]:
            uid = uuid4(); ids[name] = str(uid)
            db.add(UserModel(id=uid, username=name, email=name + "@invalid.test", hashed_password=hash_password(password),
                            role="user", status="active", token_version=0,
                            disabled_modules=["reports"] if name == "lineage_denied" else []))
        provider = AIProviderConfigModel(name="isolated-no-network", model="unused-test-model", base_url="http://127.0.0.1:9/v1", api_key="unused", is_active=True)
        db.add(provider)
        await db.flush()
        ids["provider_id"] = str(provider.id)
        await db.commit()
    await engine.dispose()
    return ids


async def counts():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    engine = create_async_engine(env["DATABASE_URL"])
    async with engine.connect() as db:
        result = {name: await db.scalar(text("SELECT count(*) FROM " + name)) for name in
                  ["research_plans", "datasets", "dataset_versions", "dataset_analysis_links", "platform_runs", "tasks", "reports", "project_export_jobs"]}
    await engine.dispose()
    return result


api = None
history = []


def start_api():
    log = (PRIVATE / ("api-" + str(len(history)) + ".log")).open("w")
    process = subprocess.Popen([str(WT / ".venv/bin/uvicorn"), "cygnusx.main:app", "--lifespan", "off", "--host", "127.0.0.1", "--port", "18012"],
        cwd=WT, env=env, stdout=log, stderr=subprocess.STDOUT)
    for _ in range(90):
        if process.poll() is not None:
            raise RuntimeError("Isolated API exited; inspect its private log")
        try:
            httpx.get("http://127.0.0.1:18012/health", timeout=2)
            break
        except httpx.ConnectError:
            time.sleep(.5)
    else:
        raise RuntimeError("Isolated API not ready")
    history.append({"pid": process.pid, "flags": {key: env[key] for key in flags}})
    save("runtime-handle.json", {"private_root": str(PRIVATE), "api_pid": process.pid, "worktree": str(WT), "postgres": PG, "redis": CACHE})
    private_env = PRIVATE / "environment.json"
    private_env.write_text(json.dumps(env)); os.chmod(private_env, 0o600)
    save("flag-history.json", history)
    return process


try:
    run(["docker", "run", "-d", "--name", PG, "--label", "cygnusx.task=session-lineage", "--env-file", str(pg_env), "-p", "127.0.0.1:55444:5432", image_id("pgvector/pgvector:pg14")], capture_output=True)
    run(["docker", "run", "-d", "--name", CACHE, "--label", "cygnusx.task=session-lineage", "-p", "127.0.0.1:16391:6379", image_id("redis:7-alpine")], capture_output=True)
    for _ in range(90):
        probe = subprocess.run(["docker", "exec", PG, "pg_isready", "-h", "127.0.0.1", "-U", "lineage_test"], capture_output=True)
        if probe.returncode == 0: break
        time.sleep(.5)
    with (OUT / "migration-runtime.log").open("w") as log:
        run([str(WT / ".venv/bin/alembic"), "upgrade", "head"], env=env, cwd=WT, stdout=log, stderr=subprocess.STDOUT)
    os.environ.update(env)
    identities = asyncio.run(seed())
    api = start_api()
    client = httpx.Client(base_url="http://127.0.0.1:18012/api/v1", timeout=30)
    setup = client.post("/auth/setup", json={"username": "lineage_admin", "email": "lineage_admin@invalid.test", "password": password})
    assert setup.status_code == 201, setup.text
    tokens = {}
    for username in ["lineage_owner", "lineage_other", "lineage_denied"]:
        response = client.post("/auth/login", data={"username": username, "password": password})
        response.raise_for_status()
        tokens[username] = response.json()["access_token"]
    client.headers["Authorization"] = "Bearer " + tokens["lineage_owner"]
    project_response = client.post("/projects", json={"name": "lineage-empty-project"})
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()
    evidence = []
    for suffix in ["research-plans", "research-delivery", "delivery-inventory", "capability-status"]:
        for actor, expected in [("anonymous", 401), ("lineage_other", 403), ("lineage_owner", 200)]:
            response = client.get(f"/projects/{project['id']}/{suffix}", headers={"Authorization": "Bearer " + tokens[actor] if actor in tokens else ""})
            assert response.status_code == expected, (suffix, actor, response.status_code, response.text)
            evidence.append({"endpoint": suffix, "actor": actor, "status": response.status_code, "response": response.json()})
    assert next(e["response"] for e in evidence if e["endpoint"] == "research-plans" and e["actor"] == "lineage_owner") == []
    assert next(e["response"] for e in evidence if e["endpoint"] == "research-delivery" and e["actor"] == "lineage_owner")["datasets"] == []
    inventory = next(e["response"] for e in evidence if e["endpoint"] == "delivery-inventory" and e["actor"] == "lineage_owner")
    assert inventory["datasets"] == [] and not inventory["export_enabled"]
    save("part-a-http.json", evidence)
    empty_counts = asyncio.run(counts())
    assert not any(empty_counts.values()), empty_counts
    save("part-a-db-counts.json", empty_counts)
    context = {"owner_username": "lineage_owner", "owner_password": password, "project_id": project["id"], "ids": identities, "base_url": "http://127.0.0.1:18012/api/v1"}
    (PRIVATE / "context.json").write_text(json.dumps(context)); os.chmod(PRIVATE / "context.json", 0o600)
    print("Part A HTTP/PG evidence ready; metadata gate remains false. Handle: " + str(PRIVATE), flush=True)
    approved = False
    while not (PRIVATE / "stop").exists():
        permission = OUT / "metadata-gate-approval.json"
        if not approved and permission.exists() and json.loads(permission.read_text()).get("approved_by_user") is True:
            api.terminate(); api.wait(timeout=20)
            env["DATASET_DISCOVERY_READONLY"] = "true"
            api = start_api()
            approved = True
            print("Explicit user metadata-gate approval applied only to isolated API", flush=True)
        if api.poll() is not None: raise RuntimeError("Isolated API stopped unexpectedly")
        time.sleep(1)
finally:
    if api is not None and api.poll() is None:
        api.terminate(); api.wait(timeout=20)
    for name in [PG, CACHE]: subprocess.run(["docker", "stop", name], capture_output=True)
    save("closure.json", {"api_stopped": api is None or api.poll() is not None, "dedicated_containers_stopped": True, "volumes_retained": True, "existing_deployment_modified": False})

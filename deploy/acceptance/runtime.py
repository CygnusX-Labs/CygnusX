"""Acceptance-only process configuration. No business logic or mocked services."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path


def configure() -> None:
    import yaml

    from cygnusx.core.config import Settings, get_settings

    # Disable .env before constructing Settings (images must not inject credentials).
    Settings.model_config["env_file"] = None
    get_settings.cache_clear()
    settings = get_settings()
    from sqlalchemy.engine import make_url

    url = make_url(settings.database_url)
    expected = ("postgresql", "postgres", 5432, "ri095_acceptance", "project_export_test_ri095")
    actual = (url.get_backend_name(), url.host, url.port, url.username, url.database)
    if os.environ.get("ACCEPTANCE_DISPOSABLE") != "RI095_DISPOSABLE_ONLY" or actual != expected:
        raise RuntimeError("Refusing non-disposable database target")
    for value, database in (
        (settings.celery_broker_url, "1"),
        (settings.celery_result_backend, "2"),
    ):
        parsed = make_url(value)
        if (parsed.drivername, parsed.host, parsed.port, parsed.database) != (
            "redis",
            "redis",
            6379,
            database,
        ):
            raise RuntimeError("Refusing external broker/backend")
    if settings.agent_analysis_write_enabled or settings.agent_download_write_enabled:
        raise RuntimeError("Analysis/download execution must remain closed")
    if settings.deployment_mode != "local" or settings.storage_type != "local":
        raise RuntimeError("Only private local acceptance storage authorized")
    if os.environ.get("ACCEPTANCE_QUEUE") != "ri095_acceptance":
        raise RuntimeError("Invalid queue namespace")
    # Preserve current site registry; override storage explicitly because YAML wins.
    document = yaml.safe_load(Path("/app/data/CygnusX.yaml").read_text())
    document["storage"] = {
        "data_root": "/acceptance-storage",
        "type": "local",
        "users_subdir": "users",
        "shared_subdir": "shared",
        "system_subdir": "system",
    }
    Path(settings.site_content_yaml).write_text(yaml.safe_dump(document, allow_unicode=True))
    from cygnusx.infrastructure.config.storage_config import get_storage_config

    storage = get_storage_config()
    if storage.data_root != "/acceptance-storage" or storage.storage_type != "local":
        raise RuntimeError("Effective storage escaped private volume")
    if not os.access(storage.data_root, os.W_OK):
        raise RuntimeError("Private volume must be writable by UID 10001")
    print(
        json.dumps(
            {
                "target": actual,
                "queue": "ri095_acceptance",
                "storage": storage.data_root,
                "bucket": "UNUSED_LOCAL",
                "flags": {
                    name: getattr(settings, name)
                    for name in (
                        "project_report_write_enabled",
                        "project_report_pdf_enabled",
                        "project_export_enabled",
                        "research_delivery_read_enabled",
                        "agent_analysis_write_enabled",
                        "agent_download_write_enabled",
                    )
                },
            }
        ),
        flush=True,
    )


async def identity() -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from cygnusx.core.config import get_settings

    engine = create_async_engine(get_settings().database_url)
    try:
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        "SELECT current_database(), current_user, inet_server_addr()::text, version()"
                    )
                )
            ).one()
            if row[0:2] != ("project_export_test_ri095", "ri095_acceptance"):
                raise RuntimeError("Database server identity mismatch")
            print(json.dumps({"database_identity": list(row)}), flush=True)
    finally:
        await engine.dispose()


def celery_app():  # type annotations intentionally local to optional runtime dependencies
    from cygnusx.infrastructure.celery_app.celery import celery_app as app

    prefix = "cygnusx.infrastructure.celery_app.tasks."
    app.conf.task_default_queue = "ri095_acceptance"
    app.conf.task_routes = {
        prefix + domain + ".*": {"queue": "ri095_acceptance"}
        for domain in ("project_reports", "project_exports")
    }
    app.conf.beat_schedule = {
        key: value
        for key, value in app.conf.beat_schedule.items()
        if key in ("project-report-reconcile", "project-export-reconcile")
    }
    # Limit the real worker registry to existing report/export tasks.
    app.loader.import_default_modules()
    allowed = {
        prefix + domain + "." + action
        for domain, action in (
            ("project_reports", "generate_project_report"),
            ("project_reports", "reconcile_project_reports"),
            ("project_exports", "generate_project_export"),
            ("project_exports", "reconcile_project_exports"),
        )
    }
    for name in list(app.tasks):
        if name not in allowed:
            app.tasks.pop(name)
    return app


def main() -> None:
    configure()
    asyncio.run(identity())
    role = sys.argv[1]
    if role == "identity":
        return
    if role == "permissions":
        import tempfile

        if (os.getuid(), os.getgid()) != (10001, 10001):
            raise RuntimeError("Unexpected runtime UID/GID")
        for directory in ("/tmp", "/acceptance-storage"):
            with tempfile.NamedTemporaryFile(dir=directory) as probe:
                probe.write(b"ri095-private-write-probe")
                probe.flush()
                os.fsync(probe.fileno())
                probe.seek(0)
                if probe.read() != b"ri095-private-write-probe":
                    raise RuntimeError("Private volume readback failed")
        print(
            json.dumps(
                {
                    "uid": os.getuid(),
                    "gid": os.getgid(),
                    "tmpfs_and_private_volume_write_readback": "PASS_RUNTIME",
                }
            )
        )
        return
    if role == "migrate":
        # In-process Alembic keeps env_file disabled.
        from alembic import command
        from alembic.config import Config

        command.upgrade(Config("/app/alembic.ini"), "head")
        command.current(Config("/app/alembic.ini"), verbose=True)
        return
    if role == "versions":
        for binary in ("pandoc", "typst", "fc-list"):
            try:
                result = subprocess.run(
                    [binary, "--version"] if binary != "fc-list" else [binary],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                print(
                    json.dumps(
                        {
                            "binary": binary,
                            "exit": result.returncode,
                            "stdout": result.stdout,
                            "stderr": result.stderr,
                        }
                    )
                )
            except FileNotFoundError:
                print(json.dumps({"binary": binary, "status": "MISSING"}))
        return
    app = celery_app()
    if role == "worker":
        app.worker_main(["worker", "-Q", "ri095_acceptance", "--concurrency=1", "--loglevel=INFO"])
    elif role == "beat":
        app.start(["beat", "--schedule=/tmp/acceptance-beat", "--loglevel=INFO"])
    elif role == "api":
        import uvicorn

        uvicorn.run("cygnusx.main:app", host="0.0.0.0", port=8000)
    else:
        raise RuntimeError("Unknown acceptance process")


if __name__ == "__main__":
    main()

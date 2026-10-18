"""IAT-R2 dedicated download test worker entrypoint.

Extends the acceptance-only process configuration with a download role: the real
celery app, real task registration (download domain included), and ONLY the
ri095_acceptance queue. Business download execution gate stays closed at the
service layer (require_download_runtime untouched). No production queues.

Run inside the acceptance app container: python /acceptance/runtime_dl.py <role>
"""

from __future__ import annotations

import sys


def configure() -> None:
    import runtime  # reuse the fail-closed acceptance configuration

    runtime.configure()


def celery_app():
    from cygnusx.infrastructure.celery_app.celery import celery_app as app

    prefix = "cygnusx.infrastructure.celery_app.tasks."
    app.conf.task_default_queue = "ri095_acceptance"
    app.conf.task_routes = {
        prefix + domain + ".*": {"queue": "ri095_acceptance"}
        for domain in ("project_reports", "project_exports", "download")
    }
    app.conf.beat_schedule = {
        key: value
        for key, value in app.conf.beat_schedule.items()
        if key
        in ("project-report-reconcile", "project-export-reconcile", "download-task-reconcile")
    }
    app.loader.import_default_modules()
    allowed = {
        prefix + domain + "." + action
        for domain, action in (
            ("project_reports", "generate_project_report"),
            ("project_reports", "reconcile_project_reports"),
            ("project_exports", "generate_project_export"),
            ("project_exports", "reconcile_project_exports"),
            ("download", "run_download"),
            ("download", "reconcile_downloads"),
        )
    }
    for name in list(app.tasks):
        if name not in allowed:
            app.tasks.pop(name)
    return app


def main() -> None:
    configure()
    role = sys.argv[1]
    app = celery_app()
    if role == "inspect":
        print("registered:", sorted(app.tasks))
        return
    if role == "worker":
        app.worker_main(["worker", "-Q", "ri095_acceptance", "--concurrency=1", "--loglevel=INFO"])
    elif role == "beat":
        app.start(["beat", "--schedule=/tmp/acceptance-beat-dl", "--loglevel=INFO"])
    else:
        raise RuntimeError("Unknown download-worker role")


if __name__ == "__main__":
    main()

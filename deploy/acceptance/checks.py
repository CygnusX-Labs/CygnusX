"""Offline regression for fail-closed configuration, no runtime PASS claims."""

import copy
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType, SimpleNamespace

import control


def check_download_worker_registry():
    import runtime_dl

    prefix = "cygnusx.infrastructure.celery_app.tasks."
    app = SimpleNamespace(
        conf=SimpleNamespace(
            task_default_queue="default",
            task_routes={},
            beat_schedule={
                "project-report-reconcile": {},
                "project-export-reconcile": {},
                "download-task-reconcile": {},
                "unrelated-cleanup": {},
            },
        ),
        tasks={"unrelated.task": object()},
    )

    def import_registered_tasks():
        app.tasks.update(
            {
                prefix + "project_reports.generate_project_report": object(),
                prefix + "project_reports.reconcile_project_reports": object(),
                prefix + "project_exports.generate_project_export": object(),
                prefix + "project_exports.reconcile_project_exports": object(),
                prefix + "download.run_download": object(),
                prefix + "download.reconcile_downloads": object(),
                prefix + "chat.unrelated": object(),
            }
        )

    app.loader = SimpleNamespace(import_default_modules=import_registered_tasks)
    celery_module = ModuleType("cygnusx.infrastructure.celery_app.celery")
    celery_module.celery_app = app
    original = sys.modules.get(celery_module.__name__)
    sys.modules[celery_module.__name__] = celery_module
    try:
        configured = runtime_dl.celery_app()
    finally:
        if original is None:
            del sys.modules[celery_module.__name__]
        else:
            sys.modules[celery_module.__name__] = original

    expected = {
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
    assert configured.conf.task_default_queue == "ri095_acceptance"
    assert set(configured.tasks) == expected
    assert set(configured.conf.beat_schedule) == {
        "project-report-reconcile",
        "project-export-reconcile",
        "download-task-reconcile",
    }
    assert set(configured.conf.task_routes) == {
        prefix + domain + ".*" for domain in ("project_reports", "project_exports", "download")
    }
    assert all(
        route == {"queue": "ri095_acceptance"} for route in configured.conf.task_routes.values()
    )
    print("PASS_STATIC: download worker registry restricted to ri095_acceptance tasks/Beat")


def main():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "acceptance.env"
        values = {
            f"ACCEPTANCE_{key}_IMAGE": "example.invalid/image@sha256:" + "a" * 64
            for key in control.IMAGES
        }
        values.update(
            {f"ACCEPTANCE_{key}": str(index + 1) * 64 for index, key in enumerate(control.SECRETS)}
        )
        values.update({f"ACCEPTANCE_{key}": "false" for key in control.FLAGS})
        values["ACCEPTANCE_BROWSER_SECCOMP"] = str(control.ROOT / "seccomp-browser.json")

        def write():
            path.write_text("".join(f"{key}={value}\n" for key, value in values.items()))
            path.chmod(0o600)

        write()
        control.load_env(path)
        command = [
            "docker",
            "compose",
            "--env-file",
            str(path),
            "-f",
            str(control.ROOT / "compose.yml"),
            "--profile",
            "browser",
            "config",
            "--format",
            "json",
        ]
        result = subprocess.run(
            command, env={"PATH": os.environ["PATH"]}, capture_output=True, text=True, check=True
        )
        import json

        config = json.loads(result.stdout)
        control.validate(config)
        cases = [
            (
                "published DB",
                lambda c: c["services"]["postgres"].update(ports=[{"published": "5432"}]),
            ),
            (
                "external DB",
                lambda c: c["services"]["api"]["environment"].update(
                    DATABASE_URL="postgresql://production/db"
                ),
            ),
            (
                "analysis writes",
                lambda c: c["services"]["worker"]["environment"].update(
                    AGENT_ANALYSIS_WRITE_ENABLED="true"
                ),
            ),
            ("external network", lambda c: c["networks"]["isolated"].update(external=True)),
            (
                "socket mount",
                lambda c: c["services"]["worker"]["volumes"].append(
                    {
                        "type": "bind",
                        "source": "/var/run/docker.sock",
                        "target": "/var/run/docker.sock",
                        "read_only": True,
                    }
                ),
            ),
            (
                "split tmpfs",
                lambda c: c["services"]["worker"].update(
                    tmpfs=["/tmp:uid=10001", "gid=10001", "mode=1777"]
                ),
            ),
            (
                "wrong UID",
                lambda c: c["services"]["frontend"].update(user="0:0"),
            ),
        ]
        for name, mutate in cases:
            changed = copy.deepcopy(config)
            mutate(changed)
            try:
                control.validate(changed)
            except ValueError:
                print("PASS_STATIC reject:", name)
            else:
                raise AssertionError(name)
        values["DATABASE_URL"] = "postgresql://production/db"
        write()
        try:
            control.load_env(path)
        except ValueError:
            print("PASS_STATIC reject: unapproved env variable")
        else:
            raise AssertionError("host DATABASE_URL accepted")
        print("PASS_STATIC: Compose renders, eight rejection checks; runtime NOT_RUN")
        check_download_worker_registry()


if __name__ == "__main__":
    main()

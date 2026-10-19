"""Fail-closed Compose controller; never loads host .env or forwards host secrets."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = "cygnusx-20261019-235848-bootstrap"
IMAGES = ("APP", "FRONTEND", "POSTGRES", "REDIS", "BROWSER")
SECRETS = ("DB_PASSWORD", "REDIS_PASSWORD", "APP_SECRET", "JWT_SECRET")
FLAGS = ("READS", "WRITES", "PDF")


def load_env(path: Path) -> dict[str, str]:
    if path.stat().st_mode & 0o077:
        raise ValueError("Acceptance env must have mode 600")
    values = {}
    allowed = {"ACCEPTANCE_" + key + "_IMAGE" for key in IMAGES}
    allowed |= {"ACCEPTANCE_" + key for key in (*SECRETS, *FLAGS)}
    allowed.add("ACCEPTANCE_BROWSER_SECCOMP")
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or key not in allowed or key in values:
            raise ValueError("Unknown or duplicate acceptance variable")
        values[key] = value
    for key in SECRETS:
        if not re.fullmatch(r"[a-f0-9]{64}", values.get("ACCEPTANCE_" + key, "")):
            raise ValueError("Supply four independently generated 32-byte hex secrets")
    if len({values["ACCEPTANCE_" + key] for key in SECRETS}) != 4:
        raise ValueError("Secrets must be independent")
    for key in IMAGES:
        value = values.get("ACCEPTANCE_" + key + "_IMAGE", "")
        if not re.fullmatch(r"[a-zA-Z0-9_./:-]+@sha256:[a-f0-9]{64}", value):
            raise ValueError("All images must use reviewed sha256 digests")
    for key in FLAGS:
        if values.get("ACCEPTANCE_" + key) not in {"true", "false"}:
            raise ValueError("Explicit boolean flags required")
    if values["ACCEPTANCE_WRITES"] == "true" and values["ACCEPTANCE_READS"] != "true":
        raise ValueError("Writes require read prerequisites")
    if values["ACCEPTANCE_PDF"] == "true" and values["ACCEPTANCE_WRITES"] != "true":
        raise ValueError("PDF requires write prerequisites")
    seccomp = values.get("ACCEPTANCE_BROWSER_SECCOMP", "")
    if not re.fullmatch(r"/[A-Za-z0-9_./-]*seccomp-browser\.json", seccomp):
        raise ValueError("Browser seccomp must be the reviewed narrow profile path")
    return values


def validate(config: dict) -> None:
    if config.get("name") != PROJECT:
        raise ValueError("Unexpected Compose project")
    services = config["services"]
    if set(services) != {
        "postgres",
        "redis",
        "migrate",
        "api",
        "worker",
        "beat",
        "frontend",
        "browser",
    }:
        raise ValueError("Unexpected services")
    if set(config["networks"]) != {"isolated"} or not config["networks"]["isolated"].get(
        "internal"
    ):
        raise ValueError("Internal network required")
    if any(
        item.get("external") for item in [*config["networks"].values(), *config["volumes"].values()]
    ):
        raise ValueError("External resource forbidden")
    for name, service in services.items():
        if (
            service.get("ports")
            or service.get("privileged")
            or service.get("network_mode")
            or service.get("env_file")
            or service.get("container_name")
        ):
            raise ValueError("Shared access or published port forbidden")
        if set(service["networks"]) != {"isolated"}:
            raise ValueError("Unexpected service network")
        if name in {"api", "worker", "beat", "migrate", "frontend", "browser"}:
            if service.get("user") != "10001:10001":
                raise ValueError("Acceptance process must use UID/GID 10001")
            if service.get("tmpfs") != ["/tmp:uid=10001,gid=10001,mode=1777"]:
                raise ValueError("tmpfs must be one complete quoted mount specification")
        if name == "browser":
            if service.get("cap_drop") != ["ALL"]:
                raise ValueError("Browser must drop all capabilities")
            security = service.get("security_opt") or []
            if not any(opt.endswith("/seccomp-browser.json") for opt in security):
                raise ValueError("Browser must use the reviewed narrow seccomp profile")
            if not any(opt == "no-new-privileges:true" for opt in security):
                raise ValueError("Browser must forbid new privileges")
        for volume in service.get("volumes", []):
            if volume["type"] == "bind" and (
                Path(volume["source"]).resolve() != ROOT or not volume.get("read_only")
            ):
                raise ValueError("Host data or socket mount forbidden")
        if name in {"api", "worker", "beat", "migrate"}:
            env = service["environment"]
            if service.get("user") != "10001:10001":
                raise ValueError("Application UID must be 10001")
            if (env["STORAGE_TYPE"], env["DEPLOYMENT_MODE"], env["STORAGE_S3_BUCKET"]) != (
                "local",
                "local",
                "ri095-acceptance-unused",
            ):
                raise ValueError("Unexpected storage backend or bucket")
            for field, database in (("CELERY_BROKER_URL", 1), ("CELERY_RESULT_BACKEND", 2)):
                redis_password = env["REDIS_PASSWORD"]
                if env[field] != f"redis://:{redis_password}@redis:6379/{database}":
                    raise ValueError("Unexpected broker/backend target")
            password = env["POSTGRES_PASSWORD"]
            if (
                env["DATABASE_URL"]
                != f"postgresql+asyncpg://ri095_acceptance:{password}@postgres:5432/project_export_test_ri095"
            ):
                raise ValueError("Unexpected database target")
            if (
                env["ACCEPTANCE_QUEUE"] != "ri095_acceptance"
                or env["STORAGE_PATH"] != "/acceptance-storage"
            ):
                raise ValueError("Unexpected storage/queue namespace")
            for flag in (
                "AGENT_ANALYSIS_WRITE_ENABLED",
                "AGENT_DOWNLOAD_WRITE_ENABLED",
                "RESEARCH_DELIVERY_WRITE_ENABLED",
            ):
                if env[flag] != "false":
                    raise ValueError("Protected execution flag must stay closed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=["preflight", "start", "stop", "logs", "versions", "permissions", "browser-probe"],
    )
    parser.add_argument("--env", required=True, type=Path)
    args = parser.parse_args()
    values = load_env(args.env.resolve())
    # DOCKER_HOST/CONTEXT, cloud credentials, DATABASE_URL and root .env never inherited.
    env = {"PATH": os.environ["PATH"], **values}
    base = [
        "docker",
        "--host",
        "unix:///var/run/docker.sock",
        "compose",
        "--project-name",
        PROJECT,
        "--env-file",
        str(args.env.resolve()),
        "-f",
        str(ROOT / "compose.yml"),
        "--profile",
        "browser",
    ]
    result = subprocess.run(
        [*base, "config", "--format", "json"], env=env, capture_output=True, text=True
    )
    if result.returncode:
        raise SystemExit(
            "BLOCKED: Compose configuration could not be rendered (no secrets printed)"
        )
    validate(json.loads(result.stdout))
    print("PASS_STATIC: isolated Compose targets; not runtime acceptance", flush=True)
    if args.action == "preflight":
        return
    subprocess.run(
        ["docker", "--host", "unix:///var/run/docker.sock", "version"], env=env, check=True
    )

    def run(*command: str) -> None:
        subprocess.run([*base, *command], env=env, check=True)

    if args.action == "start":
        # No pull/build: reviewed images must already exist locally.
        run("up", "-d", "--pull", "never", "--wait", "postgres", "redis")
        run("run", "--rm", "--no-deps", "--pull", "never", "migrate", "identity")
        run("run", "--rm", "--no-deps", "--pull", "never", "migrate")
        run("up", "-d", "--pull", "never", "api", "worker", "beat", "frontend")
    elif args.action == "stop":
        run("stop")  # retain all evidence and volumes; never down -v
    elif args.action == "logs":
        run("logs", "--no-color")
    elif args.action == "versions":
        run("images", "--format", "json")
        run("run", "--rm", "--no-deps", "--pull", "never", "migrate", "versions")
    elif args.action == "permissions":
        run("run", "--rm", "--no-deps", "--pull", "never", "migrate", "permissions")
    else:
        run("run", "--rm", "--no-deps", "--pull", "never", "browser")


if __name__ == "__main__":
    main()

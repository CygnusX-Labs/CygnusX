"""Read-only S3-E1 dependency probe. Never certifies isolation or starts a process."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
from pathlib import Path
from typing import cast

_CAPABILITIES = {"CAP_SYS_ADMIN": 21, "CAP_NET_ADMIN": 12, "CAP_BPF": 39, "CAP_PERFMON": 38}


def _status_fields() -> dict[str, str]:
    status = Path("/proc/self/status")
    selected: dict[str, str] = {}
    if status.exists():
        for line in status.read_text().splitlines():
            key, _, value = line.partition(":")
            if key in {"Uid", "Gid", "CapEff", "CapBnd", "NoNewPrivs", "Seccomp"}:
                selected[key] = value.strip()
    return selected


def _capability_report(status: dict[str, str]) -> dict[str, dict[str, bool]]:
    report: dict[str, dict[str, bool]] = {}
    for source in ("CapEff", "CapBnd"):
        raw = status.get(source, "0")
        try:
            mask = int(raw, 16)
        except ValueError:
            mask = 0
        report[source] = {name: bool(mask & (1 << bit)) for name, bit in _CAPABILITIES.items()}
    return report


def _current_cgroup_path() -> str | None:
    path = Path("/proc/self/cgroup")
    if not path.exists():
        return None
    for line in path.read_text().splitlines():
        hierarchy, _, relative = line.partition(":")
        if hierarchy == "0" and relative.startswith(":"):
            return relative[1:] or "/"
    return None


def _mount_for(target: str) -> dict[str, object]:
    target_path = Path(target).resolve()
    mountinfo = Path("/proc/self/mountinfo")
    candidates: list[tuple[int, dict[str, object]]] = []
    if mountinfo.exists():
        for line in mountinfo.read_text().splitlines():
            left, separator, right = line.partition(" - ")
            if not separator:
                continue
            fields = left.split()
            details = right.split()
            if len(fields) < 6 or len(details) < 3:
                continue
            mountpoint = Path(fields[4].replace("\\040", " "))
            try:
                target_path.relative_to(mountpoint)
            except ValueError:
                continue
            options = sorted(set(fields[5].split(",") + details[2].split(",")))
            project_quota_visible = bool(
                details[0] == "xfs" and {"pquota", "prjquota"}.intersection(options)
                or details[0] == "ext4" and "prjquota" in options
            )
            candidates.append(
                (
                    len(str(mountpoint)),
                    {
                        "mountpoint": str(mountpoint),
                        "filesystem": details[0],
                        "options": options,
                        "xfs_project_quota_option": bool(
                            details[0] == "xfs" and {"pquota", "prjquota"}.intersection(options)
                        ),
                        "supported_project_quota_option": project_quota_visible,
                    },
                )
            )
    if not candidates:
        return {"filesystem": "UNKNOWN", "options": [], "xfs_project_quota_option": False}
    return max(candidates, key=lambda item: item[0])[1]


def inspect_dependencies(
    workdir_root: Path = Path("/tmp"),
    cgroup_root: Path = Path("/sys/fs/cgroup"),
) -> dict[str, object]:
    selected = _status_fields()
    controllers_path = cgroup_root / "cgroup.controllers"
    namespaces = {
        name: Path(f"/proc/self/ns/{name}").exists()
        for name in ("cgroup", "ipc", "mnt", "net", "pid", "user", "uts")
    }
    tools = ("bpftool", "nft", "iptables", "ip", "unshare", "xfs_quota", "setpriv")
    cgroup = {
        "v2_visible": controllers_path.is_file(),
        "current_path": _current_cgroup_path(),
        "controllers": (
            controllers_path.read_text().split() if controllers_path.is_file() else []
        ),
        "root_writable_hint": os.access(cgroup_root, os.W_OK),
        "kill_file_visible": (cgroup_root / "cgroup.kill").is_file(),
    }
    filesystems = {
        target: _mount_for(target) for target in ("/", "/tmp", str(workdir_root))
    }
    visible_checks = {
        "cgroup_v2": bool(cgroup["v2_visible"]),
        "writable_cgroup_subtree_hint": bool(cgroup["root_writable_hint"]),
        "cgroup_kill_visible": bool(cgroup["kill_file_visible"]),
        "network_namespace_visible": namespaces["net"],
        "workdir_exists_and_writable": workdir_root.is_dir() and os.access(workdir_root, os.W_OK),
        "workdir_project_quota_mount_option_visible": bool(
            filesystems[str(workdir_root)]["supported_project_quota_option"]
        ),
    }
    missing_visible_checks = [name for name, passed in visible_checks.items() if not passed]
    return {
        "scope": "HOST_READ_ONLY_NOT_WORKER",
        "status": (
            "VISIBLE_PREREQUISITES_MISSING"
            if missing_visible_checks
            else "VISIBLE_PREREQUISITES_ONLY_NOT_CERTIFIED"
        ),
        "runtime_certified": False,
        "kernel": {"release": platform.release(), "machine": platform.machine()},
        "process": selected,
        "capabilities": _capability_report(selected),
        "cgroup": cgroup,
        "cgroup_root": str(cgroup_root),
        "namespaces_visible": namespaces,
        "workdir_root": str(workdir_root),
        "writable_filesystems": filesystems,
        "visible_preflight": {
            "checks": visible_checks,
            "missing": missing_visible_checks,
            "limits": [
                "visibility and access hints do not prove cgroup delegation or cgroup.kill behavior",
                "mount options do not prove project quota accounting or hard-limit enforcement",
                "namespace handles do not prove namespace creation is permitted",
                "this probe does not test network hooks, atomic RX accounting, process launch or cleanup",
            ],
        },
        "inspection_tools": {name: shutil.which(name) for name in tools},
        "docker_socket_visible": Path("/var/run/docker.sock").exists(),
        "worker_control_client": "IMPLEMENTED_UNVERIFIED",
        "supervisor_server": "NOT_IMPLEMENTED",
        "host_enforcement_runtime": "NOT_IMPLEMENTED",
        "network_enforcement": "NOT_TESTED_BY_READ_ONLY_PROBE",
        "atomic_rx_accounting": "NOT_TESTED",
        "filesystem_quota": "NOT_TESTED_BY_READ_ONLY_PROBE",
        "worker_loss_cleanup": "NOT_TESTED",
        "required_external_dependencies": [
            "authorized isolated non-production Worker and controlled HTTP origin",
            "authenticated supervisor independent of Worker with bounded lease",
            "per-Task cgroup, network/mount namespaces and immutable CLI digest",
            "unbypassable IPv4/IPv6 egress with atomic ingress byte admission",
            "per-Task block/inode hard quota covering every writable path",
            "trusted server admission and durable budget reference resolution",
            "existing Task/FileRegistry/Dataset reconciliation environment",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--workdir-root",
        type=Path,
        default=Path("/tmp"),
        help="existing Supervisor workdir mount to inspect without changing it",
    )
    parser.add_argument(
        "--cgroup-root",
        type=Path,
        default=Path("/sys/fs/cgroup"),
        help="delegated cgroup v2 subtree root to inspect without changing it",
    )
    parser.add_argument(
        "--require-visible-prerequisites",
        action="store_true",
        help="exit 2 if required host prerequisites are visibly absent; never certifies enforcement",
    )
    args = parser.parse_args()
    report = inspect_dependencies(args.workdir_root, args.cgroup_root)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    preflight = cast(dict[str, object], report["visible_preflight"])
    missing = cast(list[str], preflight["missing"])
    if args.require_visible_prerequisites and missing:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

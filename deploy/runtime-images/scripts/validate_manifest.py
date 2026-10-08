#!/usr/bin/env python3
"""Validate a built tool manifest against one runtime profile declaration."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml

_VERSION_RE = re.compile(r"(?<![A-Za-z0-9.])v?\d+(?:\.\d+){1,3}(?!\d)")


def _version_tuple(value: str) -> tuple[int, ...]:
    matches = _VERSION_RE.findall(value)
    if not matches:
        return ()
    return tuple(int(part) for part in matches[-1].lstrip("v").split("."))


def _compare_versions(
    actual: tuple[int, ...], required: tuple[int, ...]
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    width = max(len(actual), len(required))
    return actual + (0,) * (width - len(actual)), required + (0,) * (width - len(required))


def _satisfies(actual: str, requirement: str) -> bool:
    requirement = str(requirement).strip()
    if not requirement or requirement == "installed":
        return True
    actual_version = _version_tuple(actual)
    required_version = _version_tuple(requirement)
    if not actual_version or not required_version:
        return False
    actual_version, required_version = _compare_versions(actual_version, required_version)
    if requirement.startswith(">="):
        return actual_version >= required_version
    if requirement.startswith("<="):
        return actual_version <= required_version
    if requirement.startswith(">"):
        return actual_version > required_version
    if requirement.startswith("<"):
        return actual_version < required_version
    return actual_version == required_version


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--registry", type=Path, default=Path("data/ai/runtime_images.yaml"))
    args = parser.parse_args()

    raw: dict[str, Any] = yaml.safe_load(args.registry.read_text(encoding="utf-8")) or {}
    profiles = raw.get("profiles") or {}
    profile = profiles.get(args.profile)
    if not isinstance(profile, dict):
        raise SystemExit(f"unknown runtime profile: {args.profile}")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    tools = {
        str(item.get("name")): item
        for item in manifest.get("tools", [])
        if isinstance(item, dict)
    }
    missing: list[str] = []
    conflicts: list[str] = []
    for name, requirement in (profile.get("software") or {}).items():
        entry = tools.get(str(name))
        if entry is None or entry.get("probe_status") != "ok":
            missing.append(str(name))
            continue
        if not _satisfies(str(entry.get("version") or ""), str(requirement)):
            conflicts.append(f"{name}: {entry.get('version')} does not satisfy {requirement}")
    if missing or conflicts:
        details = [*(f"missing/unverified: {item}" for item in missing), *conflicts]
        raise SystemExit("BUILD FAILED - " + "; ".join(details))
    print(f"manifest validation passed: {args.profile}, {len(tools)} tools, {manifest.get('manifest_digest')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Generate a small, verified tool manifest during image construction."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

_VERSION_RE = re.compile(r"(?<!\d)\d+(?:\.\d+){1,3}(?!\d)")


def _extract_version(output: str, fallback: str = "installed") -> str:
    """Extract a package version from R output, which may include prompts."""
    lines = output.splitlines()
    preferred = [
        line
        for line in lines
        if re.search(r"(?:version|qualimap|featurecounts|macs|bowtie|samtools)", line, re.I)
    ]
    matches = _VERSION_RE.findall("\n".join(preferred or lines))
    return matches[-1][:200] if matches else fallback


def probe(name: str, command: str | None = None) -> dict[str, str]:
    executable = shutil.which(command or name)
    if executable is None:
        return {"name": name, "probe_status": "missing"}
    try:
        # Bioinformatics CLIs are inconsistent: featureCounts uses ``-v``
        # and Java launchers such as Qualimap may print the version on help.
        result = None
        raw_output = ""
        for argument in ("--version", "-v", "version", "--help"):
            candidate = subprocess.run(
                [executable, argument],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            candidate_output = (candidate.stdout or candidate.stderr).strip()
            candidate_version = _extract_version(candidate_output, "")
            is_error = "unrecognized option" in candidate_output.lower()
            if candidate_output and candidate_version and not is_error:
                result, raw_output = candidate, candidate_output
            if candidate.returncode == 0 and candidate_version and not is_error:
                break
        version = _extract_version(raw_output, "unknown")
        status = "ok" if result is not None and _extract_version(raw_output, "") else "version_probe_failed"
    except (OSError, subprocess.SubprocessError) as exc:
        version = str(exc)[:200]
        status = "version_probe_failed"
    return {
        "name": name,
        "probe_type": "cli",
        "version": version,
        "path": executable,
        "source": "micromamba",
        "probe_status": status,
    }


def probe_python_import(name: str, module: str) -> dict[str, str]:
    executable = shutil.which("python")
    if executable is None:
        return {"name": name, "probe_status": "missing"}
    try:
        result = subprocess.run(
            [executable, "-c", f"import {module}; print(getattr({module}, '__version__', 'installed'))"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        output = (result.stdout or result.stderr).strip().splitlines()
        return {
            "name": name,
            "probe_type": "python_import",
            "probe_target": module,
            "version": output[0][:200] if output else "installed",
            "path": executable,
            "source": "micromamba",
            "probe_status": "ok" if result.returncode == 0 else "import_probe_failed",
        }
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "name": name,
            "probe_type": "python_import",
            "probe_target": module,
            "probe_status": "import_probe_failed",
            "version": str(exc)[:200],
        }


def probe_r_library(name: str, package: str) -> dict[str, str]:
    executable = shutil.which("R")
    if executable is None:
        return {"name": name, "probe_status": "missing"}
    try:
        result = subprocess.run(
            [
                executable,
                "--vanilla",
                "--slave",
                "-e",
                f"if (!requireNamespace('{package}', quietly=TRUE)) quit(status=1); cat(as.character(packageVersion('{package}')))",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        raw_output = (result.stdout or result.stderr).strip()
        return {
            "name": name,
            "probe_type": "r_library",
            "probe_target": package,
            "version": _extract_version(raw_output, "unknown"),
            "path": executable,
            "source": "micromamba",
            "probe_status": (
                "ok"
                if result.returncode == 0 and _extract_version(raw_output, "")
                else "library_probe_failed"
            ),
        }
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "name": name,
            "probe_type": "r_library",
            "probe_target": package,
            "probe_status": "library_probe_failed",
            "version": str(exc)[:200],
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base", type=Path)
    parser.add_argument(
        "--tool",
        action="append",
        default=[],
        metavar="NAME[:COMMAND]",
        help="Tool name and optional executable name.",
    )
    parser.add_argument(
        "--python-import",
        action="append",
        default=[],
        metavar="NAME:MODULE",
        help="Verify a Python module import and record its version.",
    )
    parser.add_argument(
        "--r-library",
        action="append",
        default=[],
        metavar="NAME:PACKAGE",
        help="Verify an R package namespace and record its version.",
    )
    args = parser.parse_args()

    entries: list[dict[str, str]] = []
    if args.base and args.base.is_file():
        base = json.loads(args.base.read_text(encoding="utf-8"))
        entries.extend(base.get("tools", []))
    known = {entry.get("name") for entry in entries}
    for declaration in args.tool:
        name, separator, command = declaration.partition(":")
        if name in known:
            continue
        entries.append(probe(name, command if separator else None))
        known.add(name)
    for declaration in args.python_import:
        name, separator, module = declaration.partition(":")
        if not separator or name in known:
            continue
        entries.append(probe_python_import(name, module))
        known.add(name)
    for declaration in args.r_library:
        name, separator, package = declaration.partition(":")
        if not separator or name in known:
            continue
        entries.append(probe_r_library(name, package))
        known.add(name)

    manifest = {
        "schema_version": 1,
        "profile": args.profile,
        "image": args.image,
        "generated_by": "render_tools_manifest.py",
        "tools": entries,
    }
    payload = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    manifest["manifest_digest"] = f"sha256:{digest}"
    payload = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    args.output.write_text(payload, encoding="utf-8")
    missing = [
        entry["name"] for entry in entries if entry.get("probe_status") != "ok"
    ]
    print(f"{len(entries)} tools verified -> {args.output} sha256:{digest}")
    if missing:
        raise SystemExit(f"BUILD FAILED - missing or unverified tools: {', '.join(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Backfill runtime registry digests from built image manifests.

The registry remains unchanged unless ``--write`` is supplied. A manifest can
be read from a local file for release pipelines that export image contents, or
from a Docker image using a read-only ``docker run`` invocation.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_PROFILE_BLOCK_RE = re.compile(
    r"(?ms)^(  (?P<profile>[A-Za-z0-9_-]+):\n)(?P<body>(?:(?!^  [A-Za-z0-9_-]+:\n).)*)"
)
_DIGEST_LINE_RE = re.compile(r"(?m)^(    tools_manifest_digest:\s*).*$")


def _parse_assignments(values: list[str], kind: str) -> dict[str, str]:
    assignments: dict[str, str] = {}
    for value in values:
        profile, separator, source = value.partition("=")
        if not separator or not profile or not source:
            raise SystemExit(f"{kind} must use PROFILE=VALUE: {value}")
        if profile in assignments:
            raise SystemExit(f"duplicate {kind} profile: {profile}")
        assignments[profile] = source
    return assignments


def _manifest_digest(payload: str, source: str) -> str:
    try:
        manifest: dict[str, Any] = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid manifest from {source}: {exc}") from exc
    digest = str(manifest.get("manifest_digest") or "")
    if not _DIGEST_RE.fullmatch(digest):
        raise SystemExit(f"invalid manifest_digest from {source}: {digest!r}")
    return digest


def _read_image_manifest(image: str) -> str:
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--entrypoint",
            "cat",
            image,
            "/opt/agent-tools.json",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()[-500:]
        raise SystemExit(f"unable to read manifest from image {image}: {detail}")
    return result.stdout


def _replace_digest(text: str, profile: str, digest: str) -> str:
    match = next(
        (item for item in _PROFILE_BLOCK_RE.finditer(text) if item.group("profile") == profile),
        None,
    )
    if match is None:
        raise SystemExit(f"profile not found in registry: {profile}")
    body = match.group("body")
    updated_body, count = _DIGEST_LINE_RE.subn(rf"\g<1>{digest}", body, count=1)
    if count != 1:
        raise SystemExit(f"tools_manifest_digest not found in profile: {profile}")
    return text[: match.start("body")] + updated_body + text[match.end("body") :]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, default=Path("data/ai/runtime_images.yaml"))
    parser.add_argument("--mapping", type=Path, help="optional deployment image mapping to update")
    parser.add_argument("--manifest", action="append", default=[], metavar="PROFILE=PATH")
    parser.add_argument("--image", action="append", default=[], metavar="PROFILE=IMAGE")
    parser.add_argument("--write", action="store_true", help="write digests into the registry")
    args = parser.parse_args()

    manifests = _parse_assignments(args.manifest, "--manifest")
    images = _parse_assignments(args.image, "--image")
    overlap = set(manifests) & set(images)
    if overlap:
        raise SystemExit(f"profile supplied by both --manifest and --image: {sorted(overlap)}")
    if not manifests and not images:
        raise SystemExit("provide at least one --manifest PROFILE=PATH or --image PROFILE=IMAGE")

    registry_text = args.registry.read_text(encoding="utf-8")
    digests: dict[str, str] = {}
    for profile, path_value in manifests.items():
        path = Path(path_value)
        digests[profile] = _manifest_digest(path.read_text(encoding="utf-8"), str(path))
    for profile, image in images.items():
        digests[profile] = _manifest_digest(_read_image_manifest(image), image)

    updated = registry_text
    for profile, digest in digests.items():
        updated = _replace_digest(updated, profile, digest)
        print(f"{profile}: {digest}")
    if args.write:
        args.registry.write_text(updated, encoding="utf-8")
        print(f"updated {args.registry}")
        if args.mapping:
            mapping_text = args.mapping.read_text(encoding="utf-8")
            for profile, digest in digests.items():
                mapping_text = _replace_digest(mapping_text, profile, digest)
            args.mapping.write_text(mapping_text, encoding="utf-8")
            print(f"updated {args.mapping}")
    else:
        print("dry-run: pass --write to update the registry")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

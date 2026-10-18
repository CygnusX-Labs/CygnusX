"""Standalone offline ZIP verifier; Python standard library only, never extracts files.

Run: python verify_project_delivery.py project.zip
Archive integrity does not establish scientific reproducibility or authenticity.
"""

from __future__ import annotations

import hashlib
import json
import stat
import sys
import zipfile
from pathlib import Path
from typing import Any, BinaryIO


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def safe_member(name: str) -> bool:
    return (
        bool(name)
        and not name.startswith("/")
        and "\\" not in name
        and ":" not in name
        and not any(part in {"", ".", ".."} for part in name.split("/"))
        and not any(ord(c) < 32 for c in name)
    )


def strict_json(content: bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    return json.loads(
        content,
        object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")),
    )


def verify_archive(
    source: str | Path | BinaryIO, *, max_bytes: int = 256 * 1024**2, max_files: int = 1002
) -> dict[str, Any]:
    with zipfile.ZipFile(source) as archive:
        infos = archive.infolist()
        names = [i.filename for i in infos]
        if len(infos) > max_files or len(names) != len(set(names)):
            raise ValueError("Duplicate members or file budget exceeded")
        if sum(i.file_size for i in infos) > max_bytes:
            raise ValueError("Expanded ZIP budget exceeded")
        for info in infos:
            mode = info.external_attr >> 16
            if (
                not safe_member(info.filename)
                or info.is_dir()
                or (stat.S_IFMT(mode) not in {0, stat.S_IFREG})
                or info.flag_bits & 1
            ):
                raise ValueError("Unsafe ZIP member")
        document = strict_json(archive.read("ProjectDeliveryManifest.json"))
        if not isinstance(document, dict):
            raise ValueError("Manifest object required")
        manifest = document["manifest"]
        if (
            manifest["schema_version"] not in {"cygnusx.project_delivery.v1", "cygnusx.project_delivery.v2"}
            or manifest["digest_policy"] != "sorted_utf8_json.v1"
        ):
            raise ValueError("Unsupported manifest version")
        if hashlib.sha256(canonical(manifest)).hexdigest() != document["manifest_digest"]:
            raise ValueError("Manifest digest mismatch")
        files = manifest["files"]
        declared = [f["path"] for f in files]
        if len(declared) != len(set(declared)) or set(names) != set(declared) | {
            "ProjectDeliveryManifest.json",
            "checksums.sha256",
        }:
            raise ValueError("Archive coverage mismatch")
        if set(declared) & {"ProjectDeliveryManifest.json", "checksums.sha256"}:
            raise ValueError("Self-referential manifest")
        checksums = {}
        for item in files:
            name = item["path"]
            h = hashlib.sha256()
            size = 0
            with archive.open(name) as stream:
                while chunk := stream.read(1024 * 1024):
                    h.update(chunk)
                    size += len(chunk)
                    if size > item["size"] or size > max_bytes:
                        raise ValueError("Member budget exceeded")
            if size != item["size"] or h.hexdigest() != item["sha256"]:
                raise ValueError("File fingerprint mismatch")
            checksums[name] = h.hexdigest()
        checksums["ProjectDeliveryManifest.json"] = hashlib.sha256(
            archive.read("ProjectDeliveryManifest.json")
        ).hexdigest()
        expected = "".join(f"{checksums[name]}  {name}\n" for name in sorted(checksums))
        if archive.read("checksums.sha256") != expected.encode():
            raise ValueError("Checksums coverage mismatch")
        return document


if __name__ == "__main__":
    verify_archive(sys.argv[1])
    print("PASS: archive bytes verified; scientific reproduction NOT_RUN")

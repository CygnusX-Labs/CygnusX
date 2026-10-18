"""Build and verify a bounded, offline research delivery package."""

from __future__ import annotations

import hashlib
import json
import re
import stat
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Literal
from uuid import UUID, uuid4

from cygnusx.application.schemas.report_delivery import DeliveryFile, EvidenceManifest
from cygnusx.application.schemas.report_snapshot import ReportSnapshot


@dataclass(frozen=True)
class DeliveryInput:
    logical_name: str
    content: bytes | None
    file_type: str
    source_object: str
    generation: Literal["reused", "rendered", "generated"] = "reused"
    original_artifact_id: UUID | None = None


@dataclass(frozen=True)
class DeliveryBuild:
    package_id: UUID
    directory: Path
    zip_path: Path
    manifest: EvidenceManifest


def _safe_name(name: str) -> str:
    path = PurePosixPath(name)
    if (
        path.is_absolute()
        or ".." in path.parts
        or not name
        or "\\" in name
        or ":" in name
        or any(ord(c) < 32 for c in name)
    ):
        raise ValueError("交付文件名非法")
    safe = "/".join(part for part in path.parts if part not in ("", "."))
    if not safe or safe != name:
        raise ValueError("交付文件名非法")
    return safe


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class ResearchDeliveryBuilder:
    PACKAGE_VERSION = "delivery-v1.1.0"
    MAX_FILES = 2_000
    MAX_TOTAL_BYTES = 512 * 1024 * 1024

    def build(
        self,
        *,
        snapshot: ReportSnapshot | None,
        snapshot_id: UUID | None,
        output_root: Path,
        inputs: tuple[DeliveryInput, ...],
        task_id: UUID | None = None,
        renderer_version: str = "not_used",
        template_version: str = "delivery-v1.0.0",
    ) -> DeliveryBuild:
        package_id = uuid4()
        directory = output_root / f"research-delivery-{package_id.hex}"
        directory.mkdir(parents=True, exist_ok=False)
        generated_at = datetime.now(UTC)
        if snapshot is None and not any(
            item.logical_name == "ReportSnapshot.json" for item in inputs
        ):
            inputs = (*inputs, DeliveryInput("ReportSnapshot.json", None, "json", "NOT_RECORDED"))
        files: list[DeliveryFile] = []
        missing: list[str] = []
        materialized: dict[str, bytes] = {}
        seen: set[str] = set()
        for item in inputs:
            if len(files) >= self.MAX_FILES:
                raise ValueError("交付文件数量超过上限")
            name = _safe_name(item.logical_name)
            if name in seen or name in {"README.md", "EvidenceManifest.json", "checksums.sha256"}:
                raise ValueError("交付文件重复或占用保留名称")
            seen.add(name)
            if item.content is None:
                missing.append(name)
                files.append(
                    DeliveryFile(
                        logical_name=name,
                        file_type=item.file_type,
                        size=0,
                        sha256=_sha256(b""),
                        source_object=item.source_object,
                        original_artifact_id=item.original_artifact_id,
                        generation=item.generation,
                        availability="missing",
                        integrity="not_applicable",
                    )
                )
                continue
            if name in materialized:
                raise ValueError(f"交付文件重复: {name}")
            materialized[name] = item.content
            files.append(
                DeliveryFile(
                    logical_name=name,
                    file_type=item.file_type,
                    size=len(item.content),
                    sha256=_sha256(item.content),
                    source_object=item.source_object,
                    original_artifact_id=item.original_artifact_id,
                    generation=item.generation,
                    availability="available",
                    integrity="verified",
                )
            )
        status = "partial" if missing else "complete"
        if snapshot is None and "ReportSnapshot.json" not in missing:
            missing.append("ReportSnapshot.json")
        status = "partial" if missing else "complete"
        readme = self._readme(snapshot, snapshot_id, files, missing)
        materialized["README.md"] = readme.encode("utf-8")
        files.append(
            DeliveryFile(
                logical_name="README.md",
                file_type="md",
                size=len(materialized["README.md"]),
                sha256=_sha256(materialized["README.md"]),
                source_object="cygnusx.delivery_builder",
                generation="generated",
                availability="available",
                integrity="verified",
            )
        )
        snapshot_task_id = snapshot.source_execution.task_id if snapshot else task_id
        snapshot_digest = snapshot.snapshot_digest if snapshot else None
        if snapshot_task_id is None or (snapshot is not None and snapshot_digest is None):
            raise ValueError("快照缺少任务身份或摘要")
        manifest = EvidenceManifest(
            manifest_schema_version="cygnusx.evidence_manifest.v1"
            if snapshot
            else "cygnusx.evidence_manifest.v1.1",
            package_id=package_id,
            task_id=snapshot_task_id,
            snapshot_id=snapshot_id,
            snapshot_digest=snapshot_digest,
            package_version=self.PACKAGE_VERSION,
            source_artifacts=tuple(item.artifact_reference for item in snapshot.artifacts)
            if snapshot
            else (),
            renderer_version=renderer_version,
            template_version=template_version,
            files=tuple(files),
            evidence_status=status,
            missing_files=tuple(missing),
            validation_status="validated",
            generated_at=generated_at,
        )
        materialized["EvidenceManifest.json"] = json.dumps(
            manifest.model_dump(mode="json"), ensure_ascii=False, indent=2
        ).encode("utf-8")
        files.append(
            DeliveryFile(
                logical_name="EvidenceManifest.json",
                file_type="json",
                size=len(materialized["EvidenceManifest.json"]),
                sha256=_sha256(materialized["EvidenceManifest.json"]),
                source_object="cygnusx.delivery_builder",
                generation="generated",
                availability="available",
                integrity="verified",
            )
        )
        checksums = "".join(
            f"{_sha256(content)}  {name}\n" for name, content in sorted(materialized.items())
        )
        materialized["checksums.sha256"] = checksums.encode("utf-8")
        total_bytes = sum(len(content) for content in materialized.values())
        if total_bytes > self.MAX_TOTAL_BYTES:
            raise ValueError("交付包总大小超过上限")
        for name, content in materialized.items():
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        zip_path = output_root / f"research-delivery-{package_id.hex}.zip"
        with zipfile.ZipFile(zip_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for name in sorted(materialized):
                archive.writestr(name, materialized[name])
        return DeliveryBuild(package_id, directory, zip_path, manifest)

    @staticmethod
    def verify_package(zip_path: Path) -> EvidenceManifest:
        """Verify ZIP names, the manifest, and every manifest-listed byte stream."""
        with zipfile.ZipFile(zip_path) as archive:
            names = archive.namelist()
            if len(names) > ResearchDeliveryBuilder.MAX_FILES + 3:
                raise ValueError("交付包文件数量超过上限")
            if (
                sum(item.file_size for item in archive.infolist())
                > ResearchDeliveryBuilder.MAX_TOTAL_BYTES
            ):
                raise ValueError("交付包解压大小超过上限")
            if len(names) != len(set(names)):
                raise ValueError("交付包包含重复成员")
            for name in names:
                _safe_name(name)
            for zip_info in archive.infolist():
                mode = (zip_info.external_attr >> 16) & 0o170000
                if mode == stat.S_IFLNK or zip_info.is_dir():
                    raise ValueError("交付包不允许符号链接或目录成员")
            try:
                if archive.getinfo("EvidenceManifest.json").file_size > 4 * 1024 * 1024:
                    raise ValueError("交付清单大小超限")
                manifest = EvidenceManifest.model_validate(
                    json.loads(archive.read("EvidenceManifest.json"))
                )
            except (KeyError, json.JSONDecodeError) as exc:
                raise ValueError("交付包缺少有效 EvidenceManifest.json") from exc
            listed = [item.logical_name for item in manifest.files]
            if len(listed) != len(set(listed)):
                raise ValueError("交付清单包含重复文件")
            expected = {"EvidenceManifest.json", "checksums.sha256"}
            for item in manifest.files:
                _safe_name(item.logical_name)
                if item.logical_name in {"EvidenceManifest.json", "checksums.sha256"}:
                    raise ValueError("交付清单包含自引用")
                if item.availability == "available":
                    expected.add(item.logical_name)
                elif item.logical_name in names:
                    raise ValueError("缺失文件不应出现在交付包")
            if set(names) != expected:
                raise ValueError("交付包包含未登记成员或缺少文件")
            for item in manifest.files:
                if item.availability != "available":
                    continue
                content = archive.read(item.logical_name)
                if len(content) != item.size or _sha256(content) != item.sha256:
                    raise ValueError(f"交付文件完整性校验失败: {item.logical_name}")
            checksums: dict[str, str] = {}
            for line in archive.read("checksums.sha256").decode("utf-8").splitlines():
                match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
                if match is None or match[2] in checksums:
                    raise ValueError("交付校验清单非法")
                checksums[match[2]] = match[1]
            if set(checksums) != expected - {"checksums.sha256"}:
                raise ValueError("交付校验清单与包不一致")
            for name, sha in checksums.items():
                if _sha256(archive.read(name)) != sha:
                    raise ValueError("交付校验清单摘要不一致")
            return manifest

    @staticmethod
    def _readme(
        snapshot: ReportSnapshot | None,
        snapshot_id: UUID | None,
        files: list[DeliveryFile],
        missing: list[str],
    ) -> str:
        if snapshot is None:
            return (
                "# Research Delivery Package\n\nStatus: partial\nReportSnapshot: NOT_RECORDED\nMissing: "
                + ", ".join(missing)
                + "\nNo reproduction claim. Verify checksums.sha256 offline.\n"
            )
        task_id = snapshot.source_execution.task_id
        status = "partial" if missing else "complete"
        project = snapshot.source_execution.project_slug or "未记录"
        analysis_type = next(
            (
                str(item.value)
                for item in snapshot.inputs
                if item.field in {"flow_id", "analysis_type", "pipeline"} and item.value is not None
            ),
            "未记录",
        )
        environment = (
            "; ".join(
                f"{item.field}={item.value}"
                for item in snapshot.environment
                if item.value is not None
            )
            or "未记录"
        )
        blockers = "; ".join(snapshot.reproducibility.blockers) or "无"
        file_lines = "\n".join(f"- `{item.logical_name}` ({item.size} bytes)" for item in files)
        missing_lines = "\n".join(f"- `{item}`" for item in missing) or "- 无"
        return f"""# Research Delivery Package\n\n- Project: `{project}`\n- Task: `{task_id}`\n- Analysis type: `{analysis_type}`\n- Snapshot: `{snapshot_id}`\n- Snapshot digest: `{snapshot.snapshot_digest}`\n- Delivery status: **{status}**\n- Reproducibility assessment: **{snapshot.reproducibility.assessment}**\n\n## Environment and dependencies\n{environment}\n\n## Files\n{file_lines}\n\n## Missing files\n{missing_lines}\n\n## Reproduction limits\n{blockers}\n\nScientific Report 是分析结果展示；Reproducibility Record 是执行证据及缺口记录。\n本包提供复现条件和文件完整性信息，不表示科研计算已经重新执行或结果已复现。\n\n使用 `sha256sum -c checksums.sha256` 校验文件。哈希证明文件字节完整，不证明科学结论正确。\n\n复现需要满足原始输入、执行定义、软件/镜像、参考库和资源版本均可用；本包会保留无法验证的历史事实和限制。\n"""

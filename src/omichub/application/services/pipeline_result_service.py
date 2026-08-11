"""分析流水线结果的受控读取与摘要。"""

from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select

from omichub.application.schemas.tool_invocation import ToolInvocationContext
from omichub.application.services.task_service import TaskService
from omichub.core.exceptions import ValidationError
from omichub.infrastructure.database.models.file import FileRecordModel
from omichub.infrastructure.storage import get_path_factory


class PipelineResultService:
    _MAX_FILES = 200
    _MAX_TABLE_BYTES = 10 * 1024 * 1024

    def __init__(self, context: ToolInvocationContext):
        self.context = context

    async def get_task_summary(self, task_id: str) -> dict[str, Any]:
        task = await TaskService(self.context.db).get_task(UUID(task_id), self.context.user_id)
        task_root = self._task_root(task_id, task.work_dir)
        roots = self._result_roots(task_root, task.result_path, task.work_dir)
        records = await self.context.db.scalars(
            select(FileRecordModel).where(
                FileRecordModel.user_id == UUID(self.context.user_id),
                FileRecordModel.task_id == UUID(task_id),
                FileRecordModel.status == "active",
            )
        )
        return {
            "task_id": task_id,
            "status": task.status,
            "flow_id": task.flow_id,
            "parameters": task.parameters,
            "progress": task.progress,
            "metrics": self._task_metrics(task.parameters, roots),
            "artifacts": self._list_artifacts(task_root, roots),
            "file_records": [
                {
                    "file_id": str(record.id),
                    "name": record.original_name,
                    "path": record.storage_path,
                    "size": record.size,
                    "type": record.file_type,
                }
                for record in records.all()
            ],
            "error_excerpt": str(task.error_message or "")[-500:],
        }

    async def preview_task_file(
        self, task_id: str, path: str, *, max_bytes: int = 20_000
    ) -> dict[str, Any]:
        task = await TaskService(self.context.db).get_task(UUID(task_id), self.context.user_id)
        task_root = self._task_root(task_id, task.work_dir)
        candidate = self._resolve_preview_path(task_root, path)
        content = candidate.read_bytes()[:max_bytes]
        size = candidate.stat().st_size
        return {
            "task_id": task_id,
            "path": candidate.relative_to(task_root).as_posix(),
            "size": size,
            "truncated": size > len(content),
            "content": content.decode("utf-8", errors="replace"),
        }

    async def get_results(
        self,
        task_id: str,
        pipeline_type: str,
        result_types: list[str],
    ) -> dict[str, Any]:
        task = await TaskService(self.context.db).get_task(UUID(task_id), self.context.user_id)
        if task.flow_id != pipeline_type:
            raise ValidationError(f"任务 {task_id} 不属于 {pipeline_type} 流程")
        if str(task.status).lower() != "success":
            raise ValidationError("任务尚未成功完成，暂不能读取最终结果")

        task_root = self._task_root(task_id, task.work_dir)
        roots = self._result_roots(task_root, task.result_path, task.work_dir)
        artifacts = self._list_artifacts(task_root, roots)
        metrics = self._task_metrics(task.parameters, roots) if "summary" in result_types else {}

        payload: dict[str, Any] = {
            "task_id": task_id,
            "pipeline_type": pipeline_type,
            "status": task.status,
            "progress": task.progress,
            "report_url": f"/tasks/{task_id}/report",
            "metrics": metrics,
        }
        if "artifacts" in result_types:
            payload["artifacts"] = artifacts
        return payload

    def _task_root(self, task_id: str, work_dir: str) -> Path:
        """新项目目录与历史 UUID 任务目录兼容解析。"""
        factory = get_path_factory()
        work_path = Path(work_dir).resolve() if work_dir else None
        projects_root = factory.projects_dir(self.context.user_id).resolve()
        if work_path is not None:
            try:
                work_path.relative_to(projects_root)
            except ValueError:
                pass
            else:
                return work_path.parent if work_path.name == "work" else work_path
        return factory.task_dir(self.context.user_id, task_id).resolve()

    @staticmethod
    def _result_roots(task_root: Path, result_path: str, work_dir: str) -> list[Path]:
        roots: list[Path] = []
        for raw_path in (result_path, str(task_root / "output"), work_dir):
            if not raw_path:
                continue
            candidate = Path(raw_path).resolve()
            try:
                candidate.relative_to(task_root)
            except ValueError:
                continue
            if candidate.exists() and candidate not in roots:
                roots.append(candidate)
        return roots

    def _list_artifacts(self, task_root: Path, roots: list[Path]) -> list[dict[str, Any]]:
        artifacts: list[dict[str, Any]] = []
        seen: set[Path] = set()
        for root in roots:
            candidates = [root] if root.is_file() else root.rglob("*")
            for path in candidates:
                if len(artifacts) >= self._MAX_FILES:
                    return artifacts
                if not path.is_file() or path.is_symlink():
                    continue
                resolved = path.resolve()
                try:
                    relative = resolved.relative_to(task_root)
                except ValueError:
                    continue
                if resolved in seen:
                    continue
                seen.add(resolved)
                artifacts.append(
                    {
                        "name": path.name,
                        "path": str(relative),
                        "size": path.stat().st_size,
                        "type": path.suffix.lower().lstrip(".") or "file",
                    }
                )
        return artifacts

    def _extract_metrics(self, roots: list[Path]) -> dict[str, Any]:
        for root in roots:
            candidates = [root] if root.is_file() else root.rglob("*")
            for path in candidates:
                lower_name = path.name.lower()
                if not path.is_file() or path.stat().st_size > self._MAX_TABLE_BYTES:
                    continue
                if path.suffix.lower() not in {".csv", ".tsv", ".txt"}:
                    continue
                if not any(token in lower_name for token in ("deg", "differential", "diff_gene")):
                    continue
                summary = self._summarize_differential_table(path)
                if summary:
                    return summary
        return {}

    def _task_metrics(self, parameters: dict[str, Any], roots: list[Path]) -> dict[str, Any]:
        metrics: dict[str, Any] = {}
        for key in ("qc_metrics", "metrics"):
            raw = parameters.get(key)
            if isinstance(raw, dict):
                metrics.update(self._canonical_metrics(raw))
        for root in roots:
            candidates = [root] if root.is_file() else root.rglob("*")
            for path in candidates:
                if (
                    not path.is_file()
                    or path.is_symlink()
                    or path.stat().st_size > self._MAX_TABLE_BYTES
                ):
                    continue
                lower_name = path.name.lower()
                if not any(token in lower_name for token in ("qc", "metric", "multiqc", "summary")):
                    continue
                if path.suffix.lower() == ".json":
                    try:
                        payload = json.loads(path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        continue
                    if isinstance(payload, dict):
                        metrics.update(self._canonical_metrics(payload))
                elif path.suffix.lower() in {".csv", ".tsv", ".txt"}:
                    metrics.update(self._metrics_from_table(path))
        metrics.update(self._extract_metrics(roots))
        return metrics

    @classmethod
    def _canonical_metrics(cls, payload: dict[str, Any]) -> dict[str, float]:
        aliases = {
            "mapping_rate": ("mapping_rate", "mapped_rate", "mapping_pct", "mapping_percent"),
            "q30": ("q30", "q30_rate", "q30_pct", "percent_q30", "avg_q30"),
            "duplicate_rate": (
                "duplicate_rate",
                "duplication_rate",
                "duplicate_pct",
                "percent_duplicates",
            ),
        }
        flattened: dict[str, Any] = {}

        def visit(value: Any) -> None:
            if not isinstance(value, dict):
                return
            for key, nested in value.items():
                normalized = str(key).strip().lower().replace(" ", "_").replace("%", "pct")
                flattened[normalized] = nested
                visit(nested)

        visit(payload)
        result: dict[str, float] = {}
        for canonical, candidates in aliases.items():
            values = [cls._rate(flattened[name]) for name in candidates if name in flattened]
            valid = [value for value in values if value is not None]
            if valid:
                result[canonical] = float(statistics.median(valid))
        return result

    @classmethod
    def _metrics_from_table(cls, path: Path) -> dict[str, float]:
        try:
            with path.open(encoding="utf-8", errors="replace", newline="") as handle:
                sample = handle.read(4096)
                handle.seek(0)
                delimiter = "\t" if sample.count("\t") >= sample.count(",") else ","
                rows = list(csv.DictReader(handle, delimiter=delimiter))
        except OSError:
            return {}
        collected: dict[str, list[float]] = {
            "mapping_rate": [],
            "q30": [],
            "duplicate_rate": [],
        }
        for row in rows:
            canonical = cls._canonical_metrics(row)
            for key, value in canonical.items():
                collected[key].append(value)
        return {
            key: float(statistics.median(values)) for key, values in collected.items() if values
        }

    @staticmethod
    def _rate(value: Any) -> float | None:
        try:
            rate = float(str(value).strip().rstrip("%"))
        except (TypeError, ValueError):
            return None
        if rate > 1:
            rate /= 100
        return rate if 0 <= rate <= 1 else None

    @staticmethod
    def _resolve_preview_path(root: Path, requested: str) -> Path:
        relative = Path(requested)
        if not requested.strip() or relative.is_absolute() or ".." in relative.parts:
            raise ValidationError("文件路径必须是任务目录内的安全相对路径")
        resolved_root = root.resolve()
        current = resolved_root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise ValidationError("禁止预览符号链接")
        resolved = (resolved_root / relative).resolve()
        try:
            resolved.relative_to(resolved_root)
        except ValueError as exc:
            raise ValidationError("文件路径超出任务目录") from exc
        if not resolved.is_file():
            raise ValidationError("请求的任务文件不存在或不是普通文件")
        return resolved

    @staticmethod
    def _summarize_differential_table(path: Path) -> dict[str, int]:
        delimiter = "\t" if path.suffix.lower() in {".tsv", ".txt"} else ","
        total = up = down = 0
        try:
            with path.open(encoding="utf-8", errors="replace", newline="") as handle:
                reader = csv.DictReader(handle, delimiter=delimiter)
                if not reader.fieldnames:
                    return {}
                fold_column = next(
                    (
                        name
                        for name in reader.fieldnames
                        if name.lower() in {"log2foldchange", "log2fc", "logfc", "fold_change"}
                    ),
                    None,
                )
                for row in reader:
                    total += 1
                    if total > 100_000:
                        break
                    if not fold_column:
                        continue
                    try:
                        value = float(row.get(fold_column, ""))
                    except (TypeError, ValueError):
                        continue
                    if value > 0:
                        up += 1
                    elif value < 0:
                        down += 1
        except OSError:
            return {}
        return {
            "differential_gene_count": total,
            "upregulated_count": up,
            "downregulated_count": down,
        }

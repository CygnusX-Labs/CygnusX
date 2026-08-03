"""分析流水线结果的受控读取与摘要。"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any
from uuid import UUID

from omichub.application.schemas.tool_invocation import ToolInvocationContext
from omichub.application.services.task_service import TaskService
from omichub.core.exceptions import ValidationError
from omichub.infrastructure.storage import get_path_factory


class PipelineResultService:
    _MAX_FILES = 200
    _MAX_TABLE_BYTES = 10 * 1024 * 1024

    def __init__(self, context: ToolInvocationContext):
        self.context = context

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
        metrics = self._extract_metrics(roots) if "summary" in result_types else {}

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

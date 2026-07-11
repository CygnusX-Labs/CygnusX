"""系统发育树构建 Celery 任务。

任务命名：omichub.tools.phylogenetic_tree.tasks.build_tree
路由队列：config.yaml 中 execution.celery.queue（默认 phylo_tree）
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

from omichub.core.config import get_settings

logger = logging.getLogger(__name__)

# 阶段权重（用于进度计算）
PHASE_WEIGHTS = {
    "alignment": 0.35,
    "tree_building": 0.40,
    "bootstrap": 0.20,
    "formatting": 0.05,
}


def _update_progress(task: Any, phase: str, progress: float, message: str) -> None:
    """更新 Celery 任务进度。"""
    task.update_state(
        state="PROGRESS",
        meta={
            "phase": phase,
            "progress": round(progress, 4),
            "message": message,
            "timestamp": time.time(),
        },
    )


@shared_task(
    bind=True,
    name="omichub.tools.phylogenetic_tree.tasks.build_tree",
    time_limit=3600 * 2,
    soft_time_limit=3600,
    max_retries=1,
    default_retry_delay=30,
    queue="phylo_tree",
)
def build_phylogenetic_tree(self, task_input: dict[str, Any]) -> dict[str, Any]:
    """系统发育树构建主任务：MSA → 树构建 → Bootstrap → 结果格式化。"""
    from omichub.tools.phylogenetic_tree.runner import (
        compute_tree_statistics,
        format_results,
        run_alignment,
        run_bootstrap,
        run_tree_building,
    )

    task_id = str(self.request.id)
    start_time = time.time()
    phases_completed: list[str] = []

    settings = get_settings()
    work_dir = Path(settings.storage_path) / "results" / "phylo" / task_id
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        # ═══ PHASE 1: 多序列比对 ═══
        if task_input.get("alignment_tool") != "prealigned":
            _update_progress(self, "ALIGNING", 0.05, "开始多序列比对...")
            run_alignment(
                task_input,
                work_dir,
                callback=lambda p, msg: _update_progress(
                    self, "ALIGNING", 0.05 + p * PHASE_WEIGHTS["alignment"], msg
                ),
            )
            phases_completed.append("alignment")
        else:
            _update_progress(self, "ALIGNING", 0.05, "输入已比对，跳过 MSA")
            run_alignment(task_input, work_dir)
            phases_completed.append("alignment_skipped")

        # ═══ PHASE 2: 进化树构建 ═══
        _update_progress(self, "BUILDING", 0.40, "开始构建进化树...")
        run_tree_building(
            task_input,
            work_dir,
            callback=lambda p, msg: _update_progress(
                self, "BUILDING", 0.40 + p * PHASE_WEIGHTS["tree_building"], msg
            ),
        )
        phases_completed.append("tree_building")

        # ═══ PHASE 3: Bootstrap ═══
        if task_input.get("bootstrap_enabled") and task_input.get("tree_method") in (
            "nj",
            "upgma",
            "iqtree",
        ):
            _update_progress(self, "BOOTSTRAPPING", 0.80, "开始 Bootstrap 评估...")
            run_bootstrap(
                task_input,
                work_dir,
                callback=lambda p, msg: _update_progress(
                    self, "BOOTSTRAPPING", 0.80 + p * PHASE_WEIGHTS["bootstrap"], msg
                ),
            )
            phases_completed.append("bootstrap")
        else:
            phases_completed.append("bootstrap_skipped")

        # ═══ PHASE 4: 结果格式化 ═══
        _update_progress(self, "FORMATTING", 0.95, "格式化输出结果...")
        output_files = format_results(task_input, work_dir)
        tree_stats = compute_tree_statistics(output_files["newick"])
        phases_completed.append("formatting")

        _update_progress(self, "COMPLETED", 1.0, "任务完成！")

        return {
            "task_id": task_id,
            "status": "COMPLETED",
            "output_files": output_files,
            "statistics": tree_stats,
            "execution_time": round(time.time() - start_time, 2),
            "phases_completed": phases_completed,
        }

    except SoftTimeLimitExceeded:
        return {
            "status": "FAILED",
            "error": "任务执行超时",
            "phases_completed": phases_completed,
        }
    except Exception as exc:
        logger.exception("构建系统发育树失败")
        return {
            "status": "FAILED",
            "error": str(exc),
            "phases_completed": phases_completed,
        }

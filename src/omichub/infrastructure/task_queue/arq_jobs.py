"""ARQ 异步任务函数注册表。

ARQ Worker 通过本模块的 functions 列表发现任务。
工具异步执行走统一的 `run_tool_async`，内部按 tool_name 分发到具体实现。
"""

from __future__ import annotations

import json
import time
from typing import Any

from arq.connections import RedisSettings

from omichub.core.config import get_settings


async def _publish_progress(
    redis: Any, task_id: str, phase: str, progress: float, message: str
) -> None:
    """发布进度到 Redis pub/sub 频道，供 SSE 端点消费。"""
    payload = json.dumps(
        {
            "task_id": task_id,
            "phase": phase,
            "progress": round(progress, 4),
            "message": message,
            "timestamp": time.time(),
        },
        ensure_ascii=False,
    )
    await redis.publish(f"task:{task_id}:progress", payload)


async def _run_phylogenetic_tree(
    ctx: dict[str, Any], task_id: str, user_id: str, args: dict[str, Any]
) -> dict[str, Any]:
    """系统发育树构建 ARQ 任务。"""
    from omichub.tools.phylogenetic_tree.core import build_tree
    from omichub.tools.phylogenetic_tree.service import PhylogeneticTreeService

    service = PhylogeneticTreeService()
    meta = service._load_meta(user_id, args.get("file_id", ""))

    # 默认参数与 PhyloSubmitRequest 对齐
    method_raw = args.get("method", "nj")
    method_map = {
        "NJ": "nj",
        "UPGMA": "upgma",
        "ML": "iqtree",
        "Bayesian": "mrbayes",
    }
    tree_method = method_map.get(method_raw, method_raw).lower()
    task_input = {
        "input_path": meta["input_path"],
        "alignment_tool": args.get("alignment_tool", "mafft"),
        "alignment_mode": args.get("alignment_mode", "auto"),
        "tree_method": tree_method,
        "substitution_model": args.get("substitution_model", "auto"),
        "bootstrap_enabled": args.get("bootstrap_enabled", False),
        "bootstrap_type": args.get("bootstrap_type", "standard"),
        "bootstrap_replicates": args.get("bootstrap_replicates", 100),
        "sequence_type": meta.get("sequence_type", "dna"),
        "advanced_params": args.get("advanced_params", {}),
        "user_id": str(user_id),
    }

    redis = ctx.get("redis")

    async def progress(phase: str, progress: float, message: str) -> None:
        if redis is not None:
            await _publish_progress(redis, task_id, phase, progress, message)

    return await build_tree(task_id, task_input, progress_callback=progress)


# 工具名 → ARQ 执行函数的映射
_TOOL_RUNNERS: dict[str, Any] = {
    "omichub_build_phylogenetic_tree": _run_phylogenetic_tree,
}


async def run_tool_async(
    ctx: dict[str, Any], tool_name: str, user_id: str, **kwargs: Any
) -> dict[str, Any]:
    """通用工具异步执行入口。"""
    task_id = ctx.get("job_id")
    if task_id is None:
        task_id = f"arq-{int(time.time() * 1000)}"

    runner = _TOOL_RUNNERS.get(tool_name)
    if runner is None:
        return {
            "task_id": task_id,
            "status": "FAILED",
            "error": f"未找到工具 {tool_name} 的 ARQ 执行器",
        }

    redis = ctx.get("redis")
    if redis is not None:
        await _publish_progress(redis, task_id, "PENDING", 0.0, "任务已入队")

    try:
        result = await runner(ctx, task_id, user_id, kwargs)
        if not isinstance(result, dict):
            return {
                "task_id": task_id,
                "status": "FAILED",
                "error": f"工具 {tool_name} 返回非字典结果: {type(result)}",
            }
        result.setdefault("task_id", task_id)
        return result
    except Exception as e:  # noqa: BLE001
        return {
            "task_id": task_id,
            "status": "FAILED",
            "error": str(e),
        }


class WorkerSettings:
    """ARQ Worker 配置。"""

    functions = [run_tool_async]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 10
    job_timeout = 3600
    max_tries = 2

"""分析任务 - Snakemake 工作流执行"""

from celery import shared_task


@shared_task(name="omichub.infrastructure.celery_app.tasks.analysis.run_snakemake")
def run_snakemake(
    snakefile: str,
    config: dict,
    cores: int = 4,
    work_dir: str = "",
    use_conda: bool = True,
) -> dict:
    """执行 Snakemake 工作流

    本地模式: 通过 subprocess 调用 Snakemake CLI
    远程模式: 通过 HTTP 调用远程 Executor
    """
    # TODO: 实现完整的 Snakemake 执行逻辑
    return {
        "status": "pending",
        "message": "snakemake task placeholder",
        "snakefile": snakefile,
    }


@shared_task(name="omichub.infrastructure.celery_app.tasks.analysis.cleanup_expired")
def cleanup_expired() -> dict:
    """清理过期结果归档"""
    # TODO: 调用 FileDomainService.cleanup_expired_archives()
    return {"status": "ok", "cleaned": 0}

"""本地执行器 - Snakemake subprocess"""

import asyncio
from typing import Any

from omichub.core.config import get_settings


class LocalSnakemakeExecutor:
    """本地 Snakemake 执行器

    通过 subprocess 调用 Snakemake CLI，直接在 Worker 所在服务器执行。
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    async def execute(
        self,
        snakefile: str,
        config: dict[str, Any],
        cores: int | None = None,
        work_dir: str = "",
        targets: list[str] | None = None,
    ) -> dict[str, Any]:
        """执行 Snakemake 工作流

        Returns:
            执行结果，包含 status, stdout, stderr, returncode
        """
        cmd = [
            "snakemake",
            "-s", snakefile,
            "--cores", str(cores or self.settings.snakemake_cores),
        ]

        if self.settings.snakemake_use_conda:
            cmd.append("--use-conda")

        if work_dir:
            cmd.extend(["--directory", work_dir])

        if targets:
            cmd.extend(targets)

        # 传递配置参数
        for key, value in config.items():
            cmd.extend(["--config", f"{key}={value}"])

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        return {
            "status": "success" if process.returncode == 0 else "failed",
            "returncode": process.returncode,
            "stdout": stdout.decode(),
            "stderr": stderr.decode(),
        }

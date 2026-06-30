"""本地执行器 - Snakemake subprocess"""

import asyncio
import shutil
from typing import Any

from omichub.core.config import get_settings
from omichub.infrastructure.execution.base import (
    BaseExecutor,
    ExecutionContext,
    ExecutionResult,
)


class LocalSnakemakeExecutor(BaseExecutor):
    """本地 Snakemake 执行器

    通过 subprocess 调用 Snakemake CLI，直接在 Worker 所在服务器执行。
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    async def execute(self, ctx: ExecutionContext) -> ExecutionResult:
        """统一执行入口（实现 BaseExecutor 契约）。

        委托给既有的 _execute(...)，保留原缓冲行为，不改 Snakemake 可观测日志。
        """
        if ctx.snakefile is None:
            return ExecutionResult(
                status="failed", returncode=-1, stderr="Snakemake 缺少 snakefile"
            )
        result = await self._execute(
            snakefile=ctx.snakefile,
            work_dir=ctx.work_dir,
            cores=ctx.cores,
            config_file=ctx.config_file,
            config_file_param=ctx.config_file_param,
        )
        return ExecutionResult(
            status=result["status"],
            returncode=result["returncode"],
            stdout=result["stdout"],
            stderr=result["stderr"],
        )

    async def _execute(
        self,
        snakefile: str,
        config: dict[str, Any] | None = None,
        cores: int | None = None,
        work_dir: str = "",
        targets: list[str] | None = None,
        config_file: str | None = None,
        config_file_param: str = "analysisyaml",
    ) -> dict[str, Any]:
        """执行 Snakemake 工作流（既有实现，向后兼容）。

        Args:
            snakefile: Snakefile 路径
            config: 需要以 --config key=value 形式传递的配置字典
            cores: CPU 核心数
            work_dir: Snakemake --directory 工作目录
            targets: 目标文件列表
            config_file: 若提供，则以 --config <config_file_param>=<config_file> 形式传递
            config_file_param: 流程接收配置文件的 --config 参数名，默认 analysisyaml
                               （RNAFlow 使用 analysisyaml；其他流程可在 execution 中指定）

        Returns:
            执行结果，包含 status, stdout, stderr, returncode
        """
        cmd = [
            "snakemake",
            "-s",
            snakefile,
            "--cores",
            str(cores or self.settings.snakemake_cores),
        ]

        if self.settings.snakemake_use_conda:
            cmd.append("--use-conda")

        if work_dir:
            cmd.extend(["--directory", work_dir])

        if targets:
            cmd.extend(targets)

        if config_file:
            cmd.extend(["--config", f"{config_file_param}={config_file}"])
        elif config:
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

    async def generate_dag(
        self,
        snakefile: str,
        config_file: str = "",
        work_dir: str = "",
        config_file_param: str = "analysisyaml",
    ) -> dict[str, Any]:
        """生成 Snakemake DAG 可视化。

        若系统安装了 graphviz 的 dot，则返回 SVG；否则返回 DOT 文本。
        """
        cmd = [
            "snakemake",
            "-s",
            snakefile,
            "--dag",
            "--cores",
            "1",
        ]

        if self.settings.snakemake_use_conda:
            cmd.append("--use-conda")

        if work_dir:
            cmd.extend(["--directory", work_dir])

        if config_file:
            cmd.extend(["--config", f"{config_file_param}={config_file}"])

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        dot_text, stderr = await process.communicate()
        dot_text_str = dot_text.decode()

        if process.returncode != 0:
            return {
                "status": "failed",
                "returncode": process.returncode,
                "error": stderr.decode(),
            }

        if shutil.which("dot"):
            dot_proc = await asyncio.create_subprocess_exec(
                "dot",
                "-Tsvg",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            svg_bytes, dot_err = await dot_proc.communicate(input=dot_text)
            if dot_proc.returncode == 0:
                return {
                    "status": "success",
                    "format": "svg",
                    "content": svg_bytes.decode(),
                }
            return {
                "status": "success",
                "format": "dot",
                "content": dot_text_str,
                "warning": f"dot 渲染失败: {dot_err.decode()}",
            }

        return {
            "status": "success",
            "format": "dot",
            "content": dot_text_str,
        }

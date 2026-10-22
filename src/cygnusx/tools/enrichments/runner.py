"""GO / KEGG 富集 R 容器执行器 —— 拼接并运行 `docker run` 调用 R 计算镜像。

镜像本身由用户构建（契约见 tool_configs/enrichments/KEGG_Docker_契约.md），本模块只负责：
- 按 settings 拼接 docker run 命令（网络 / 代理 / 挂载 / 资源 / 超时）；
- asyncio.create_subprocess_exec 执行，事件循环不阻塞；
- 捕获 stdout / stderr，超时则 kill 容器进程。

路径约定：宿主 enrichment_data_mount 挂载到容器内 /data/cygnusx。Worker 数据根
storage_path 下的输入、输出和参考文件路径，必须转换为容器内路径后再传给 R。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic, TypeVar

from cygnusx.core.config import get_settings
from cygnusx.core.telemetry import get_tracer
from cygnusx.tools.container_paths import ToolDataMount

logger = logging.getLogger(__name__)


@dataclass
class EnrichmentRunResult:
    """容器执行结果。"""

    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


@dataclass
class EnrichmentRunParams:
    """单次富集分析入参，文件路径来自 Worker 共享数据根或容器挂载点。"""

    input_path: str
    output_path: str
    kegg_code: str
    id_type: str
    go_obo: str | None = None
    go_annotation: str | None = None
    kegg_id_map: str | None = None
    kegg_key_type: str = "kegg"
    p_value_cutoff: float = 0.05
    q_value_cutoff: float = 0.1


RunParamsT = TypeVar("RunParamsT")


class EnrichmentDockerRunnerBase(ABC, Generic[RunParamsT]):
    """GO/KEGG 与 GSEA 共享进程执行和超时处理，保留各自的参数类型。"""

    def __init__(self) -> None:
        self._settings = get_settings()

    @abstractmethod
    def build_command(self, params: RunParamsT, container_name: str) -> list[str]:
        """由具体工具构造命令。"""

    async def run(self, params: RunParamsT, container_name: str) -> EnrichmentRunResult:
        """执行容器，返回 stdout/stderr/returncode；超时 kill。

        docker run --rm 退出后容器自动清理；kill 主进程会连带终止容器。
        """
        cmd = self.build_command(params, container_name)
        logger.info("enrichment docker run: %s", " ".join(cmd))

        tracer = get_tracer("cygnusx.toolbox")
        with tracer.start_as_current_span(
            "toolbox.runner",
            attributes={"toolbox.runner": "enrichment", "toolbox.command": " ".join(cmd)[:1000]},
        ) as span:
            start = time.perf_counter()
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                timeout = self._settings.enrichment_exec_timeout
                try:
                    stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                except TimeoutError:
                    # 超时：杀掉 docker run 主进程（--rm 会清理容器）
                    with contextlib.suppress(ProcessLookupError):
                        proc.kill()
                    # 给被杀进程一点时间回收 stdout/stderr，收不到也无所谓
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(proc.communicate(), timeout=10)
                    span.set_attribute("toolbox.returncode", -1)
                    span.set_attribute("toolbox.timed_out", True)
                    return EnrichmentRunResult(
                        returncode=-1,
                        stdout="",
                        stderr=f"富集分析执行超时（>{timeout}s）",
                        timed_out=True,
                    )

                returncode = proc.returncode if proc.returncode is not None else -1
                span.set_attribute("toolbox.returncode", returncode)
                return EnrichmentRunResult(
                    returncode=returncode,
                    stdout=stdout_b.decode("utf-8", errors="replace"),
                    stderr=stderr_b.decode("utf-8", errors="replace"),
                )
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                span.set_attribute("toolbox.duration_ms", round(duration_ms, 2))
                logger.info("enrichment runner finished in %.2f ms", duration_ms)


class EnrichmentDockerRunner(EnrichmentDockerRunnerBase[EnrichmentRunParams]):
    """R 富集分析容器执行器。"""

    def build_command(self, params: EnrichmentRunParams, container_name: str) -> list[str]:
        """构造 `docker run` 命令行参数列表。"""
        s = self._settings
        mount = ToolDataMount(s.enrichment_data_mount, s.storage_path)
        command = [
            "docker",
            "run",
            "--rm",
            "--name",
            container_name,
        ]
        if s.enrichment_docker_network:
            command.extend(["--network", s.enrichment_docker_network])
        if s.enrichment_proxy_url:
            command.extend(
                [
                    "-e",
                    f"http_proxy={s.enrichment_proxy_url}",
                    "-e",
                    f"https_proxy={s.enrichment_proxy_url}",
                    "-e",
                    "no_proxy=localhost,127.0.0.1",
                ]
            )
        command.extend(
            [
                "-v",
                mount.volume,
                "--memory",
                s.enrichment_memory,
                "--cpus",
                str(s.enrichment_cpus),
                s.enrichment_docker_image,
                "Rscript",
                "/app/run_enrichment.R",
                "--input",
                mount.container_path(params.input_path),
                "--output",
                mount.container_path(params.output_path),
                "--kegg_code",
                params.kegg_code,
                "--id_type",
                params.id_type,
                "--kegg_key_type",
                params.kegg_key_type,
                "--p_value_cutoff",
                str(params.p_value_cutoff),
                "--q_value_cutoff",
                str(params.q_value_cutoff),
            ]
        )
        if params.go_obo:
            command.extend(["--go_obo", mount.container_path(params.go_obo)])
        if params.go_annotation:
            command.extend(["--go_annotation", mount.container_path(params.go_annotation)])
        if params.kegg_id_map:
            command.extend(["--kegg_id_map", mount.container_path(params.kegg_id_map)])
        return command


# 模块级单例
enrichment_runner = EnrichmentDockerRunner()

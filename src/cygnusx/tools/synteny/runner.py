from __future__ import annotations

import asyncio
from dataclasses import dataclass

from cygnusx.core.config import get_settings
from cygnusx.tools.container_paths import ToolDataMount


@dataclass
class SyntenyRunResult:
    returncode: int
    stdout: str
    stderr: str


class SyntenyDockerRunner:
    def build_command(self, gff3: str, blastp: str, output: str, container_name: str) -> list[str]:
        settings = get_settings()
        mount = ToolDataMount(settings.enrichment_data_mount, settings.storage_path)
        return [
            "docker",
            "run",
            "--rm",
            "--name",
            container_name,
            "-v",
            mount.volume,
            "cygnusx-synteny:v1",
            "--gff3",
            mount.container_path(gff3),
            "--blastp",
            mount.container_path(blastp),
            "--output",
            mount.container_path(output),
        ]

    async def run(
        self, gff3: str, blastp: str, output: str, container_name: str
    ) -> SyntenyRunResult:
        process = await asyncio.create_subprocess_exec(
            *self.build_command(gff3, blastp, output, container_name),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        return SyntenyRunResult(process.returncode or 0, stdout.decode(), stderr.decode())

from __future__ import annotations

from dataclasses import dataclass

from cygnusx.tools.container_paths import ToolDataMount
from cygnusx.tools.enrichments.runner import EnrichmentDockerRunnerBase


@dataclass
class GseaRunParams:
    input_path: str
    output_path: str
    gene_set: str
    go_annotation: str | None
    p_value_cutoff: float
    q_value_cutoff: float


class GseaDockerRunner(EnrichmentDockerRunnerBase[GseaRunParams]):
    def build_command(self, params: GseaRunParams, container_name: str) -> list[str]:
        settings = self._settings
        mount = ToolDataMount(settings.enrichment_data_mount, settings.storage_path)
        command = [
            "docker",
            "run",
            "--rm",
            "--name",
            container_name,
            "-v",
            mount.volume,
            "--memory",
            settings.enrichment_memory,
            "--cpus",
            str(settings.enrichment_cpus),
            settings.enrichment_docker_image,
            "Rscript",
            "/app/run_gsea.R",
            "--input",
            mount.container_path(params.input_path),
            "--output",
            mount.container_path(params.output_path),
            "--gene_set",
            params.gene_set,
            "--p_value_cutoff",
            str(params.p_value_cutoff),
            "--q_value_cutoff",
            str(params.q_value_cutoff),
        ]
        if params.go_annotation:
            command.extend(["--go_annotation", mount.container_path(params.go_annotation)])
        return command

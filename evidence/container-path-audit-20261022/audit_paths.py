"""只构造命令和读取配置，不启动容器、不提交任务、不修改用户文件。"""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any

from cygnusx.core.config import get_settings
from cygnusx.tools.blast.core import build_docker_blast_command
from cygnusx.tools.deg.runner import DegDockerRunner, DegRunParams
from cygnusx.tools.download.config import get_download_config
from cygnusx.tools.enrichments.runner import EnrichmentDockerRunner, EnrichmentRunParams
from cygnusx.tools.fastq_qc.config import get_fastq_qc_config
from cygnusx.tools.gsea.runner import GseaDockerRunner, GseaRunParams
from cygnusx.tools.jbrowse.config import config_manager as jbrowse_manager
from cygnusx.tools.jbrowse.config import to_tracks_uri
from cygnusx.tools.synteny.runner import SyntenyDockerRunner
from cygnusx.tools.terminal.config import get_terminal_config


def audit_command(name: str, command: list[str], file_flags: list[str]) -> dict[str, Any]:
    mounts = []
    for index, token in enumerate(command):
        if token == "-v":
            source, destination, *_mode = command[index + 1].split(":")
            mounts.append({"source": source, "destination": destination})
    files = []
    for flag in file_flags:
        value = command[command.index(flag) + 1]
        covered = [
            mount
            for mount in mounts
            if PurePosixPath(value).is_relative_to(mount["destination"])
        ]
        files.append({"flag": flag, "value": value, "covered_by_mount": bool(covered)})
    return {
        "tool": name,
        "mounts": mounts,
        "files": files,
        "all_file_arguments_covered": all(item["covered_by_mount"] for item in files),
    }


def main() -> None:
    settings = get_settings()
    root = Path(settings.storage_path)
    work = root / "users/audit/projects/path-audit/runs/check"
    records = []
    for engine in ("deseq2", "edger"):
        params = DegRunParams(
            engine=engine,
            counts_path=str(work / "input/counts.csv"),
            metadata_path=str(work / "input/metadata.csv"),
            pairs_path=str(work / "input/pairs.csv"),
            output_dir=str(work / "output"),
            annotation_path=str(work / "input/annotation.csv"),
        )
        records.append(
            audit_command(
                f"DEG/{engine}",
                DegDockerRunner().build_command(params, "audit-deg"),
                ["-c", "-m", "-p", "-o", "-a"],
            )
        )
    records.append(
        audit_command(
            "GSEA",
            GseaDockerRunner().build_command(
                GseaRunParams(
                    input_path=str(work / "input/ranking.tsv"),
                    output_path=str(work / "output/gsea_result.csv"),
                    gene_set="GO_BP",
                    go_annotation=str(root / "omichub_data/reference/ITAG4.1/go.annot"),
                    p_value_cutoff=0.05,
                    q_value_cutoff=0.1,
                ),
                "audit-gsea",
            ),
            ["--input", "--output", "--go_annotation"],
        )
    )
    records.append(
        audit_command(
            "Synteny",
            SyntenyDockerRunner().build_command(
                str(work / "input/annotations.gff3"),
                str(work / "input/blastp.outfmt6"),
                str(work / "output/synteny.json"),
                "audit-synteny",
            ),
            ["--gff3", "--blastp", "--output"],
        )
    )
    records.append(
        audit_command(
            "GO/KEGG (worktree fix)",
            EnrichmentDockerRunner().build_command(
                EnrichmentRunParams(
                    input_path=str(work / "input/gene_list.txt"),
                    output_path=str(work / "output/enrichment_result.csv"),
                    kegg_code="sly",
                    id_type="ITAG4.1",
                ),
                "audit-enrichment",
            ),
            ["--input", "--output"],
        )
    )
    records.append(
        audit_command(
            "BLAST search",
            build_docker_blast_command(
                "blastn",
                work / "input/query.fa",
                root / "blast/db/example/sequence",
                work / "output/result.xml",
            ),
            ["-query", "-db", "-out"],
        )
    )

    jbrowse = []
    for assembly in jbrowse_manager.get_config().assemblies:
        for field in ("fasta", "fai"):
            configured = getattr(assembly, field)
            uri = to_tracks_uri(configured)
            # 单独记录旧部署现存的对应参考文件，不把候选路径当作自动修复规则。
            counterpart = configured.replace(
                "/data/cygnusx/cygnusx_data/", str(root / "omichub_data") + "/", 1
            )
            jbrowse.append(
                {
                    "assembly": assembly.id,
                    "field": field,
                    "configured": configured,
                    "configured_exists": Path(configured).is_file(),
                    "tracks_uri": uri,
                    "file_behind_tracks_uri_exists": (root / uri.removeprefix("/tracks/")).is_file(),
                    "legacy_counterpart": counterpart,
                    "legacy_counterpart_exists": Path(counterpart).is_file(),
                }
            )

    report = {
        "storage_path": str(root),
        "deg_data_mount": settings.deg_data_mount,
        "enrichment_data_mount": settings.enrichment_data_mount,
        "command_audits": records,
        "jbrowse": jbrowse,
        "explicit_config_roots": {
            "terminal_workspace_base": get_terminal_config().storage.workspace_base,
            "fastq_qc_root": get_fastq_qc_config().storage.root,
            "download_binaries": get_download_config().binaries.model_dump(),
            "jbrowse_scan_paths": jbrowse_manager.get_config().auto_scan.scan_paths,
            "jbrowse_upload_dir": jbrowse_manager.get_config().upload.upload_dir,
        },
        "scope": "command construction and local config/filesystem inspection; no live execution",
    }
    out = Path(__file__).with_name("audit-results.json")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for item in records:
        print(item["tool"], "covered=" + str(item["all_file_arguments_covered"]))
    for item in jbrowse:
        print(json.dumps(item, ensure_ascii=False))
    print("report:", out)


if __name__ == "__main__":
    main()

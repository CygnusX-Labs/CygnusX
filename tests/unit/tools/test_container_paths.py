"""跨数据根部署时，工具文件参数必须与容器数据卷对应。"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from cygnusx.core.exceptions import ValidationError
from cygnusx.tools.container_paths import ToolDataMount
from cygnusx.tools.deg.runner import DegDockerRunner, DegRunParams
from cygnusx.tools.enrichments.runner import EnrichmentDockerRunner, EnrichmentRunParams
from cygnusx.tools.gsea.runner import GseaDockerRunner, GseaRunParams
from cygnusx.tools.synteny.runner import SyntenyDockerRunner

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("tool", ["enrichment", "deseq2", "edger", "gsea", "synteny"])
@pytest.mark.parametrize(
    ("storage_root", "mount_source"),
    [
        ("/data/cygnusx", "/data/cygnusx"),
        ("/data/omichub", "/data/omichub"),
        ("/worker/data", "/srv/shared data"),
    ],
)
def test_all_tool_file_arguments_map_to_the_container_volume(
    tool: str, storage_root: str, mount_source: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = SimpleNamespace(
        storage_path=storage_root,
        enrichment_data_mount=mount_source,
        deg_data_mount=mount_source,
        enrichment_docker_network="",
        deg_docker_network="cygnusx_app_net",
        enrichment_proxy_url="",
        enrichment_memory="2g",
        enrichment_cpus=2.0,
        enrichment_docker_image="cygnusx-r-enrichment:v1",
        deg_docker_image="cygnusx-r-deg:v1",
    )
    root = Path(storage_root)
    if tool in {"deseq2", "edger"}:
        runner = DegDockerRunner.__new__(DegDockerRunner)
        runner._settings = settings
        files = {
            "-c": "input/counts.csv",
            "-m": "input/metadata.csv",
            "-p": "input/pairs.csv",
            "-o": "output",
            "-a": "input/annotation.csv",
        }
        command = runner.build_command(
            DegRunParams(
                engine=tool,
                counts_path=str(root / files["-c"]),
                metadata_path=str(root / files["-m"]),
                pairs_path=str(root / files["-p"]),
                output_dir=str(root / files["-o"]),
                annotation_path=str(root / files["-a"]),
            ),
            "audit-deg",
        )
    elif tool == "gsea":
        gsea = GseaDockerRunner.__new__(GseaDockerRunner)
        gsea._settings = settings
        files = {
            "--input": "input/ranking.tsv",
            "--output": "output/gsea.csv",
            "--go_annotation": "reference/go.annot",
        }
        command = gsea.build_command(
            GseaRunParams(
                str(root / files["--input"]),
                str(root / files["--output"]),
                "GO_BP",
                str(root / files["--go_annotation"]),
                0.05,
                0.1,
            ),
            "audit-gsea",
        )
    elif tool == "synteny":
        monkeypatch.setattr("cygnusx.tools.synteny.runner.get_settings", lambda: settings)
        files = {
            "--gff3": "input/annotations.gff3",
            "--blastp": "input/blastp.tsv",
            "--output": "output/synteny.json",
        }
        command = SyntenyDockerRunner().build_command(
            str(root / files["--gff3"]),
            str(root / files["--blastp"]),
            str(root / files["--output"]),
            "audit-synteny",
        )
    else:
        enrichment = EnrichmentDockerRunner.__new__(EnrichmentDockerRunner)
        enrichment._settings = settings
        files = {
            "--input": "input/genes.txt",
            "--output": "output/enrichment.csv",
            "--go_obo": "reference/go.obo",
            "--go_annotation": "reference/go.annot",
            "--kegg_id_map": "reference/kegg.id",
        }
        command = enrichment.build_command(
            EnrichmentRunParams(
                input_path=str(root / files["--input"]),
                output_path=str(root / files["--output"]),
                kegg_code="sly",
                id_type="ITAG4.1",
                go_obo=str(root / files["--go_obo"]),
                go_annotation=str(root / files["--go_annotation"]),
                kegg_id_map=str(root / files["--kegg_id_map"]),
            ),
            "audit-enrichment",
        )
    assert command[command.index("-v") + 1] == f"{mount_source}:/data/cygnusx"
    for flag, relative in files.items():
        assert command[command.index(flag) + 1] == f"/data/cygnusx/{relative}"


@pytest.mark.parametrize("root", ["/worker/data", "/srv/shared", "/data/cygnusx"])
def test_mount_supports_worker_daemon_and_existing_container_paths(root: str) -> None:
    mount = ToolDataMount("/srv/shared", "/worker/data")
    assert mount.container_path(f"{root}/ref/go.obo") == "/data/cygnusx/ref/go.obo"


@pytest.mark.parametrize(
    "path",
    [
        "input.txt",
        "/worker/data-backup/input.txt",
        "/worker/data/../private/input.txt",
        "/data/cygnusx/../../private/input.txt",
    ],
)
def test_mount_rejects_paths_outside_the_shared_data(path: str) -> None:
    with pytest.raises(ValidationError, match="共享数据挂载"):
        ToolDataMount("/srv/shared", "/worker/data").container_path(path)


def test_output_mapping_writes_back_to_the_original_worker_file(tmp_path: Path) -> None:
    mount = ToolDataMount(str(tmp_path), "/worker/data")
    output = mount.container_path("/worker/data/output/result.csv")
    daemon_file = tmp_path / Path(output).relative_to("/data/cygnusx")
    daemon_file.parent.mkdir()
    daemon_file.write_text("Source,Count\nGO,12\n", encoding="utf-8")
    assert (tmp_path / "output/result.csv").read_text(encoding="utf-8") == "Source,Count\nGO,12\n"

"""R Docker 富集容器命令构造测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from cygnusx.core.exceptions import ValidationError
from cygnusx.tools.enrichments.runner import EnrichmentDockerRunner, EnrichmentRunParams
from cygnusx.tools.enrichments.service import EnrichmentService

pytestmark = pytest.mark.unit


def test_runner_passes_local_go_and_kegg_references_to_r_container() -> None:
    runner = EnrichmentDockerRunner.__new__(EnrichmentDockerRunner)
    runner._settings = SimpleNamespace(
        enrichment_docker_network="cygnusx_app_net",
        enrichment_proxy_url="",
        enrichment_data_mount="/data/cygnusx",
        storage_path="/data/cygnusx",
        enrichment_memory="2g",
        enrichment_cpus=2.0,
        enrichment_docker_image="cygnusx-r-enrichment:v1",
    )
    params = EnrichmentRunParams(
        input_path="/data/cygnusx/users/u1/enrichments/tomato_project/t1/gene_list.txt",
        output_path="/data/cygnusx/users/u1/enrichments/tomato_project/t1/enrichment_result.csv",
        kegg_code="sly",
        id_type="ITAG4.1",
        go_obo="/data/cygnusx/cygnusx_data/reference/ITAG4.1/go-basic.obo",
        go_annotation="/data/cygnusx/cygnusx_data/reference/ITAG4.1/go.annot",
        kegg_id_map="/data/cygnusx/cygnusx_data/reference/ITAG4.1/kegg.id",
    )

    command = runner.build_command(params, "cygnusx-enrich-test")

    assert command[:3] == ["docker", "run", "--rm"]
    assert command[command.index("--network") + 1] == "cygnusx_app_net"
    assert "http_proxy=" not in " ".join(command)
    assert "--go_obo" in command
    assert "--go_annotation" in command
    assert "--kegg_id_map" in command
    assert command[command.index("--output") + 1] == params.output_path
    assert command[command.index("--kegg_code") + 1] == "sly"
    assert command[command.index("--p_value_cutoff") + 1] == "0.05"
    assert command[command.index("--q_value_cutoff") + 1] == "0.1"


def test_runner_uses_docker_default_bridge_when_network_is_not_configured() -> None:
    runner = EnrichmentDockerRunner.__new__(EnrichmentDockerRunner)
    runner._settings = SimpleNamespace(
        enrichment_docker_network="",
        enrichment_proxy_url="",
        enrichment_data_mount="/data/cygnusx",
        storage_path="/data/cygnusx",
        enrichment_memory="2g",
        enrichment_cpus=2.0,
        enrichment_docker_image="cygnusx-r-enrichment:v1",
    )
    params = EnrichmentRunParams(
        input_path="/data/cygnusx/users/u1/enrichments/project/t1/gene_list.txt",
        output_path="/data/cygnusx/users/u1/enrichments/project/t1/enrichment_result.csv",
        kegg_code="hsa",
        id_type="ENTREZID",
    )

    command = runner.build_command(params, "cygnusx-enrich-test")

    assert "--network" not in command


@pytest.mark.parametrize(
    ("storage_root", "mount_source", "reference_root"),
    [
        ("/data/cygnusx", "/data/cygnusx", "/data/cygnusx"),
        ("/data/omichub", "/data/omichub", "/data/omichub"),
        ("/data/omichub", "/data/omichub", "/data/cygnusx"),
        ("/worker/data", "/srv/shared", "/worker/data"),
        ("/worker/data", "/srv/shared", "/srv/shared"),
    ],
)
def test_runner_maps_all_file_arguments_to_the_data_volume(
    storage_root: str, mount_source: str, reference_root: str
) -> None:
    runner = EnrichmentDockerRunner.__new__(EnrichmentDockerRunner)
    runner._settings = SimpleNamespace(
        storage_path=storage_root,
        enrichment_data_mount=mount_source,
        enrichment_docker_network="",
        enrichment_proxy_url="",
        enrichment_memory="2g",
        enrichment_cpus=2.0,
        enrichment_docker_image="cygnusx-r-enrichment:v1",
    )
    run = "users/u1/projects/COP1-HY5_Example/runs/enrichment-20261022-141407"
    reference = "omichub_data/reference/ITAG4.1"
    params = EnrichmentRunParams(
        input_path=f"{storage_root}/{run}/input/gene_list.txt",
        output_path=f"{storage_root}/{run}/output/enrichment_result.csv",
        kegg_code="sly",
        id_type="ITAG4.1",
        go_obo=f"{reference_root}/{reference}/go-basic.obo",
        go_annotation=f"{reference_root}/{reference}/go.annot",
        kegg_id_map=f"{reference_root}/{reference}/kegg.id",
    )

    command = runner.build_command(params, "cygnusx-enrich-test")

    assert command[command.index("-v") + 1] == f"{mount_source}:/data/cygnusx"
    expected_paths = {
        "--input": f"/data/cygnusx/{run}/input/gene_list.txt",
        "--output": f"/data/cygnusx/{run}/output/enrichment_result.csv",
        "--go_obo": f"/data/cygnusx/{reference}/go-basic.obo",
        "--go_annotation": f"/data/cygnusx/{reference}/go.annot",
        "--kegg_id_map": f"/data/cygnusx/{reference}/kegg.id",
    }
    for flag, expected in expected_paths.items():
        assert command[command.index(flag) + 1] == expected


@pytest.mark.parametrize(
    "invalid_path",
    ["/data/omichub-backup/genes.txt", "/data/omichub/../private/genes.txt", "genes.txt"],
)
def test_runner_rejects_file_paths_outside_the_shared_volume(invalid_path: str) -> None:
    runner = EnrichmentDockerRunner.__new__(EnrichmentDockerRunner)
    runner._settings = SimpleNamespace(
        storage_path="/data/omichub",
        enrichment_data_mount="/data/omichub",
        enrichment_docker_network="",
        enrichment_proxy_url="",
        enrichment_memory="2g",
        enrichment_cpus=2.0,
        enrichment_docker_image="cygnusx-r-enrichment:v1",
    )
    params = EnrichmentRunParams(
        input_path=invalid_path,
        output_path="/data/omichub/output/enrichment_result.csv",
        kegg_code="sly",
        id_type="ITAG4.1",
    )

    with pytest.raises(ValidationError, match="共享数据挂载"):
        runner.build_command(params, "cygnusx-enrich-test")


def test_uploaded_csv_and_tsv_accept_only_gene_id_column() -> None:
    csv_genes = EnrichmentService._parse_uploaded_genes(
        None,
        b"GeneID,ignored_column\nGeneA,1\nGeneB,2\nGeneA,3\n",
        "genes.csv",
    )
    tsv_genes = EnrichmentService._parse_uploaded_genes(
        None,
        b"gene_id\tignored_column\nGeneA\t1\nGeneB\t2\n",
        "genes.tsv",
    )

    assert csv_genes == ["GeneA", "GeneB"]
    assert tsv_genes == ["GeneA", "GeneB"]


@pytest.mark.quarantine(reason="EnrichmentService 已无 _project_slug 属性，内部实现已改名")
def test_project_name_builds_safe_user_enrichment_directory() -> None:
    service = EnrichmentService.__new__(EnrichmentService)
    service._settings = SimpleNamespace(enrichment_data_mount="/data/cygnusx")

    project_name = service._normalize_project_name("  Tomato / COP1:HY5  ")
    project_slug = service._project_slug(project_name)
    work_dir = service._work_dir("user-1", project_slug, "task-1")

    assert project_name == "Tomato / COP1:HY5"
    assert project_slug == "Tomato_COP1_HY5"
    assert work_dir == Path("/data/cygnusx/users/user-1/enrichments/Tomato_COP1_HY5/task-1")

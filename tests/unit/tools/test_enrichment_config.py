"""富集参考文件随部署参考库目录解析。"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from cygnusx.tools.enrichments.config import EnrichmentConfigManager

pytestmark = pytest.mark.unit


def test_relative_references_follow_the_configured_reference_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reference_dir = tmp_path / "omichub_data" / "reference"
    reference_dir.mkdir(parents=True)
    monkeypatch.setattr(
        "cygnusx.tools.enrichments.config.get_settings",
        lambda: SimpleNamespace(
            reference_genomes_yaml=str(reference_dir / "reference_genomes.yaml")
        ),
    )
    manager = EnrichmentConfigManager("tool_configs/enrichments/species_config.yaml")

    species = manager.get_species("tomato_itag4_1")

    assert species is not None
    assert species.go_obo == str(reference_dir / "ITAG4.1" / "go-basic.obo")
    assert species.go_annotation == str(
        reference_dir / "ITAG4.1" / "ITAG4.1_blast2go_annot.annot_deal"
    )
    assert species.kegg_id_map == str(reference_dir / "ITAG4.1" / "ITAG4.1.kegg.id")
    assert species.analysis_types == ["GO", "KEGG"]
    assert manager.get_config() is manager.get_config()


def test_absolute_reference_paths_remain_supported(tmp_path: Path) -> None:
    config_path = tmp_path / "species.yaml"
    config_path.write_text(
        "species_list:\n"
        "  - id: custom\n"
        "    display_name: Custom\n"
        "    go_obo: /data/cygnusx/reference/go.obo\n"
        "    go_annotation: /data/cygnusx/reference/go.annot\n"
        "    kegg_id_map: /data/cygnusx/reference/kegg.id\n",
        encoding="utf-8",
    )

    species = EnrichmentConfigManager(config_path).get_species("custom")

    assert species is not None
    assert species.go_obo == "/data/cygnusx/reference/go.obo"
    assert species.go_annotation == "/data/cygnusx/reference/go.annot"
    assert species.kegg_id_map == "/data/cygnusx/reference/kegg.id"

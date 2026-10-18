"""The research tool pack must bind database adapters to their MCP presets."""

from pathlib import Path

import yaml


def test_research_pack_binds_database_mcp_presets() -> None:
    pack_path = Path(__file__).parents[2] / "data/ai/tools/research.yaml"
    pack = yaml.safe_load(pack_path.read_text(encoding="utf-8"))

    biothings_id = "7711b9e0-845c-5ff0-85a1-4578d15b009e"
    research_id = "9110de7a-d7bf-557c-94f1-50aa0a4af67b"
    assert pack["mcp_ids"] == [biothings_id, research_id]
    assert len(pack["mcp_tools"][biothings_id]) == 10
    assert len(pack["mcp_tools"][research_id]) == 26
    assert "cygnusx_gene_search" not in pack["builtin_tools"]
    assert "cygnusx_genome_lookup" not in pack["builtin_tools"]

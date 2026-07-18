from pathlib import Path

from omichub.infrastructure.mas.agent_capabilities import load_agent_capabilities


def test_loads_server_owned_agent_capabilities(tmp_path: Path) -> None:
    path = tmp_path / "agent_capabilities.yaml"
    path.write_text("agents:\n  agent-rnaseq: [rnaflow, quality-gate]\n")

    assert load_agent_capabilities(path) == {"agent-rnaseq": {"rnaflow", "quality-gate"}}
    assert load_agent_capabilities(tmp_path / "missing.yaml") == {}

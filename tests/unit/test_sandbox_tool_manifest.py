"""sandbox-agent 工具清单端点的纯 Python 单元测试。"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_AGENT_PATH = Path(__file__).resolve().parents[2] / "deploy" / "studio" / "sandbox_agent.py"
_spec = importlib.util.spec_from_file_location("sandbox_agent_manifest_test", _AGENT_PATH)
assert _spec is not None and _spec.loader is not None
sandbox_agent = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sandbox_agent)


@pytest.mark.unit
async def test_list_available_tools_filters_manifest_and_can_verify(tmp_path: Path, monkeypatch):
    manifest_path = tmp_path / "agent-tools.json"
    manifest_path.write_text(
        json.dumps(
            {
                "profile": "analysis-qc",
                "image": "test",
                "manifest_digest": "sha256:test",
                "tools": [
                    {
                        "name": "python",
                        "version": "unknown",
                        "path": sys.executable,
                        "probe_type": "cli",
                        "probe_status": "ok",
                    },
                    {"name": "samtools", "version": "1.20", "probe_status": "ok"},
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sandbox_agent, "TOOLS_MANIFEST_PATH", manifest_path)

    result = await sandbox_agent.list_available_tools(
        sandbox_agent.ToolsQueryRequest(pattern="py*", verify=True)
    )

    assert result["manifest_digest"] == "sha256:test"
    assert result["source"] == "runtime_probe"
    assert [tool["name"] for tool in result["tools"]] == ["python"]
    assert result["tools"][0]["probe_status"] == "ok"

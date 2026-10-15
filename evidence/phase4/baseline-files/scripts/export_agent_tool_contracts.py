"""Regenerate the shared tool contract from its single Python authority."""

from __future__ import annotations

import json
from pathlib import Path

from cygnusx.application.schemas.agent_tools import (
    GatewayResult,
    TaskStatusView,
    ToolProposal,
    capability_catalog,
)
from cygnusx.application.schemas.dataset import DataHandoff


def main() -> None:
    destination = Path("docs/contracts/cygnusx-agent-capabilities-v1.schema.json")
    contract = {
        "generated_from": "cygnusx.application.schemas.agent_tools",
        "schema_version": "1.0",
        "capabilities": [
            c.model_dump() for c in capability_catalog(include_write=True, include_dataset=True)
        ],
        "results": {
            "envelope": GatewayResult.model_json_schema(),
            "proposal": ToolProposal.model_json_schema(),
            "task_status": TaskStatusView.model_json_schema(),
        },
    }
    Path("docs/contracts/cygnusx-dataset-handoff-v1.schema.json").write_text(
        json.dumps(DataHandoff.model_json_schema(), ensure_ascii=False, indent=2) + "\n"
    )
    destination.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()

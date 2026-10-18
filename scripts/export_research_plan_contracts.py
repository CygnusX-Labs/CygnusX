"""Export strict model suggestions separately from server-owned plan/evidence views."""

import json
from pathlib import Path

from cygnusx.application.schemas.research_claims import (
    ArtifactCellRequest,
    ClaimAssessment,
    ClaimDraft,
)
from cygnusx.application.schemas.research_plan import ResearchPlanDraft, ResearchPlanView


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "docs/contracts"
    contracts = {
        "cygnusx-research-plan-v1.schema.json": ResearchPlanView,
        "cygnusx-research-plan-input-v1.schema.json": ResearchPlanDraft,
        "cygnusx-research-claim-input-v1.schema.json": ClaimDraft,
        "cygnusx-research-claim-v1.schema.json": ClaimAssessment,
        "cygnusx-research-artifact-cell-v1.schema.json": ArtifactCellRequest,
    }
    for name, model in contracts.items():
        (root / name).write_text(
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n"
        )


if __name__ == "__main__":
    main()

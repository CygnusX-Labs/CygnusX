"""Authenticated bridge for the fixed read-only research-data adapters."""

from typing import Any

from fastapi import APIRouter

from cygnusx.api.deps import CurrentUserId
from cygnusx.application.services.research_data_service import execute_research

router = APIRouter()

_RESEARCH_TOOLS = frozenset(
    {
        "cygnusx_genome_lookup",
        "cygnusx_genome_homology",
        "cygnusx_genome_region",
        "cygnusx_genome_sequence",
        "cygnusx_plant_search",
        "cygnusx_plant_get",
        "cygnusx_te_search",
        "cygnusx_te_get",
        "cygnusx_expression_studies",
        "cygnusx_expression_manifest",
        "cygnusx_pathway_get",
        "cygnusx_protein_resolve",
        "cygnusx_protein_features",
        "cygnusx_protein_sequence",
        "cygnusx_domain_get",
        "cygnusx_domain_proteins",
        "cygnusx_structure_search",
        "cygnusx_structure_get",
        "cygnusx_structure_prediction",
        "cygnusx_clinvar_search",
        "cygnusx_clinvar_get",
        "cygnusx_target_search",
        "cygnusx_target_associations",
        "cygnusx_target_evidence",
        "cygnusx_literature_get",
        "cygnusx_literature_annotations",
    }
)


@router.post("/{tool_name}", summary="Run a fixed read-only research-data adapter")
async def query_research_data(
    _user_id: CurrentUserId,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Keep provider selection and paths server-owned; no arbitrary URL is accepted."""
    if tool_name not in _RESEARCH_TOOLS:
        return {"success": False, "summary": "Research tool is not enabled", "data": None}
    return await execute_research(tool_name, arguments)

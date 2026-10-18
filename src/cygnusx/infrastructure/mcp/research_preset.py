"""Internal read-only preset for verified research database lookups."""

from __future__ import annotations

import uuid
from typing import Any

from cygnusx.application.schemas.tool_invocation import ToolInvocationContext
from cygnusx.application.services.research_data_service import execute_research

CYGNUSX_RESEARCH_SERVER_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "cygnusx-research-data.builtin")
CYGNUSX_RESEARCH_SERVER_NAME = "cygnusx-research-data"

_TOOLS: tuple[tuple[str, str, dict[str, Any], list[str]], ...] = (
    ("cygnusx_genome_lookup", "Ensembl object lookup", {"species": {"type": "string"}, "identifier": {"type": "string"}}, ["species", "identifier"]),
    ("cygnusx_plant_search", "Search Gramene plant records", {"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10}}, ["query"]),
    ("cygnusx_protein_resolve", "Resolve proteins through UniProt", {"query": {"type": "string"}, "organism_id": {"type": "integer"}}, ["query"]),
    ("cygnusx_structure_search", "Search experimental RCSB structures by reference accession", {"accession": {"type": "string"}}, ["accession"]),
    ("cygnusx_structure_prediction", "Retrieve AlphaFold prediction metadata", {"accession": {"type": "string"}}, ["accession"]),
    ("cygnusx_pathway_get", "Retrieve Reactome pathway knowledge", {"pathway_id": {"type": "string"}}, ["pathway_id"]),
    ("cygnusx_clinvar_search", "Search ClinVar identifiers and evidence records", {"query": {"type": "string"}}, ["query"]),
    ("cygnusx_literature_get", "Retrieve bounded Europe PMC article metadata", {"source": {"type": "string", "enum": ["MED", "PMC"], "default": "MED"}, "article_id": {"type": "string"}}, ["article_id"]),
    ("cygnusx_genome_homology", "Query Ensembl plant orthologues", {"species": {"type": "string"}, "identifier": {"type": "string"}, "target_species": {"type": "string"}}, ["species", "identifier"]),
    ("cygnusx_genome_region", "Query bounded Ensembl region overlaps", {"species": {"type": "string"}, "region": {"type": "string"}, "feature": {"type": "string", "default": "gene"}}, ["species", "region"]),
    ("cygnusx_genome_sequence", "Retrieve a bounded Ensembl sequence preview", {"identifier": {"type": "string"}, "sequence_type": {"type": "string", "enum": ["genomic", "cdna", "cds", "protein"], "default": "cdna"}}, ["identifier"]),
    ("cygnusx_plant_get", "Get a Gramene gene record", {"identifier": {"type": "string"}}, ["identifier"]),
    ("cygnusx_te_search", "Search Dfam transposable-element families", {"query": {"type": "string"}, "classification": {"type": "string"}, "clade": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10}}, []),
    ("cygnusx_te_get", "Get a Dfam family summary", {"accession": {"type": "string"}}, ["accession"]),
    ("cygnusx_expression_studies", "Search Expression Atlas study metadata", {"query": {"type": "string"}, "single_cell": {"type": "boolean", "default": False}, "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20}}, []),
    ("cygnusx_expression_manifest", "Resolve Expression Atlas manifest metadata", {"accession": {"type": "string"}, "single_cell": {"type": "boolean", "default": False}}, ["accession"]),
    ("cygnusx_protein_features", "Read bounded UniProt feature sections", {"accession": {"type": "string"}, "section": {"type": "string", "enum": ["all", "function", "location", "features"], "default": "all"}}, ["accession"]),
    ("cygnusx_protein_sequence", "Retrieve a UniProt FASTA sequence within inline limits", {"accession": {"type": "string"}}, ["accession"]),
    ("cygnusx_domain_get", "Get InterPro domains and families for a protein", {"accession": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20}}, ["accession"]),
    ("cygnusx_domain_proteins", "List proteins for an InterPro entry", {"interpro_id": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20}}, ["interpro_id"]),
    ("cygnusx_structure_get", "Get bounded RCSB experimental structure metadata", {"entry_id": {"type": "string"}}, ["entry_id"]),
    ("cygnusx_clinvar_get", "Get a bounded ClinVar VCV summary", {"vcv_accession": {"type": "string"}}, ["vcv_accession"]),
    ("cygnusx_target_search", "Search Open Targets entities with a fixed query", {"query": {"type": "string"}, "entity": {"type": "string", "enum": ["target", "disease", "drug"], "default": "target"}, "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10}}, ["query"]),
    ("cygnusx_target_associations", "Read Open Targets target associations", {"target_id": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10}}, ["target_id"]),
    ("cygnusx_target_evidence", "Read Open Targets evidence rows", {"target_id": {"type": "string"}, "disease_id": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10}}, ["target_id", "disease_id"]),
    ("cygnusx_literature_annotations", "Read bounded Europe PMC annotations", {"article_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 20}}, ["article_ids"]),
)

RESEARCH_TOOLS = [
    {
        "name": name,
        "description": description,
        "inputSchema": {"type": "object", "properties": properties, "required": required, "additionalProperties": False},
    }
    for name, description, properties, required in _TOOLS
]


async def research_handler(
    arguments: dict[str, Any],
    *,
    tool_name: str,
    context: ToolInvocationContext | None = None,
    **_kwargs: Any,
) -> dict[str, Any]:
    del context
    return await execute_research(tool_name, arguments)


RESEARCH_HANDLERS = {tool["name"]: research_handler for tool in RESEARCH_TOOLS}

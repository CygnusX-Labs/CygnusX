"""Internal read-only preset for verified research database lookups."""

from __future__ import annotations

import uuid
from typing import Any

from cygnusx.application.schemas.tool_invocation import ToolInvocationContext
from cygnusx.application.services.research_data_service import execute_research

CYGNUSX_RESEARCH_SERVER_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "cygnusx-research-data.builtin")
CYGNUSX_RESEARCH_SERVER_NAME = "cygnusx-research-data"

_TOOLS: tuple[tuple[str, str, dict[str, Any], list[str]], ...] = (
    (
        "cygnusx_genome_lookup",
        "Ensembl object lookup",
        {"species": {"type": "string"}, "identifier": {"type": "string"}},
        ["species", "identifier"],
    ),
    (
        "cygnusx_plant_search",
        "Search Gramene plant records",
        {
            "query": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
        },
        ["query"],
    ),
    (
        "cygnusx_protein_resolve",
        "Resolve proteins through UniProt",
        {"query": {"type": "string"}, "organism_id": {"type": "integer"}},
        ["query"],
    ),
    (
        "cygnusx_structure_search",
        "Search experimental RCSB structures by reference accession",
        {"accession": {"type": "string"}},
        ["accession"],
    ),
    (
        "cygnusx_structure_prediction",
        "Retrieve AlphaFold prediction metadata",
        {"accession": {"type": "string"}},
        ["accession"],
    ),
    (
        "cygnusx_pathway_get",
        "Retrieve Reactome pathway knowledge",
        {"pathway_id": {"type": "string"}},
        ["pathway_id"],
    ),
    (
        "cygnusx_clinvar_search",
        "Search ClinVar identifiers and evidence records",
        {"query": {"type": "string"}},
        ["query"],
    ),
    (
        "cygnusx_literature_get",
        "Retrieve bounded Europe PMC article metadata",
        {
            "source": {"type": "string", "enum": ["MED", "PMC"], "default": "MED"},
            "article_id": {"type": "string"},
        },
        ["article_id"],
    ),
    (
        "cygnusx_genome_homology",
        "Query Ensembl plant orthologues",
        {
            "species": {"type": "string"},
            "identifier": {"type": "string"},
            "target_species": {"type": "string"},
        },
        ["species", "identifier"],
    ),
    (
        "cygnusx_genome_region",
        "Query bounded Ensembl region overlaps",
        {
            "species": {"type": "string"},
            "region": {"type": "string"},
            "feature": {"type": "string", "default": "gene"},
        },
        ["species", "region"],
    ),
    (
        "cygnusx_genome_sequence",
        "Retrieve a bounded Ensembl sequence preview",
        {
            "identifier": {"type": "string"},
            "sequence_type": {
                "type": "string",
                "enum": ["genomic", "cdna", "cds", "protein"],
                "default": "cdna",
            },
        },
        ["identifier"],
    ),
    (
        "cygnusx_plant_get",
        "Get a Gramene gene record",
        {"identifier": {"type": "string"}},
        ["identifier"],
    ),
    (
        "cygnusx_te_search",
        "Search Dfam transposable-element families",
        {
            "query": {"type": "string"},
            "classification": {"type": "string"},
            "clade": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
        },
        [],
    ),
    (
        "cygnusx_te_get",
        "Get a Dfam family summary",
        {"accession": {"type": "string"}},
        ["accession"],
    ),
    (
        "cygnusx_expression_studies",
        "Search Expression Atlas study metadata",
        {
            "query": {"type": "string"},
            "single_cell": {"type": "boolean", "default": False},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
        },
        [],
    ),
    (
        "cygnusx_expression_manifest",
        "Resolve Expression Atlas manifest metadata",
        {"accession": {"type": "string"}, "single_cell": {"type": "boolean", "default": False}},
        ["accession"],
    ),
    (
        "cygnusx_protein_features",
        "Read bounded UniProt feature sections",
        {
            "accession": {"type": "string"},
            "section": {
                "type": "string",
                "enum": ["all", "function", "location", "features"],
                "default": "all",
            },
        },
        ["accession"],
    ),
    (
        "cygnusx_protein_sequence",
        "Retrieve a UniProt FASTA sequence within inline limits",
        {"accession": {"type": "string"}},
        ["accession"],
    ),
    (
        "cygnusx_domain_get",
        "Get InterPro domains and families for a protein",
        {
            "accession": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
        },
        ["accession"],
    ),
    (
        "cygnusx_domain_proteins",
        "List proteins for an InterPro entry",
        {
            "interpro_id": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
        },
        ["interpro_id"],
    ),
    (
        "cygnusx_structure_get",
        "Get bounded RCSB experimental structure metadata",
        {"entry_id": {"type": "string"}},
        ["entry_id"],
    ),
    (
        "cygnusx_clinvar_get",
        "Get bounded ClinVar evidence by VCV, RCV, SCV, or Variation ID; Allele ID is unsupported",
        {
            "vcv_accession": {"type": "string", "maxLength": 32},
            "identifier": {"type": "string", "maxLength": 32},
            "identifier_type": {
                "type": "string",
                "enum": ["VCV", "RCV", "SCV", "VariationID", "AlleleID"],
            },
        },
        [],
    ),
    (
        "cygnusx_target_search",
        "Search Open Targets entities with a fixed query",
        {
            "query": {"type": "string"},
            "entity": {
                "type": "string",
                "enum": ["target", "disease", "drug"],
                "default": "target",
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
        },
        ["query"],
    ),
    (
        "cygnusx_target_associations",
        "Read Open Targets target associations",
        {
            "target_id": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
        },
        ["target_id"],
    ),
    (
        "cygnusx_target_evidence",
        "Read Open Targets evidence rows",
        {
            "target_id": {"type": "string"},
            "disease_id": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
        },
        ["target_id", "disease_id"],
    ),
    (
        "cygnusx_literature_annotations",
        "Read bounded Europe PMC annotations",
        {
            "article_ids": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 20,
            }
        },
        ["article_ids"],
    ),
    (
        "cygnusx_string_resolve",
        "Resolve a protein identifier to bounded STRING candidates for one explicit NCBI taxon; does not select among ambiguous matches.",
        {
            "identifier": {"type": "string", "minLength": 1, "maxLength": 128},
            "taxon_id": {"type": "integer", "minimum": 1, "maximum": 1000000},
            "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 10},
        },
        ["identifier", "taxon_id"],
    ),
    (
        "cygnusx_string_network",
        "Retrieve bounded STRING protein partners for an explicit STRING ID and taxon. Network type is explicit; scores are association evidence, not causal probabilities.",
        {
            "string_id": {"type": "string", "minLength": 1, "maxLength": 80},
            "taxon_id": {"type": "integer", "minimum": 1, "maximum": 1000000},
            "network_type": {
                "type": "string",
                "enum": ["functional", "physical", "regulatory"],
            },
            "required_score": {"type": "integer", "minimum": 0, "maximum": 1000, "default": 400},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
        },
        ["string_id", "taxon_id", "network_type"],
    ),
)


def _input_schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


RESEARCH_TOOLS = [
    {
        "name": name,
        "description": description,
        "inputSchema": _input_schema(properties, required),
    }
    for name, description, properties, required in _TOOLS
]
_RESEARCH_SCHEMAS: dict[str, dict[str, Any]] = {
    name: _input_schema(properties, required) for name, _description, properties, required in _TOOLS
}


def validate_research_arguments(tool_name: str, arguments: dict[str, Any]) -> str | None:
    """Enforce the published tool schema at both BUILTIN and REST entry points."""
    schema = _RESEARCH_SCHEMAS.get(tool_name)
    if schema is None:
        return "Research tool is not enabled"
    if not isinstance(arguments, dict):
        return "Arguments must be an object"

    properties = schema["properties"]
    unknown = sorted(set(arguments) - set(properties))
    if unknown:
        return f"Unknown arguments: {', '.join(unknown)}"
    missing = sorted(set(schema.get("required", [])) - set(arguments))
    if missing:
        return f"Missing required arguments: {', '.join(missing)}"

    if tool_name == "cygnusx_clinvar_get":
        if any(name in arguments and arguments[name] is None for name in properties):
            return "ClinVar identifier arguments cannot be null"
        legacy = "vcv_accession" in arguments
        typed = "identifier" in arguments or "identifier_type" in arguments
        if legacy and typed:
            return "Use vcv_accession or identifier with identifier_type, not both"
        if typed and not {"identifier", "identifier_type"} <= set(arguments):
            return "identifier and identifier_type must be provided together"
        if not legacy and not typed:
            return "Provide vcv_accession or identifier with identifier_type"

    for name, value in arguments.items():
        field = properties[name]
        expected = field.get("type")
        valid = {
            "string": lambda item: isinstance(item, str),
            "integer": lambda item: type(item) is int,
            "number": lambda item: type(item) in {int, float},
            "boolean": lambda item: type(item) is bool,
            "array": lambda item: isinstance(item, list),
            "object": lambda item: isinstance(item, dict),
        }.get(expected)
        if valid is not None and not valid(value):
            return f"Argument {name} must be {expected}"
        if "enum" in field and value not in field["enum"]:
            return f"Argument {name} must be one of: {', '.join(map(str, field['enum']))}"
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in field and value < field["minimum"]:
                return f"Argument {name} must be at least {field['minimum']}"
            if "maximum" in field and value > field["maximum"]:
                return f"Argument {name} must be at most {field['maximum']}"
        if isinstance(value, list):
            if "minItems" in field and len(value) < field["minItems"]:
                return f"Argument {name} must contain at least {field['minItems']} items"
            if "maxItems" in field and len(value) > field["maxItems"]:
                return f"Argument {name} must contain at most {field['maxItems']} items"
            item_type = field.get("items", {}).get("type")
            if item_type == "string" and any(not isinstance(item, str) for item in value):
                return f"Items in {name} must be strings"
        if isinstance(value, str):
            if "minLength" in field and len(value) < field["minLength"]:
                return f"Argument {name} is too short"
            if "maxLength" in field and len(value) > field["maxLength"]:
                return f"Argument {name} is too long"
    return None


async def research_handler(
    arguments: dict[str, Any],
    *,
    tool_name: str,
    context: ToolInvocationContext | None = None,
    **_kwargs: Any,
) -> dict[str, Any]:
    del context
    error = validate_research_arguments(tool_name, arguments)
    if error:
        return {"success": False, "summary": error, "data": None}
    return await execute_research(tool_name, arguments)


RESEARCH_HANDLERS = {tool["name"]: research_handler for tool in RESEARCH_TOOLS}

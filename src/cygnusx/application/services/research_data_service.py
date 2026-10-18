"""Bounded read-only adapters shared by the internal research-data MCP preset."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any
from urllib.parse import quote
from weakref import WeakKeyDictionary

import httpx

_HOSTS = {
    "ensembl": "https://rest.ensembl.org",
    "gramene": "https://data.gramene.org/v69",
    "uniprot": "https://rest.uniprot.org",
    "rcsb_search": "https://search.rcsb.org",
    "rcsb": "https://data.rcsb.org",
    "alphafold": "https://alphafold.ebi.ac.uk/api",
    "reactome": "https://reactome.org/ContentService/data",
    "clinvar": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
    "europepmc": "https://www.ebi.ac.uk/europepmc/webservices/rest",
}
_CLIENTS: WeakKeyDictionary[asyncio.AbstractEventLoop, httpx.AsyncClient] = WeakKeyDictionary()
_MAX_RESPONSE = 2 * 1024 * 1024
_MAX_OUTPUT = 3000
_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


def _client() -> httpx.AsyncClient:
    loop = asyncio.get_running_loop()
    client = _CLIENTS.get(loop)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=3.0),
            follow_redirects=False,
            headers={"accept": "application/json"},
        )
        _CLIENTS[loop] = client
    return client


async def close_research_clients() -> None:
    clients = list(_CLIENTS.values())
    _CLIENTS.clear()
    for client in clients:
        await client.aclose()


def _bounded(result: dict[str, Any]) -> dict[str, Any]:
    if len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()) <= _MAX_OUTPUT:
        return result
    return {
        "success": result.get("success", False),
        "summary": str(result.get("summary", ""))[:256],
        "data": {"truncated": True, "provider": result.get("data", {}).get("provider")},
        "truncated": True,
    }


async def _request(
    provider: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
) -> Any:
    if provider not in _HOSTS or path.startswith("/") or ".." in path.split("/"):
        raise ValueError("invalid fixed provider path")
    response = await _client().request(
        "POST" if payload is not None else "GET",
        f"{_HOSTS[provider]}/{path}",
        params=params,
        json=payload,
    )
    response.raise_for_status()
    if len(response.content) > _MAX_RESPONSE:
        raise ValueError("provider response exceeds 2 MiB")
    if "json" not in response.headers.get("content-type", "").lower():
        raise ValueError("provider returned a non-JSON response")
    return response.json()


async def _request_text(provider: str, path: str, *, params: dict[str, Any] | None = None) -> str:
    if provider not in _HOSTS or path.startswith("/") or ".." in path.split("/"):
        raise ValueError("invalid fixed provider path")
    response = await _client().get(f"{_HOSTS[provider]}/{path}", params=params)
    response.raise_for_status()
    if len(response.content) > _MAX_RESPONSE:
        raise ValueError("provider response exceeds 2 MiB")
    return response.text


def _ok(summary: str, provider: str, data: Any) -> dict[str, Any]:
    return _bounded({"success": True, "summary": summary, "data": {"provider": provider, "result": data}})


async def execute_research(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        if tool_name == "cygnusx_genome_lookup":
            species = str(arguments.get("species", "")).strip()
            identifier = str(arguments.get("identifier", "")).strip()
            if not _ID.fullmatch(species) or not _ID.fullmatch(identifier):
                raise ValueError("species and identifier are required and bounded")
            result = await _request(
                "ensembl",
                f"lookup/id/{quote(identifier, safe='')}",
                params={"species": species},
            )
            return _ok("Ensembl object lookup", "ensembl", {"species": species, "result": result})

        if tool_name == "cygnusx_genome_homology":
            species = str(arguments.get("species", "")).strip()
            identifier = str(arguments.get("identifier", "")).strip()
            target = str(arguments.get("target_species", "")).strip()
            if not _ID.fullmatch(species) or not _ID.fullmatch(identifier):
                raise ValueError("species and identifier are required and bounded")
            params: dict[str, Any] = {"compara": "plants", "type": "orthologues"}
            if target:
                if not _ID.fullmatch(target):
                    raise ValueError("target_species is invalid")
                params["target_species"] = target
            result = await _request("ensembl", f"homology/id/{quote(species, safe='')}/{quote(identifier, safe='')}", params=params)
            return _ok("Ensembl plant homology", "ensembl", {"species": species, "result": result})

        if tool_name == "cygnusx_genome_region":
            species = str(arguments.get("species", "")).strip()
            region = str(arguments.get("region", "")).strip()
            feature = str(arguments.get("feature", "gene"))
            if not _ID.fullmatch(species) or not re.fullmatch(r"[A-Za-z0-9_.-]+:[0-9]+\.\.[0-9]+(?::[-+1])?", region):
                raise ValueError("species and region are invalid")
            if feature not in {"gene", "transcript", "cds", "exon", "variation"}:
                raise ValueError("unsupported region feature")
            result = await _request("ensembl", f"overlap/region/{quote(species, safe='')}/{quote(region, safe=':')}", params={"feature": feature})
            return _ok("Ensembl region overlap", "ensembl", {"species": species, "region": region, "feature": feature, "result": result})

        if tool_name == "cygnusx_genome_sequence":
            identifier = str(arguments.get("identifier", "")).strip()
            sequence_type = str(arguments.get("sequence_type", "cdna"))
            if not _ID.fullmatch(identifier) or sequence_type not in {"genomic", "cdna", "cds", "protein"}:
                raise ValueError("identifier or sequence_type is invalid")
            result = await _request("ensembl", f"sequence/id/{quote(identifier, safe='')}", params={"type": sequence_type})
            sequence = str(result.get("seq", "")) if isinstance(result, dict) else ""
            return _ok("Ensembl sequence", "ensembl", {"id": identifier, "type": sequence_type, "length": len(sequence), "sequence_preview": sequence[:3000], "truncated": len(sequence) > 3000})

        if tool_name == "cygnusx_plant_search":
            query = str(arguments.get("query", "")).strip()
            limit = int(arguments.get("limit", 10))
            if not query or len(query) > 2048 or not 1 <= limit <= 50:
                raise ValueError("query must be 1-2048 characters and limit 1-50")
            result = await _request("gramene", "search", params={"q": query, "rows": limit})
            return _ok("Gramene plant search", "gramene", {"query": query, "result": result})

        if tool_name == "cygnusx_plant_get":
            identifier = str(arguments.get("identifier", "")).strip()
            if not _ID.fullmatch(identifier):
                raise ValueError("identifier is required and bounded")
            result = await _request("gramene", "genes", params={"idList": identifier, "rows": 10})
            return _ok("Gramene gene detail", "gramene", {"identifier": identifier, "result": result})

        if tool_name in {"cygnusx_te_search", "cygnusx_te_get"}:
            if tool_name == "cygnusx_te_search":
                query = str(arguments.get("query", "")).strip()
                classification = str(arguments.get("classification", "")).strip()
                clade = str(arguments.get("clade", "")).strip()
                if not query and not classification:
                    raise ValueError("query or classification is required")
                te_params: dict[str, Any] = {"format": "summary", "limit": max(1, min(int(arguments.get("limit", 10)), 50))}
                if query:
                    te_params["name"] = query[:200]
                if classification:
                    te_params["classification"] = classification[:512]
                if clade:
                    te_params["clade"] = clade[:256]
                result = await _request("dfam", "families", params=te_params)
                return _ok("Dfam family search", "dfam", {"query": query, "classification": classification, "clade": clade, "result": result})
            accession = str(arguments.get("accession", "")).strip()
            if not _ID.fullmatch(accession):
                raise ValueError("Dfam accession is required")
            result = await _request("dfam", f"families/{quote(accession, safe='')}", params={"format": "summary"})
            return _ok("Dfam family detail", "dfam", {"accession": accession, "result": result})

        if tool_name == "cygnusx_expression_studies":
            provider = "sc_atlas" if bool(arguments.get("single_cell", False)) else "atlas"
            result = await _request(provider, "experiments")
            query = str(arguments.get("query", "")).strip().casefold()
            limit = max(1, min(int(arguments.get("limit", 20)), 50))
            studies = result if isinstance(result, list) else result.get("experiments", result.get("entries", []))
            if query:
                studies = [item for item in studies if query in str(item).casefold()]
            return _ok("Expression Atlas study directory", provider, {"query": query, "studies": studies[:limit], "total_matches": len(studies)})

        if tool_name == "cygnusx_expression_manifest":
            accession = str(arguments.get("accession", "")).strip()
            if not _ID.fullmatch(accession):
                raise ValueError("experiment accession is required")
            provider = "sc_atlas" if bool(arguments.get("single_cell", False)) else "atlas"
            result = await _request(provider, "experiments")
            studies = result if isinstance(result, list) else result.get("experiments", result.get("entries", []))
            matches = [item for item in studies if accession.casefold() in str(item).casefold()]
            return _ok("Expression Atlas manifest metadata", provider, {"accession": accession, "matches": matches[:10], "found": bool(matches)})

        if tool_name == "cygnusx_protein_resolve":
            query = str(arguments.get("query", "")).strip()
            organism = arguments.get("organism_id")
            if not query or len(query) > 512 or (organism is not None and not str(organism).isdigit()):
                raise ValueError("query and optional numeric organism_id are required")
            expression = f"({query})"
            if organism is not None:
                expression += f" AND (organism_id:{organism})"
            result = await _request(
                "uniprot",
                "uniprotkb/search",
                params={"query": expression, "format": "json", "size": 10, "fields": "accession,id,protein_name,organism_id,length"},
            )
            return _ok("UniProt protein resolve", "uniprot", result)

        if tool_name == "cygnusx_protein_features":
            accession = str(arguments.get("accession", "")).strip()
            section = str(arguments.get("section", "all"))
            if not _ID.fullmatch(accession) or section not in {"all", "function", "location", "features"}:
                raise ValueError("accession or section is invalid")
            entry = await _request("uniprot", f"uniprotkb/{quote(accession, safe='')}.json")
            comments = entry.get("comments", []) if isinstance(entry, dict) else []
            features = entry.get("features", []) if isinstance(entry, dict) else []
            if section == "function":
                comments, features = [item for item in comments if item.get("commentType") == "FUNCTION"], []
            elif section == "location":
                comments, features = [item for item in comments if item.get("commentType") == "SUBCELLULAR LOCATION"], []
            elif section == "features":
                comments = []
            return _ok("UniProt protein features", "uniprot", {"accession": accession, "section": section, "comments": comments[:100], "features": features[:200], "truncated": len(comments) > 100 or len(features) > 200})

        if tool_name == "cygnusx_protein_sequence":
            accession = str(arguments.get("accession", "")).strip()
            if not _ID.fullmatch(accession):
                raise ValueError("UniProt accession is required")
            text = await _request_text("uniprot", f"uniprotkb/{quote(accession, safe='')}.fasta")
            sequence = "".join(text.splitlines()[1:])
            if len(sequence) > 3000:
                return {"success": False, "summary": "Sequence exceeds inline budget; file export is disabled.", "data": None}
            return _ok("UniProt FASTA sequence", "uniprot", {"accession": accession, "fasta": text, "length": len(sequence)})

        if tool_name in {"cygnusx_domain_get", "cygnusx_domain_proteins"}:
            if tool_name == "cygnusx_domain_get":
                accession = str(arguments.get("accession", "")).strip()
                if not _ID.fullmatch(accession):
                    raise ValueError("UniProt accession is required")
                path = f"entry/interpro/protein/uniprot/{quote(accession, safe='')}/"
                key = "accession"
                value = accession
            else:
                interpro_id = str(arguments.get("interpro_id", "")).strip()
                if not _ID.fullmatch(interpro_id):
                    raise ValueError("InterPro accession is required")
                path = f"protein/uniprot/entry/interpro/{quote(interpro_id, safe='')}/"
                key = "interpro_id"
                value = interpro_id
            result = await _request("interpro", path, params={"page_size": max(1, min(int(arguments.get("limit", 20)), 50))})
            return _ok("InterPro protein annotations", "interpro", {key: value, "result": result})

        if tool_name == "cygnusx_structure_get":
            entry_id = str(arguments.get("entry_id", "")).strip().upper()
            if not re.fullmatch(r"[0-9][A-Za-z0-9]{3}", entry_id):
                raise ValueError("entry_id must be a four-character PDB identifier")
            result = await _request("rcsb", f"rest/v1/core/entry/{entry_id.lower()}")
            return _ok("RCSB experimental entry", "rcsb", {"entry_id": entry_id, "result": result})

        if tool_name == "cygnusx_structure_search":
            accession = str(arguments.get("accession", "")).strip()
            if not _ID.fullmatch(accession):
                raise ValueError("accession is required")
            result = await _request(
                "rcsb_search",
                "rcsbsearch/v2/query",
                payload={
                    "query": {"type": "terminal", "service": "text", "parameters": {"attribute": "rcsb_polymer_entity_container_identifiers.reference_sequence_identifiers.database_accession", "operator": "exact_match", "value": accession}},
                    "return_type": "polymer_entity",
                    "request_options": {"paginate": {"start": 0, "rows": 10}},
                },
            )
            return _ok("RCSB structure search", "rcsb_search", result)

        if tool_name == "cygnusx_structure_prediction":
            accession = str(arguments.get("accession", "")).strip()
            if not _ID.fullmatch(accession):
                raise ValueError("UniProt accession is required")
            result = await _request("alphafold", f"prediction/{quote(accession, safe='')}")
            return _ok("AlphaFold prediction metadata", "alphafold", result)

        if tool_name == "cygnusx_pathway_get":
            pathway_id = str(arguments.get("pathway_id", "")).strip()
            if not re.fullmatch(r"R-[A-Z]{3}-[0-9]+", pathway_id):
                raise ValueError("pathway_id must be a Reactome stable identifier")
            result = await _request("reactome", f"query/{quote(pathway_id, safe='-')}")
            return _ok("Reactome pathway knowledge", "reactome", result)

        if tool_name == "cygnusx_clinvar_search":
            query = str(arguments.get("query", "")).strip()
            if not query or len(query) > 1024:
                raise ValueError("query must be 1-1024 characters")
            result = await _request("clinvar", "esearch.fcgi", params={"db": "clinvar", "term": query, "retmode": "json", "retmax": 20})
            return _ok("ClinVar search", "clinvar", result)

        if tool_name == "cygnusx_clinvar_get":
            accession = str(arguments.get("vcv_accession", "")).strip()
            if not re.fullmatch(r"VCV[0-9]+(?:\.[0-9]+)?", accession):
                raise ValueError("vcv_accession must use VCV form")
            result = await _request("clinvar", "esummary.fcgi", params={"db": "clinvar", "id": accession, "retmode": "json"})
            return _ok("ClinVar VCV summary", "clinvar", {"vcv_accession": accession, "result": result})

        if tool_name in {"cygnusx_target_search", "cygnusx_target_associations", "cygnusx_target_evidence"}:
            if tool_name == "cygnusx_target_search":
                query = str(arguments.get("query", "")).strip()
                entity = str(arguments.get("entity", "target"))
                if not query or len(query) > 256 or entity not in {"target", "disease", "drug"}:
                    raise ValueError("entity and query are invalid")
                gql = "query Search($q:String!,$types:[String!]!,$page:Pagination!){search(queryString:$q,entityNames:$types,page:$page){total hits{id name entity}}}"
                variables: dict[str, Any] = {"q": query, "types": [entity], "page": {"index": 0, "size": max(1, min(int(arguments.get("limit", 10)), 50))}}
            elif tool_name == "cygnusx_target_associations":
                target = str(arguments.get("target_id", "")).strip()
                if not re.fullmatch(r"ENSG[0-9]+", target):
                    raise ValueError("target_id must be an ENSG identifier")
                gql = "query TargetAssociations($id:String!,$page:Pagination!){target(ensemblId:$id){id approvedSymbol associatedDiseases(page:$page){count rows{disease{id name} score}}}}"
                variables = {"id": target, "page": {"index": 0, "size": max(1, min(int(arguments.get("limit", 10)), 50))}}
            else:
                target = str(arguments.get("target_id", "")).strip()
                disease = str(arguments.get("disease_id", "")).strip()
                if not re.fullmatch(r"ENSG[0-9]+", target) or not _ID.fullmatch(disease):
                    raise ValueError("target_id or disease_id is invalid")
                gql = "query TargetEvidence($id:String!,$disease:String!,$size:Int!){target(ensemblId:$id){id evidences(efoIds:[$disease],size:$size){count rows{datasourceId datatypeId score}}}}"
                variables = {"id": target, "disease": disease, "size": max(1, min(int(arguments.get("limit", 10)), 50))}
            result = await _request("opentargets", "", payload={"query": gql, "variables": variables})
            if isinstance(result, dict) and result.get("errors") and not result.get("data"):
                raise ValueError("Open Targets returned GraphQL errors without data")
            return _ok("Open Targets query", "opentargets", result)

        if tool_name == "cygnusx_literature_get":
            source = str(arguments.get("source", "MED"))
            article_id = str(arguments.get("article_id", "")).strip()
            if source not in {"MED", "PMC"} or not _ID.fullmatch(article_id):
                raise ValueError("source must be MED or PMC and article_id is required")
            result = await _request("europepmc", f"{source}/{quote(article_id, safe='')}", params={"format": "json"})
            return _ok("Europe PMC article", "europepmc", result)

        if tool_name == "cygnusx_literature_annotations":
            article_ids = arguments.get("article_ids")
            if not isinstance(article_ids, list) or not 1 <= len(article_ids) <= 20 or any(not re.fullmatch(r"(?:MED|PMC|PPR):[A-Za-z0-9_.-]{1,32}", str(item)) for item in article_ids):
                raise ValueError("article_ids must contain 1-20 source-qualified IDs")
            result = await _request("europepmc", "annotationsByArticleIds", params={"articleIds": ",".join(article_ids), "format": "JSON"})
            return _ok("Europe PMC article annotations", "europepmc", {"article_ids": article_ids, "result": result})

        return {"success": False, "summary": "Research tool is not registered", "data": None}
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        return {"success": False, "summary": f"Research provider request failed: {exc}", "data": None}

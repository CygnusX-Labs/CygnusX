"""Fixed, bounded read-only adapters for documented research-data providers.

Large assets and unverified analysis endpoints are intentionally not exposed here.
"""

from __future__ import annotations

import asyncio
import re
import time
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote

import httpx
from fastmcp import FastMCP

from tools.research_common import envelope, provider_client

PROVIDERS = {
    "ensembl": "https://rest.ensembl.org",
    "gramene": "https://data.gramene.org/v69",
    "dfam": "https://dfam.org/api",
    "atlas": "https://www.ebi.ac.uk/gxa/json",
    "sc_atlas": "https://www.ebi.ac.uk/gxa/sc/json",
    "uniprot": "https://rest.uniprot.org",
    "interpro": "https://www.ebi.ac.uk/interpro/api",
    "rcsb": "https://data.rcsb.org",
    "rcsb_search": "https://search.rcsb.org",
    "alphafold": "https://alphafold.ebi.ac.uk/api",
    "reactome": "https://reactome.org/ContentService/data",
    "clinvar": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
    "opentargets": "https://api.platform.opentargets.org/api/v4/graphql",
    "europepmc": "https://www.ebi.ac.uk/europepmc/webservices/rest",
    "europepmc_annotations": "https://www.ebi.ac.uk/europepmc/annotations_api",
}
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_ATLAS_DIRECTORY_BYTES = 10 * 1024 * 1024
MAX_PAGE = 50
ATLAS_CACHE_TTL_SECONDS = 6 * 60 * 60
TIMEOUT = httpx.Timeout(15.0, connect=3.0)
_ACCESSION = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_PDB_ID = re.compile(r"^[0-9][A-Za-z0-9]{3}$")
_ATLAS_CACHE: dict[str, tuple[float, Any]] = {}
_ATLAS_CACHE_LOCK = asyncio.Lock()


async def _request_json(
    provider: str,
    path: str = "",
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
) -> Any:
    if provider not in PROVIDERS:
        raise ValueError("unknown provider")
    if path and (path.startswith("/") or ".." in path.split("/")):
        raise ValueError("provider path must be relative and fixed by the adapter")
    url = f"{PROVIDERS[provider]}/{path}" if path else PROVIDERS[provider]
    response = await provider_client(TIMEOUT).request(
        "POST" if json_body is not None or data is not None else "GET",
        url,
        params=params,
        json=json_body,
        data=data,
        headers={"accept": "application/json"},
    )
    response.raise_for_status()
    if len(response.content) > MAX_RESPONSE_BYTES:
        raise ValueError("provider response exceeds 2 MiB")
    if "json" not in response.headers.get("content-type", "").lower():
        raise ValueError("provider returned a non-JSON response")
    return response.json()


async def _atlas_directory(provider: str) -> Any:
    if provider not in {"atlas", "sc_atlas"}:
        raise ValueError("unknown Atlas catalog")
    cached = _ATLAS_CACHE.get(provider)
    now = time.monotonic()
    if cached and cached[0] > now:
        return cached[1]
    async with _ATLAS_CACHE_LOCK:
        cached = _ATLAS_CACHE.get(provider)
        now = time.monotonic()
        if cached and cached[0] > now:
            return cached[1]
        response = await provider_client(TIMEOUT).get(
            f"{PROVIDERS[provider]}/experiments", headers={"accept": "application/json"}
        )
        response.raise_for_status()
        if len(response.content) > MAX_ATLAS_DIRECTORY_BYTES:
            raise ValueError("Atlas directory exceeds the 10 MiB catalog budget")
        if "json" not in response.headers.get("content-type", "").lower():
            raise ValueError("Atlas returned a non-JSON directory")
        data = response.json()
        _ATLAS_CACHE[provider] = (time.monotonic() + ATLAS_CACHE_TTL_SECONDS, data)
        return data


async def _request_xml(provider: str, path: str, params: dict[str, Any]) -> ET.Element:
    if provider not in PROVIDERS or not path or path.startswith("/") or ".." in path.split("/"):
        raise ValueError("invalid fixed provider request")
    response = await provider_client(TIMEOUT).get(
        f"{PROVIDERS[provider]}/{path}",
        params=params,
        headers={"accept": "application/xml"},
    )
    response.raise_for_status()
    if len(response.content) > MAX_RESPONSE_BYTES:
        raise ValueError("provider response exceeds 2 MiB")
    if "xml" not in response.headers.get("content-type", "").lower():
        raise ValueError("provider returned a non-XML response")
    return ET.fromstring(response.content)


def _xml_projection(root: ET.Element, max_nodes: int = 500) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for element in root.iter():
        if len(facts) == max_nodes:
            break
        text = (element.text or "").strip()
        if text or element.attrib:
            facts.append(
                {
                    "element": element.tag.rsplit("}", 1)[-1],
                    "attributes": dict(element.attrib),
                    "text": text[:512] or None,
                }
            )
    return facts


def _limit(value: int) -> int:
    if not 1 <= value <= MAX_PAGE:
        raise ValueError(f"limit must be between 1 and {MAX_PAGE}")
    return value


def _identifier(value: str, label: str = "identifier") -> str:
    value = value.strip()
    if not _ACCESSION.fullmatch(value):
        raise ValueError(f"invalid {label}")
    return value


def _envelope(summary: str, data: Any) -> dict[str, Any]:
    return envelope(True, summary, data)


def _error(provider: str, exc: Exception) -> dict[str, Any]:
    return envelope(False, f"{provider} request failed: {exc}")


def register_genome(mcp: FastMCP, _api: Any) -> None:
    @mcp.tool()
    async def cygnusx_genome_lookup(species: str, identifier: str) -> dict[str, Any]:
        """Look up a gene/transcript/protein on Ensembl; species must be explicit."""
        try:
            species = _identifier(species, "species")
            identifier = _identifier(identifier)
            result = await _request_json("ensembl", f"lookup/id/{quote(identifier, safe='')}")
            returned_species = result.get("species") if isinstance(result, dict) else None
            if returned_species and returned_species.casefold() != species.casefold():
                raise ValueError(
                    f"requested species {species!r} does not match provider species {returned_species!r}"
                )
            return _envelope(
                "Ensembl object lookup",
                {
                    "species": species,
                    "requested_id": identifier,
                    "result": result,
                    "provider": "Ensembl REST; object species is reported by the provider",
                },
            )
        except Exception as exc:
            return _error("Ensembl", exc)

    @mcp.tool()
    async def cygnusx_genome_homology(
        species: str, identifier: str, target_species: str = ""
    ) -> dict[str, Any]:
        """Query Ensembl plant orthologues with compara=plants; no sequence alignment is returned."""
        try:
            species = _identifier(species, "species")
            identifier = _identifier(identifier)
            params: dict[str, Any] = {"compara": "plants", "type": "orthologues"}
            if target_species:
                params["target_species"] = _identifier(target_species, "target species")
            result = await _request_json(
                "ensembl",
                f"homology/id/{quote(species, safe='')}/{quote(identifier, safe='')}",
                params=params,
            )
            for item in result.get("data", []):
                for homology in item.get("homologies", []):
                    homology.pop("align_seq", None)
            return _envelope(
                "Ensembl plant homology lookup",
                {
                    "source_species": species,
                    "target_species": target_species or None,
                    "compara": "plants",
                    "result": result,
                },
            )
        except Exception as exc:
            return _error("Ensembl", exc)

    @mcp.tool()
    async def cygnusx_genome_region(
        species: str, region: str, feature: str = "gene", limit: int = 50
    ) -> dict[str, Any]:
        """Query Ensembl region overlaps. Region syntax and species are explicit."""
        try:
            if feature not in {"gene", "transcript", "cds", "exon", "variation"}:
                raise ValueError("unsupported region feature")
            species = _identifier(species, "species")
            if not re.fullmatch(r"[A-Za-z0-9_.-]+:[0-9]+\.\.[0-9]+(?::[-+1])?", region):
                raise ValueError("region must use contig:start..end[:strand] coordinates")
            result = await _request_json(
                "ensembl",
                f"overlap/region/{quote(species, safe='')}/{quote(region, safe=':')}",
                params={"feature": feature},
            )
            if isinstance(result, list):
                result = result[: _limit(limit)]
            return _envelope(
                "Ensembl region overlap",
                {
                    "species": species,
                    "region": region,
                    "feature": feature,
                    "result": result,
                },
            )
        except Exception as exc:
            return _error("Ensembl", exc)

    @mcp.tool()
    async def cygnusx_genome_sequence(
        identifier: str, sequence_type: str = "cdna"
    ) -> dict[str, Any]:
        """Retrieve a short Ensembl sequence; large sequences are returned as bounded previews."""
        try:
            identifier = _identifier(identifier)
            if sequence_type not in {"genomic", "cdna", "cds", "protein"}:
                raise ValueError("sequence_type must be genomic, cdna, cds or protein")
            result = await _request_json(
                "ensembl",
                f"sequence/id/{quote(identifier, safe='')}",
                params={"type": sequence_type},
            )
            sequence = str(result.get("seq", ""))
            return _envelope(
                "Ensembl sequence",
                {
                    "id": result.get("id", identifier),
                    "type": sequence_type,
                    "length": len(sequence),
                    "sequence_preview": sequence[:3000],
                    "truncated": len(sequence) > 3000,
                    "note": "Long sequence export to a user file is not enabled in this MCP adapter.",
                },
            )
        except Exception as exc:
            return _error("Ensembl", exc)


def register_plant_te(mcp: FastMCP, _api: Any) -> None:
    @mcp.tool()
    async def cygnusx_plant_search(query: str, limit: int = 10, offset: int = 0) -> dict[str, Any]:
        """Search Gramene v69 gene/plant knowledge index with bounded paging."""
        try:
            query = query.strip()
            if not query or len(query) > 512 or offset < 0 or offset > 10000:
                raise ValueError("query must be 1-512 characters; offset must be 0-10000")
            if any(char in query for char in ":()[]{}^~*?"):
                raise ValueError("plant search accepts literal terms, not raw Solr expressions")
            query = f'"{query.replace(chr(34), chr(92) + chr(34))}"'
            result = await _request_json(
                "gramene",
                "search",
                params={"q": query, "rows": _limit(limit), "start": offset, "wt": "json"},
            )
            return _envelope(
                "Gramene v69 search",
                {
                    "release": "v69",
                    "query": query,
                    "offset": offset,
                    "result": result,
                    "taxonomy_note": "Gramene taxon_id is provider-specific; do not treat as NCBI taxid.",
                },
            )
        except Exception as exc:
            return _error("Gramene", exc)

    @mcp.tool()
    async def cygnusx_plant_get(identifier: str) -> dict[str, Any]:
        """Get Gramene gene records for an explicit ID; preserves provider taxonomy identifiers."""
        try:
            identifier = _identifier(identifier)
            result = await _request_json(
                "gramene", "genes", params={"idList": identifier, "rows": 10}
            )
            return _envelope(
                "Gramene gene details",
                {
                    "release": "v69",
                    "input_id": identifier,
                    "result": result,
                    "taxonomy_note": "Gramene taxon_id is provider-specific; map and validate before reuse.",
                },
            )
        except Exception as exc:
            return _error("Gramene", exc)

    @mcp.tool()
    async def cygnusx_te_search(
        query: str = "", classification: str = "", clade: str = "", limit: int = 10
    ) -> dict[str, Any]:
        """Search Dfam families; classification and clade are preserved as distinct filters."""
        try:
            if not query.strip() and not classification.strip():
                raise ValueError("provide query or a full classification path")
            params: dict[str, Any] = {"format": "summary", "limit": _limit(limit)}
            if query.strip():
                params["name"] = query.strip()[:200]
            if classification.strip():
                params["classification"] = classification.strip()[:512]
            if clade.strip():
                params["clade"] = clade.strip()[:256]
            result = await _request_json("dfam", "families", params=params)
            return _envelope(
                "Dfam family search",
                {
                    "filters": {"query": query, "classification": classification, "clade": clade},
                    "result": result,
                    "note": "Classification results may include descendants; do not interpret family totals as organism counts.",
                },
            )
        except Exception as exc:
            return _error("Dfam", exc)

    @mcp.tool()
    async def cygnusx_te_get(accession: str) -> dict[str, Any]:
        """Get a Dfam family summary by accession; large family assets are excluded."""
        try:
            accession = _identifier(accession, "Dfam accession")
            result = await _request_json(
                "dfam", f"families/{quote(accession, safe='')}", params={"format": "summary"}
            )
            return _envelope("Dfam family detail", {"accession": accession, "result": result})
        except Exception as exc:
            return _error("Dfam", exc)


def register_expression(mcp: FastMCP, _api: Any) -> None:
    @mcp.tool()
    async def cygnusx_expression_studies(
        query: str = "", single_cell: bool = False, limit: int = 20
    ) -> dict[str, Any]:
        """Search cached-format bulk or single-cell Atlas study directory; no expression values."""
        try:
            provider = "sc_atlas" if single_cell else "atlas"
            data = await _atlas_directory(provider)
            studies = (
                data if isinstance(data, list) else data.get("experiments", data.get("entries", []))
            )
            term = query.strip().casefold()
            if term:
                studies = [study for study in studies if term in str(study).casefold()]
            return _envelope(
                "Expression Atlas study directory",
                {
                    "atlas": "single-cell" if single_cell else "bulk",
                    "query": query,
                    "total_matches": len(studies),
                    "returned": min(len(studies), _limit(limit)),
                    "studies": studies[:limit],
                    "note": "This is a study directory, not a gene-expression quantification endpoint.",
                },
            )
        except Exception as exc:
            return _error("Expression Atlas", exc)

    @mcp.tool()
    async def cygnusx_expression_manifest(
        accession: str, single_cell: bool = False
    ) -> dict[str, Any]:
        """Resolve an Atlas study from its structured directory record; no file is assumed present."""
        try:
            accession = _identifier(accession, "experiment accession")
            provider = "sc_atlas" if single_cell else "atlas"
            data = await _atlas_directory(provider)
            studies = (
                data if isinstance(data, list) else data.get("experiments", data.get("entries", []))
            )
            matches = [item for item in studies if accession.casefold() in str(item).casefold()]
            exact = (
                [
                    item
                    for item in matches
                    if accession.casefold() in str(item.get("experimentAccession", "")).casefold()
                ]
                if matches and isinstance(matches[0], dict)
                else matches
            )
            return _envelope(
                "Expression Atlas manifest metadata",
                {
                    "accession": accession,
                    "atlas": "single-cell" if single_cell else "bulk",
                    "matches": exact[:10],
                    "found": bool(exact),
                    "note": "This endpoint returns catalog metadata only; downloadable files require a verified per-study manifest and platform file service.",
                },
            )
        except Exception as exc:
            return _error("Expression Atlas", exc)


def register_pathways(mcp: FastMCP, _api: Any) -> None:
    @mcp.tool()
    async def cygnusx_pathway_get(stable_id: str) -> dict[str, Any]:
        """Get Reactome pathway/reaction knowledge by stable ID (not enrichment analysis)."""
        try:
            stable_id = _identifier(stable_id, "Reactome stable ID")
            version, pathway = (
                await _request_json("reactome", "database/version"),
                await _request_json("reactome", f"query/{quote(stable_id, safe='')}"),
            )
            return _envelope(
                "Reactome pathway knowledge",
                {
                    "stable_id": stable_id,
                    "release": version,
                    "result": pathway,
                    "note": "Knowledge lookup only; it does not infer enrichment or causal direction.",
                },
            )
        except Exception as exc:
            return _error("Reactome", exc)


def register_protein(mcp: FastMCP, _api: Any) -> None:
    @mcp.tool()
    async def cygnusx_protein_resolve(
        query: str, organism_id: int = 9606, reviewed_only: bool = False, limit: int = 10
    ) -> dict[str, Any]:
        """Resolve a UniProt protein accession/name with explicit taxonomy and review filtering."""
        try:
            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", query.strip()) or organism_id <= 0:
                raise ValueError("query and positive organism_id are required")
            fields = "accession,id,protein_name,gene_names,organism_id,length,reviewed"
            result = await _request_json(
                "uniprot",
                "uniprotkb/search",
                params={
                    "query": f"(gene_exact:{query.strip()} OR accession:{query.strip()}) AND (organism_id:{organism_id})"
                    + (" AND (reviewed:true)" if reviewed_only else ""),
                    "fields": fields,
                    "format": "json",
                    "size": _limit(limit),
                },
            )
            return _envelope(
                "UniProt protein candidates",
                {
                    "query": query,
                    "organism_id": organism_id,
                    "reviewed_only": reviewed_only,
                    "result": result,
                },
            )
        except Exception as exc:
            return _error("UniProt", exc)

    @mcp.tool()
    async def cygnusx_protein_features(accession: str, section: str = "all") -> dict[str, Any]:
        """Get UniProt entry identity and bounded feature sections; full JSON is not passed through."""
        try:
            accession = _identifier(accession, "UniProt accession")
            if section not in {"all", "function", "location", "features"}:
                raise ValueError("section must be all, function, location or features")
            entry = await _request_json("uniprot", f"uniprotkb/{quote(accession, safe='')}.json")
            comments = entry.get("comments", [])
            features = entry.get("features", [])
            if section == "function":
                comments = [item for item in comments if item.get("commentType") == "FUNCTION"]
                features = []
            elif section == "location":
                comments = [
                    item for item in comments if item.get("commentType") == "SUBCELLULAR LOCATION"
                ]
                features = []
            elif section == "features":
                comments = []
            return _envelope(
                "UniProt protein features",
                {
                    "primaryAccession": entry.get("primaryAccession"),
                    "entryType": entry.get("entryType"),
                    "entryAudit": entry.get("entryAudit"),
                    "organism": entry.get("organism"),
                    "genes": entry.get("genes"),
                    "sequence": {
                        "length": (entry.get("sequence") or {}).get("length"),
                        "version": (entry.get("sequence") or {}).get("version"),
                    },
                    "section": section,
                    "comments": comments[:100],
                    "features": features[:200],
                    "truncated": len(comments) > 100 or len(features) > 200,
                },
            )
        except Exception as exc:
            return _error("UniProt", exc)

    @mcp.tool()
    async def cygnusx_protein_sequence(accession: str) -> dict[str, Any]:
        """Return a UniProt FASTA sequence only when at most 3000 residues; large export is disabled."""
        try:
            accession = _identifier(accession, "UniProt accession")
            # FASTA is text/plain, so handle it separately from structured JSON responses.
            response = await provider_client(TIMEOUT).get(
                f"{PROVIDERS['uniprot']}/uniprotkb/{quote(accession, safe='')}.fasta"
            )
            response.raise_for_status()
            if len(response.content) > MAX_RESPONSE_BYTES:
                raise ValueError("provider response exceeds 2 MiB")
            text = response.text
            sequence = "".join(text.splitlines()[1:])
            if len(sequence) > 3000:
                return {
                    "success": False,
                    "summary": "Sequence exceeds inline budget; platform file export is not connected.",
                }
            return _envelope(
                "UniProt FASTA sequence",
                {
                    "accession": accession,
                    "fasta": text,
                    "length": len(sequence),
                    "sequence_version": text.splitlines()[0] if text else None,
                },
            )
        except Exception as exc:
            return _error("UniProt", exc)

    @mcp.tool()
    async def cygnusx_domain_get(accession: str, limit: int = 20) -> dict[str, Any]:
        """Get InterPro family/domain hits and their reported protein locations."""
        try:
            accession = _identifier(accession, "UniProt accession")
            result = await _request_json(
                "interpro",
                f"entry/interpro/protein/uniprot/{quote(accession, safe='')}/",
                params={"page_size": _limit(limit)},
            )
            return _envelope(
                "InterPro protein family/domain annotations",
                {
                    "accession": accession,
                    "result": result,
                    "note": "Preserve each metadata.type and fragment; a shared domain is not full-length orthology.",
                },
            )
        except Exception as exc:
            return _error("InterPro", exc)

    @mcp.tool()
    async def cygnusx_domain_proteins(interpro_id: str, limit: int = 20) -> dict[str, Any]:
        """List UniProt proteins associated with an InterPro accession."""
        try:
            interpro_id = _identifier(interpro_id, "InterPro accession")
            result = await _request_json(
                "interpro",
                f"protein/uniprot/entry/interpro/{quote(interpro_id, safe='')}/",
                params={"page_size": _limit(limit)},
            )
            return _envelope(
                "InterPro member proteins", {"interpro_id": interpro_id, "result": result}
            )
        except Exception as exc:
            return _error("InterPro", exc)

    @mcp.tool()
    async def cygnusx_structure_search(uniprot_accession: str, limit: int = 20) -> dict[str, Any]:
        """Find experimental RCSB polymer entities matching an exact UniProt accession."""
        try:
            accession = _identifier(uniprot_accession, "UniProt accession")
            query = {
                "query": {
                    "type": "terminal",
                    "service": "text",
                    "parameters": {
                        "attribute": "rcsb_polymer_entity_container_identifiers.reference_sequence_identifiers.database_accession",
                        "operator": "exact_match",
                        "value": accession,
                        "database_name": "UniProt",
                    },
                },
                "return_type": "polymer_entity",
                "request_options": {
                    "paginate": {"start": 0, "rows": _limit(limit)},
                    "results_content_type": ["experimental"],
                },
            }
            result = await _request_json("rcsb_search", "rcsbsearch/v2/query", json_body=query)
            return _envelope(
                "RCSB experimental structure candidates",
                {
                    "uniprot_accession": accession,
                    "result": result,
                    "note": "Results are polymer entities; deduplicate by entry to count structures.",
                },
            )
        except Exception as exc:
            return _error("RCSB", exc)

    @mcp.tool()
    async def cygnusx_structure_get(entry_id: str) -> dict[str, Any]:
        """Get bounded RCSB entry metadata; ions/cofactors are not identified as drugs."""
        try:
            entry_id = entry_id.strip().upper()
            if not _PDB_ID.fullmatch(entry_id):
                raise ValueError("entry_id must be a four-character PDB identifier")
            result = await _request_json("rcsb", f"rest/v1/core/entry/{entry_id.lower()}")
            return _envelope("RCSB experimental entry", {"entry_id": entry_id, "result": result})
        except Exception as exc:
            return _error("RCSB", exc)

    @mcp.tool()
    async def cygnusx_structure_prediction(
        uniprot_accession: str, isoform: str = ""
    ) -> dict[str, Any]:
        """List AlphaFold model candidates; predicted structures remain distinct from experimental PDB entries."""
        try:
            accession = _identifier(uniprot_accession, "UniProt accession")
            if isoform:
                isoform = _identifier(isoform, "isoform")
                if not isoform.startswith(accession + "-"):
                    raise ValueError("isoform must belong to the supplied UniProt accession")
            models = await _request_json("alphafold", f"prediction/{quote(accession, safe='')}")
            if not isinstance(models, list):
                raise ValueError("AlphaFold response is not a model list")
            if isoform:
                models = [item for item in models if item.get("uniprotAccession") == isoform]
            return _envelope(
                "AlphaFold predicted model candidates",
                {
                    "uniprot_accession": accession,
                    "isoform": isoform or None,
                    "model_type": "predicted",
                    "models": models[:20],
                    "note": "pLDDT is local confidence; it is not experimental resolution or causal evidence.",
                },
            )
        except Exception as exc:
            return _error("AlphaFold DB", exc)


def register_clinical_literature(mcp: FastMCP, _api: Any) -> None:
    @mcp.tool()
    async def cygnusx_clinvar_search(term: str, limit: int = 10, offset: int = 0) -> dict[str, Any]:
        """Search ClinVar with E-utilities; result IDs are Entrez UIDs, not VCV/SCV IDs."""
        try:
            term = term.strip()
            if not term or len(term) > 512 or offset < 0 or offset > 10000:
                raise ValueError("term must be 1-512 characters; offset must be 0-10000")
            result = await _request_json(
                "clinvar",
                "esearch.fcgi",
                params={
                    "db": "clinvar",
                    "term": term,
                    "retmode": "json",
                    "retmax": _limit(limit),
                    "retstart": offset,
                },
            )
            return _envelope(
                "ClinVar search",
                {
                    "term": term,
                    "offset": offset,
                    "id_semantics": "Entrez UID; not VCV/RCV/SCV",
                    "result": result,
                },
            )
        except Exception as exc:
            return _error("ClinVar", exc)

    @mcp.tool()
    async def cygnusx_clinvar_get(vcv_accession: str) -> dict[str, Any]:
        """Fetch a ClinVar VCV XML record by explicit accession; raw XML is not returned."""
        try:
            vcv_accession = _identifier(vcv_accession, "VCV accession")
            if not re.fullmatch(r"VCV[0-9]+(?:\.[0-9]+)?", vcv_accession):
                raise ValueError("vcv_accession must use the VCV accession form")
            root = await _request_xml(
                "clinvar",
                "efetch.fcgi",
                params={
                    "db": "clinvar",
                    "id": vcv_accession,
                    "rettype": "vcv",
                    "retmode": "xml",
                },
            )
            return _envelope(
                "ClinVar VCV summary",
                {
                    "vcv_accession": vcv_accession,
                    "xml_root": root.tag.rsplit("}", 1)[-1],
                    "record_facts": _xml_projection(root),
                    "truncated": sum(1 for _ in root.iter()) > 500,
                    "note": "Summary is evidence, not a clinical recommendation; assertions may conflict.",
                },
            )
        except Exception as exc:
            return _error("ClinVar", exc)

    @mcp.tool()
    async def cygnusx_target_search(
        query: str, entity: str = "target", limit: int = 10
    ) -> dict[str, Any]:
        """Search Open Targets using a fixed GraphQL template; arbitrary GraphQL is not accepted."""
        try:
            if entity not in {"target", "disease", "drug"} or not query.strip() or len(query) > 256:
                raise ValueError(
                    "entity must be target/disease/drug and query must be 1-256 characters"
                )
            gql = "query Search($q: String!, $types: [String!]!, $page: Pagination!) { search(queryString: $q, entityNames: $types, page: $page) { total hits { id name entity } } }"
            result = await _request_json(
                "opentargets",
                json_body={
                    "query": gql,
                    "variables": {
                        "q": query.strip(),
                        "types": [entity],
                        "page": {"index": 0, "size": _limit(limit)},
                    },
                },
            )
            if result.get("errors") and not result.get("data"):
                raise ValueError("Open Targets returned GraphQL errors without data")
            return _envelope(
                "Open Targets entity search",
                {
                    "entity": entity,
                    "query": query,
                    "partial": bool(result.get("errors")),
                    "result": result,
                    "note": "Association scores are evidence aggregates, not causal probabilities.",
                },
            )
        except Exception as exc:
            return _error("Open Targets", exc)

    @mcp.tool()
    async def cygnusx_target_associations(target_id: str, limit: int = 10) -> dict[str, Any]:
        """Get Open Targets target-to-disease associations using a fixed query template."""
        try:
            target_id = _identifier(target_id, "Ensembl target ID")
            if not target_id.startswith("ENSG"):
                raise ValueError("target_id must be a human Ensembl gene ID (ENSG...)")
            gql = "query TargetAssociations($id: String!, $page: Pagination!) { target(ensemblId: $id) { id approvedSymbol associatedDiseases(page: $page) { count rows { disease { id name } score } } } }"
            result = await _request_json(
                "opentargets",
                json_body={
                    "query": gql,
                    "variables": {"id": target_id, "page": {"index": 0, "size": _limit(limit)}},
                },
            )
            if result.get("errors") and not result.get("data"):
                raise ValueError("Open Targets returned GraphQL errors without data")
            return _envelope(
                "Open Targets target associations",
                {
                    "target_id": target_id,
                    "partial": bool(result.get("errors")),
                    "result": result,
                    "note": "Scores are not disease probabilities or proof of causation.",
                },
            )
        except Exception as exc:
            return _error("Open Targets", exc)

    @mcp.tool()
    async def cygnusx_target_evidence(
        target_id: str, disease_id: str, limit: int = 10
    ) -> dict[str, Any]:
        """Retrieve bounded Open Targets evidence for a target/disease pair via a fixed template."""
        try:
            target_id = _identifier(target_id, "Ensembl target ID")
            disease_id = _identifier(disease_id, "disease ID")
            if not target_id.startswith("ENSG"):
                raise ValueError("target_id must be a human Ensembl gene ID (ENSG...)")
            gql = "query TargetEvidence($id: String!, $disease: String!, $size: Int!) { target(ensemblId: $id) { id evidences(efoIds: [$disease], size: $size) { count rows { datasourceId datatypeId score evidence { urls { url niceName } } } } } }"
            result = await _request_json(
                "opentargets",
                json_body={
                    "query": gql,
                    "variables": {"id": target_id, "disease": disease_id, "size": _limit(limit)},
                },
            )
            if result.get("errors") and not result.get("data"):
                raise ValueError("Open Targets returned GraphQL errors without data")
            return _envelope(
                "Open Targets evidence",
                {
                    "target_id": target_id,
                    "disease_id": disease_id,
                    "partial": bool(result.get("errors")),
                    "result": result,
                },
            )
        except Exception as exc:
            return _error("Open Targets", exc)

    @mcp.tool()
    async def cygnusx_literature_get(
        source: str, article_id: str, section: str = "metadata"
    ) -> dict[str, Any]:
        """Get Europe PMC article metadata/references/citations or accessible OA full-text XML."""
        try:
            if source not in {"MED", "PMC", "PPR"}:
                raise ValueError("source must be MED, PMC or PPR")
            article_id = _identifier(article_id, "article ID")
            if section not in {"metadata", "references", "citations", "full_text"}:
                raise ValueError("unsupported literature section")
            suffix = {
                "metadata": "",
                "references": "/references",
                "citations": "/citations",
                "full_text": "/fullTextXML",
            }[section]
            path = (
                f"{quote(article_id, safe='')}{suffix}"
                if section == "full_text" and source == "PMC"
                else (f"{quote(source, safe='')}/{quote(article_id, safe='')}{suffix}")
            )
            if section == "full_text":
                raise ValueError(
                    "OA full-text XML is not exposed until license-aware parsing and byte budgeting are connected"
                )
            result = await _request_json(
                "europepmc", path, params={"format": "json", "pageSize": 20}
            )
            return _envelope(
                "Europe PMC article record",
                {
                    "source": source,
                    "article_id": article_id,
                    "section": section,
                    "result": result,
                },
            )
        except Exception as exc:
            return _error("Europe PMC", exc)

    @mcp.tool()
    async def cygnusx_literature_annotations(article_ids: list[str]) -> dict[str, Any]:
        """Fetch Europe PMC annotations for up to 20 explicit source-qualified article IDs."""
        try:
            if not article_ids or len(article_ids) > 20:
                raise ValueError("article_ids must contain 1 to 20 values")
            if any(
                not re.fullmatch(r"(?:MED|PMC|PPR):[A-Za-z0-9_.-]{1,32}", item)
                for item in article_ids
            ):
                raise ValueError("each article ID must be source-qualified, e.g. MED:29165669")
            result = await _request_json(
                "europepmc_annotations",
                "annotationsByArticleIds",
                params={"articleIds": ",".join(article_ids), "format": "JSON"},
            )
            return _envelope(
                "Europe PMC article annotations",
                {
                    "article_ids": article_ids,
                    "result": result,
                    "note": "Text-mined co-occurrence is not a validated biological relationship.",
                },
            )
        except Exception as exc:
            return _error("Europe PMC", exc)

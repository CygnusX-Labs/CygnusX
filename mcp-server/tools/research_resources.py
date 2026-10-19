"""Fixed, bounded read-only adapters for documented research-data providers.

Large assets and unverified analysis endpoints are intentionally not exposed here.
"""

from __future__ import annotations

import asyncio
import csv
import functools
import inspect
import io
import re
import time
import xml.etree.ElementTree as ET
from typing import Any, Literal
from urllib.parse import quote

import httpx
from fastmcp import FastMCP

from tools.research_common import envelope, provider_client


def _tool(mcp: FastMCP, api: Any):
    """Register a tool; production calls use the authenticated platform bridge."""

    def decorator(fn: Any) -> Any:
        if api is None:
            return mcp.tool()(fn)

        @functools.wraps(fn)
        async def bridged(*args: Any, **kwargs: Any) -> dict[str, Any]:
            bound = inspect.signature(fn).bind(*args, **kwargs)
            arguments = {key: value for key, value in bound.arguments.items() if value is not None}
            return await api.research_data(fn.__name__, arguments)

        return mcp.tool()(bridged)

    return decorator


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
    "string": "https://version-12-5.string-db.org/api/tsv",
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
_STRING_RATE_LOCK = asyncio.Lock()
_STRING_LAST_REQUEST = 0.0


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


async def _request_text(provider: str, path: str, *, accept: str = "text/plain") -> str:
    if provider not in PROVIDERS:
        raise ValueError("unknown provider")
    if path.startswith("/") or ".." in path.split("/"):
        raise ValueError("provider path must be relative and fixed by the adapter")
    request = provider_client(TIMEOUT).build_request(
        "GET", f"{PROVIDERS[provider]}/{path}"
    )
    request.headers["accept"] = accept
    response = await provider_client(TIMEOUT).send(request)
    response.raise_for_status()
    if len(response.content) > 4096:
        raise ValueError("provider text response exceeds 4096 bytes")
    content_type = response.headers.get("content-type", "").lower()
    if "html" in content_type or "text/plain" not in content_type:
        raise ValueError("provider returned a non-text response")
    return response.text.strip()


async def _request_string_tsv(method: str, params: dict[str, Any]) -> list[dict[str, str]]:
    global _STRING_LAST_REQUEST
    if method not in {"get_string_ids", "interaction_partners"}:
        raise ValueError("unsupported fixed STRING method")
    async with _STRING_RATE_LOCK:
        remaining = 1.0 - (time.monotonic() - _STRING_LAST_REQUEST)
        if remaining > 0:
            await asyncio.sleep(remaining)
        client = provider_client(TIMEOUT)
        request = client.build_request(
            "GET",
            f"{PROVIDERS['string']}/{method}",
            params=params,
            headers={"accept": "text/tab-separated-values"},
        )
        _STRING_LAST_REQUEST = time.monotonic()
        response = await client.send(request, stream=True)
    try:
        response.raise_for_status()
        body = bytearray()
        async for chunk in response.aiter_bytes():
            if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                raise ValueError("STRING response exceeds 2 MiB")
            body.extend(chunk)
        content_type = response.headers.get("content-type", "").lower()
        if "html" in content_type or "tab-separated-values" not in content_type:
            raise ValueError("STRING returned a non-TSV response")
        text = bytes(body).decode(response.encoding or "utf-8")
        return list(csv.DictReader(io.StringIO(text), delimiter="\t"))
    finally:
        await response.aclose()


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
    if re.search(rb"<!\s*(?:DOCTYPE|ENTITY)\b", response.content, re.IGNORECASE):
        raise ValueError("provider XML DTD and entity declarations are not accepted")
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
    @_tool(mcp, _api)
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

    @_tool(mcp, _api)
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

    @_tool(mcp, _api)
    async def cygnusx_genome_region(
        species: str, region: str, feature: str = "gene"
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

    @_tool(mcp, _api)
    async def cygnusx_genome_sequence(
        identifier: str, sequence_type: str = "cdna"
    ) -> dict[str, Any]:
        """按 Ensembl stable ID 读取 genomic、cdna、cds 或 protein 序列（默认 cdna）；返回序列长度和最多 3000 字符的预览及截断标记，不提供完整序列文件下载。"""
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
    @_tool(mcp, _api)
    async def cygnusx_plant_search(query: str, limit: int = 10) -> dict[str, Any]:
        """Search Gramene v69 gene/plant knowledge index with bounded paging."""
        try:
            query = query.strip()
            if not query or len(query) > 2048:
                raise ValueError("query must be 1-2048 characters")
            if any(char in query for char in ":()[]{}^~*?"):
                raise ValueError("plant search accepts literal terms, not raw Solr expressions")
            query = f'"{query.replace(chr(34), chr(92) + chr(34))}"'
            result = await _request_json(
                "gramene",
                "search",
                params={"q": query, "rows": _limit(limit), "wt": "json"},
            )
            return _envelope(
                "Gramene v69 search",
                {
                    "release": "v69",
                    "query": query,
                    "result": result,
                    "taxonomy_note": "Gramene taxon_id is provider-specific; do not treat as NCBI taxid.",
                },
            )
        except Exception as exc:
            return _error("Gramene", exc)

    @_tool(mcp, _api)
    async def cygnusx_plant_get(identifier: str) -> dict[str, Any]:
        """按 Gramene gene identifier 查询 Gramene v69 基因详情并保留原始 provider 记录；结果中的 taxon_id 是 Gramene 专用标识，不能直接当作 NCBI taxid。"""
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

    @_tool(mcp, _api)
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

    @_tool(mcp, _api)
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
    @_tool(mcp, _api)
    async def cygnusx_expression_studies(
        query: str = "", single_cell: bool = False, limit: int = 20
    ) -> dict[str, Any]:
        """在缓存的 Expression Atlas bulk 或单细胞研究目录中按 query 做不区分大小写的字面子串筛选；single_cell 选择目录，limit 限制返回条数。结果是研究元数据，不含基因表达定量值。"""
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

    @_tool(mcp, _api)
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
    @_tool(mcp, _api)
    async def cygnusx_pathway_get(pathway_id: str) -> dict[str, Any]:
        """Get Reactome pathway/reaction knowledge by stable ID (not enrichment analysis)."""
        try:
            pathway_id = _identifier(pathway_id, "Reactome stable ID")
            version, pathway = await _request_text(
                "reactome", "database/version"
            ), await _request_json("reactome", f"query/{quote(pathway_id, safe='')}")
            return _envelope(
                "Reactome pathway knowledge",
                {
                    "pathway_id": pathway_id,
                    "release": version,
                    "result": pathway,
                    "note": "Knowledge lookup only; it does not infer enrichment or causal direction.",
                },
            )
        except Exception as exc:
            return _error("Reactome", exc)


def register_protein(mcp: FastMCP, _api: Any) -> None:
    @_tool(mcp, _api)
    async def cygnusx_protein_resolve(query: str, organism_id: int | None = None) -> dict[str, Any]:
        """Resolve a UniProt protein accession/name with explicit taxonomy and review filtering."""
        try:
            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", query.strip()) or (
                organism_id is not None and organism_id <= 0
            ):
                raise ValueError("query and optional positive organism_id are required")
            fields = "accession,id,protein_name,gene_names,organism_id,length,reviewed"
            provider_query = f"(gene_exact:{query.strip()} OR accession:{query.strip()})"
            if organism_id is not None:
                provider_query += f" AND (organism_id:{organism_id})"
            result = await _request_json(
                "uniprot",
                "uniprotkb/search",
                params={
                    "query": provider_query,
                    "fields": fields,
                    "format": "json",
                    "size": 10,
                },
            )
            return _envelope(
                "UniProt protein candidates",
                {
                    "query": query,
                    "organism_id": organism_id,
                    "result": result,
                },
            )
        except Exception as exc:
            return _error("UniProt", exc)

    @_tool(mcp, _api)
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

    @_tool(mcp, _api)
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

    @_tool(mcp, _api)
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

    @_tool(mcp, _api)
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

    @_tool(mcp, _api)
    async def cygnusx_structure_search(accession: str) -> dict[str, Any]:
        """Find experimental RCSB polymer entities matching an exact UniProt accession."""
        try:
            accession = _identifier(accession, "UniProt accession")
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
                    "paginate": {"start": 0, "rows": 10},
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

    @_tool(mcp, _api)
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

    @_tool(mcp, _api)
    async def cygnusx_structure_prediction(accession: str) -> dict[str, Any]:
        """List AlphaFold model candidates; predicted structures remain distinct from experimental PDB entries."""
        try:
            accession = _identifier(accession, "UniProt accession")
            models = await _request_json("alphafold", f"prediction/{quote(accession, safe='')}")
            if not isinstance(models, list):
                raise ValueError("AlphaFold response is not a model list")
            return _envelope(
                "AlphaFold predicted model candidates",
                {
                    "uniprot_accession": accession,
                    "model_type": "predicted",
                    "models": models[:20],
                    "note": "pLDDT is local confidence; it is not experimental resolution or causal evidence.",
                },
            )
        except Exception as exc:
            return _error("AlphaFold DB", exc)


def register_clinical_literature(mcp: FastMCP, _api: Any) -> None:
    @_tool(mcp, _api)
    async def cygnusx_clinvar_search(query: str) -> dict[str, Any]:
        """Search ClinVar with E-utilities; result IDs are Entrez UIDs, not VCV/SCV IDs."""
        try:
            query = query.strip()
            if not query or len(query) > 1024:
                raise ValueError("query must be 1-1024 characters")
            result = await _request_json(
                "clinvar",
                "esearch.fcgi",
                params={
                    "db": "clinvar",
                    "term": query,
                    "retmode": "json",
                    "retmax": 20,
                },
            )
            return _envelope(
                "ClinVar search",
                {
                    "term": query,
                    "id_semantics": "Entrez UID; not VCV/RCV/SCV",
                    "result": result,
                },
            )
        except Exception as exc:
            return _error("ClinVar", exc)

    @_tool(mcp, _api)
    async def cygnusx_clinvar_get(
        vcv_accession: str | None = None,
        identifier: str | None = None,
        identifier_type: Literal["VCV", "RCV", "SCV", "VariationID", "AlleleID"] | None = None,
    ) -> dict[str, Any]:
        """Fetch ClinVar evidence by VCV, RCV, SCV, or Variation ID; Allele ID is unsupported."""
        try:
            if vcv_accession is not None:
                if identifier is not None or identifier_type is not None:
                    raise ValueError("use vcv_accession or identifier with identifier_type, not both")
                identifier, identifier_type = vcv_accession, "VCV"
            elif identifier is None or identifier_type is None:
                raise ValueError("provide vcv_accession or identifier with identifier_type")
            identifier = _identifier(identifier, f"{identifier_type} identifier")
            if identifier_type == "AlleleID":
                raise ValueError("Allele ID is unsupported; it is not interchangeable with Variation ID")
            patterns = {
                "VCV": r"VCV[0-9]+(?:\.[0-9]+)?",
                "RCV": r"RCV[0-9]+(?:\.[0-9]+)?",
                "SCV": r"SCV[0-9]+(?:\.[0-9]+)?",
                "VariationID": r"[0-9]+",
            }
            if identifier_type not in patterns or not re.fullmatch(patterns[identifier_type], identifier):
                raise ValueError("identifier does not match the selected ClinVar identifier type")
            requested_id, separator, requested_version = identifier.partition(".")
            if identifier_type == "SCV":
                search = await _request_json(
                    "clinvar",
                    "esearch.fcgi",
                    {
                        "db": "clinvar",
                        "term": f"{requested_id}[clv_acc]",
                        "retmode": "json",
                        "retmax": 1,
                    },
                )
                id_list = search.get("esearchresult", {}).get("idlist", [])
                uid = id_list[0] if id_list else None
                if not uid or not uid.isdigit():
                    raise ValueError("ClinVar did not resolve the requested SCV accession")
                root = await _request_xml(
                    "clinvar",
                    "efetch.fcgi",
                    {
                        "db": "clinvar",
                        "id": uid,
                        "rettype": "vcv",
                        "retmode": "xml",
                        "is_variationid": "true",
                        "from_esearch": "true",
                    },
                )
            else:
                rettype = "clinvarset" if identifier_type == "RCV" else "vcv"
                params = {"db": "clinvar", "id": identifier, "rettype": rettype, "retmode": "xml"}
                if identifier_type == "VariationID":
                    params.update({"is_variationid": "true", "from_esearch": "true"})
                root = await _request_xml("clinvar", "efetch.fcgi", params)
            archive = next((node for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "VariationArchive"), None)
            clinvar_set = next((node for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "ClinVarSet"), None)
            record_element = archive if archive is not None else clinvar_set
            accessions = [node for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "ClinVarAccession"]
            target_type = "RCV" if identifier_type == "RCV" else "SCV"
            accession_node = next(
                (
                    node
                    for node in accessions
                    if node.attrib.get("Type") == target_type
                    and (
                        identifier_type != "SCV"
                        or (node.attrib.get("Accession") or node.attrib.get("Acc")) == requested_id
                    )
                ),
                None,
            )
            returned_accession = (
                archive.attrib.get("Accession")
                if identifier_type == "VCV" and archive is not None
                else accession_node.attrib.get("Acc") if accession_node is not None else None
            )
            returned_version = (
                archive.attrib.get("Version")
                if identifier_type == "VCV" and archive is not None
                else accession_node.attrib.get("Version") if accession_node is not None else None
            )
            if identifier_type in {"VCV", "RCV"} and returned_accession != requested_id:
                raise ValueError(f"ClinVar returned a different {identifier_type} accession")
            if (identifier_type == "VCV" and archive is None) or (
                identifier_type == "RCV" and clinvar_set is None
            ):
                raise ValueError(f"ClinVar returned a non-{identifier_type} record")
            if separator and returned_version != requested_version:
                raise ValueError(f"ClinVar returned a different {identifier_type} version")
            if identifier_type == "VariationID" and (archive is None or archive.attrib.get("VariationID") != requested_id):
                raise ValueError("ClinVar returned a different Variation ID")
            if identifier_type == "SCV":
                scv = next((node for node in accessions if node.attrib.get("Type") == "SCV" and
                            (node.attrib.get("Accession") or node.attrib.get("Acc")) == requested_id), None)
                if scv is None or separator and scv.attrib.get("Version") != requested_version:
                    raise ValueError("ClinVar response does not match the requested SCV accession/version")
            if record_element is None:
                raise ValueError("ClinVar returned no VCV or RCV record")
            return _envelope(
                f"ClinVar {identifier_type} summary",
                {
                    "requested_identifier": identifier,
                    "identifier_type": identifier_type,
                    "xml_root": root.tag.rsplit("}", 1)[-1],
                    "record_facts": _xml_projection(root),
                    "truncated": sum(1 for _ in root.iter()) > 500,
                    "note": "Summary is evidence, not a clinical recommendation; assertions may conflict.",
                },
            )
        except Exception as exc:
            return _error("ClinVar", exc)

    @_tool(mcp, _api)
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

    @_tool(mcp, _api)
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

    @_tool(mcp, _api)
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

    @_tool(mcp, _api)
    async def cygnusx_literature_get(article_id: str, source: str = "MED") -> dict[str, Any]:
        """Get Europe PMC article metadata/references/citations or accessible OA full-text XML."""
        try:
            if source not in {"MED", "PMC"}:
                raise ValueError("source must be MED or PMC")
            article_id = _identifier(article_id, "article ID")
            path = f"article/{quote(source, safe='')}/{quote(article_id, safe='')}"
            result = await _request_json(
                "europepmc", path, params={"format": "json", "resultType": "core"}
            )
            return _envelope(
                "Europe PMC article record",
                {
                    "source": source,
                    "article_id": article_id,
                    "result": result,
                },
            )
        except Exception as exc:
            return _error("Europe PMC", exc)

    register_literature_annotations(mcp, _api)


def register_string(mcp: FastMCP, _api: Any) -> None:
    @_tool(mcp, _api)
    async def cygnusx_string_resolve(
        identifier: str, taxon_id: int, limit: int = 10
    ) -> dict[str, Any]:
        """Resolve one identifier against a required NCBI taxon and preserve all bounded candidates."""
        try:
            identifier = identifier.strip()
            if not identifier or len(identifier) > 128 or not 1 <= taxon_id <= 1_000_000:
                raise ValueError("identifier and a valid NCBI taxon_id are required")
            if not 1 <= limit <= 20:
                raise ValueError("limit must be between 1 and 20")
            rows = await _request_string_tsv(
                "get_string_ids",
                {
                    "identifiers": identifier,
                    "species": taxon_id,
                    "limit": limit,
                    "caller_identity": "CygnusX",
                },
            )
            candidates = [
                {
                    "string_id": row.get("stringId", ""),
                    "taxon_id": row.get("ncbiTaxonId", ""),
                    "taxon_name": row.get("taxonName", ""),
                    "preferred_name": row.get("preferredName", ""),
                    "annotation": row.get("annotation", "")[:512],
                }
                for row in rows[:limit]
                if row.get("stringId") and row.get("ncbiTaxonId") == str(taxon_id)
            ]
            return _envelope(
                "STRING identifier candidates",
                {
                    "input_identifier": identifier,
                    "taxon_id": taxon_id,
                    "found": bool(candidates),
                    "candidate_count": len(candidates),
                    "candidates": candidates,
                    "selection_note": "Ambiguous candidates are preserved; choose an explicit STRING ID before querying partners.",
                    "release": "12.5",
                },
            )
        except Exception as exc:
            return _error("STRING", exc)

    @_tool(mcp, _api)
    async def cygnusx_string_network(
        string_id: str,
        taxon_id: int,
        network_type: Literal["functional", "physical", "regulatory"],
        required_score: int = 400,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Get bounded STRING partners for an explicit taxon-matched ID and network type; scores are not causal probabilities."""
        try:
            string_id = string_id.strip()
            if (
                not re.fullmatch(r"[0-9]+\.[A-Za-z0-9_.-]{1,64}", string_id)
                or string_id.partition(".")[0] != str(taxon_id)
                or not 1 <= taxon_id <= 1_000_000
            ):
                raise ValueError("string_id must match the explicit taxon_id")
            if network_type not in {"functional", "physical", "regulatory"}:
                raise ValueError("network_type must be functional, physical, or regulatory")
            if not 0 <= required_score <= 1000 or not 1 <= limit <= 50:
                raise ValueError("required_score must be 0-1000 and limit must be 1-50")
            rows = await _request_string_tsv(
                "interaction_partners",
                {
                    "identifiers": string_id,
                    "species": taxon_id,
                    "network_type": network_type,
                    "required_score": required_score,
                    "limit": limit,
                    "add_color_nodes": 0,
                    "add_white_nodes": 0,
                    "caller_identity": "CygnusX",
                },
            )
            partners = []
            for row in rows[:limit]:
                item: dict[str, Any] = dict(row)
                if network_type == "regulatory":
                    source_id = row.get("source_string_id")
                    target_id = row.get("target_string_id")
                    item["partner_string_id"] = (
                        target_id if source_id == string_id else source_id if target_id == string_id else None
                    )
                    item["partner_preferred_name"] = (
                        row.get("target_preferred_name")
                        if source_id == string_id
                        else row.get("source_preferred_name") if target_id == string_id else None
                    )
                else:
                    a_id = row.get("stringId_A")
                    b_id = row.get("stringId_B")
                    item["partner_string_id"] = (
                        b_id if a_id == string_id else a_id if b_id == string_id else None
                    )
                    item["partner_preferred_name"] = (
                        row.get("preferredName_B")
                        if a_id == string_id
                        else row.get("preferredName_A") if b_id == string_id else None
                    )
                if not item["partner_string_id"]:
                    raise ValueError("STRING returned a network row unrelated to the requested ID")
                for key, value in row.items():
                    if key.endswith("score"):
                        try:
                            item[key] = float(value)
                        except (TypeError, ValueError):
                            item[key] = value
                partners.append(item)
            return _envelope(
                f"STRING {network_type} protein partners",
                {
                    "string_id": string_id,
                    "taxon_id": taxon_id,
                    "network_type": network_type,
                    "required_score": required_score,
                    "returned": len(partners),
                    "has_more": len(rows) > len(partners),
                    "partners": partners,
                    "interpretation": (
                        "Regulatory rows are directional source-to-target relationships; signs may be unavailable."
                        if network_type == "regulatory"
                        else "Scores are STRING association confidence/evidence scores, not causal probabilities."
                    ),
                    "release": "12.5",
                },
            )
        except Exception as exc:
            return _error("STRING", exc)



def register_literature_annotations(mcp: FastMCP, _api: Any) -> None:
    @_tool(mcp, _api)
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

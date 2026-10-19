"""Bounded read-only adapters shared by the internal research-data MCP preset."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Awaitable
from typing import Any, cast
from urllib.parse import quote
from weakref import WeakKeyDictionary

import httpx
from redis.exceptions import RedisError

from cygnusx.infrastructure.cache.redis_client import get_redis

_HOSTS = {
    "ensembl": "https://rest.ensembl.org",
    "gramene": "https://data.gramene.org/v69",
    "dfam": "https://dfam.org/api",
    "atlas": "https://www.ebi.ac.uk/gxa/json",
    "sc_atlas": "https://www.ebi.ac.uk/gxa/sc/json",
    "uniprot": "https://rest.uniprot.org",
    "interpro": "https://www.ebi.ac.uk/interpro/api",
    "rcsb_search": "https://search.rcsb.org",
    "rcsb": "https://data.rcsb.org",
    "alphafold": "https://alphafold.ebi.ac.uk/api",
    "reactome": "https://reactome.org/ContentService/data",
    "clinvar": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
    "opentargets": "https://api.platform.opentargets.org/api/v4/graphql",
    "europepmc": "https://www.ebi.ac.uk/europepmc/webservices/rest",
    "string": "https://version-12-5.string-db.org/api/tsv",
}
_CLIENTS: WeakKeyDictionary[asyncio.AbstractEventLoop, httpx.AsyncClient] = WeakKeyDictionary()
_ATLAS_CACHE: WeakKeyDictionary[asyncio.AbstractEventLoop, dict[str, tuple[float, Any]]] = (
    WeakKeyDictionary()
)
_ATLAS_LOCKS: WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = WeakKeyDictionary()
_MAX_RESPONSE = 2 * 1024 * 1024
_MAX_ATLAS_DIRECTORY = 10 * 1024 * 1024
_ATLAS_CACHE_TTL = 6 * 60 * 60
_MAX_OUTPUT = 3000
_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_STRING_ID = re.compile(r"^[0-9]+\.[A-Za-z0-9_.-]{1,64}$")
_STRING_RATE_LIMIT_LUA = """
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - 1000)
local first = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
if #first == 0 then
  redis.call('ZADD', KEYS[1], now, ARGV[1])
  redis.call('PEXPIRE', KEYS[1], 5000)
  return 0
end
return math.max(0, 1000 - (now - tonumber(first[2])))
"""


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
    max_response_bytes: int = _MAX_RESPONSE,
    request_timeout: httpx.Timeout | None = None,
) -> Any:
    if provider not in _HOSTS or path.startswith("/") or ".." in path.split("/"):
        raise ValueError("invalid fixed provider path")
    request_options: dict[str, Any] = {"params": params, "json": payload}
    if request_timeout is not None:
        request_options["timeout"] = request_timeout
    client = _client()
    request = client.build_request(
        "POST" if payload is not None else "GET",
        f"{_HOSTS[provider]}/{path}" if path else _HOSTS[provider],
        **request_options,
    )
    response = await client.send(request, stream=True)
    try:
        response.raise_for_status()
        body = bytearray()
        async for chunk in response.aiter_bytes():
            if len(body) + len(chunk) > max_response_bytes:
                raise ValueError(f"provider response exceeds {max_response_bytes} bytes")
            body.extend(chunk)
        if "json" not in response.headers.get("content-type", "").lower():
            raise ValueError("provider returned a non-JSON response")
        return json.loads(body)
    finally:
        await response.aclose()


async def _atlas_directory(provider: str) -> Any:
    if provider not in {"atlas", "sc_atlas"}:
        raise ValueError("unknown Atlas directory")
    loop = asyncio.get_running_loop()
    cache = _ATLAS_CACHE.setdefault(loop, {})
    now = time.monotonic()
    cached = cache.get(provider)
    if cached and cached[0] > now:
        return cached[1]
    lock = _ATLAS_LOCKS.setdefault(loop, asyncio.Lock())
    async with lock:
        now = time.monotonic()
        cached = cache.get(provider)
        if cached and cached[0] > now:
            return cached[1]
        async with asyncio.timeout(25):
            data = await _request(
                provider,
                "experiments",
                max_response_bytes=_MAX_ATLAS_DIRECTORY,
                request_timeout=httpx.Timeout(25.0, connect=3.0, read=20.0),
            )
        cache[provider] = (time.monotonic() + _ATLAS_CACHE_TTL, data)
        return data


def _atlas_experiments(data: Any) -> list[Any]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("experiments", "entries"):
            experiments = data.get(key)
            if isinstance(experiments, list):
                return experiments
    raise ValueError("Atlas returned an unexpected experiment directory shape")


async def _request_text(
    provider: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    accept: str = "text/plain, text/x-fasta;q=0.9",
) -> str:
    if provider not in _HOSTS or path.startswith("/") or ".." in path.split("/"):
        raise ValueError("invalid fixed provider path")
    client = _client()
    request = client.build_request("GET", f"{_HOSTS[provider]}/{path}", params=params)
    request.headers["accept"] = accept
    response = await client.send(request, stream=True)
    try:
        response.raise_for_status()
        body = bytearray()
        async for chunk in response.aiter_bytes():
            if len(body) + len(chunk) > _MAX_RESPONSE:
                raise ValueError("provider response exceeds 2 MiB")
            body.extend(chunk)
        content_type = response.headers.get("content-type", "").lower()
        if "html" in content_type:
            raise ValueError("provider returned a non-FASTA response")
        if "fasta" in accept and not any(
            accepted in content_type
            for accepted in ("text/plain", "text/x-fasta", "chemical/seq-aa-fasta")
        ):
            raise ValueError("provider returned a non-FASTA response")
        if "fasta" not in accept and "text/plain" not in content_type:
            raise ValueError("provider returned a non-text response")
        return bytes(body).decode(response.encoding or "utf-8")
    finally:
        await response.aclose()


async def _string_rate_limit() -> None:
    redis = get_redis()
    while True:
        eval_result = cast(
            Awaitable[Any],
            redis.eval(
                _STRING_RATE_LIMIT_LUA, 1, "provider-rate:string:v12-5", str(time.time_ns())
            ),
        )
        wait_ms = await eval_result
        if int(wait_ms) <= 0:
            return
        await asyncio.sleep(int(wait_ms) / 1000)


async def _request_string_tsv(method: str, params: dict[str, Any]) -> list[dict[str, str]]:
    if method not in {"get_string_ids", "interaction_partners"}:
        raise ValueError("unsupported fixed STRING method")
    await _string_rate_limit()
    client = _client()
    request = client.build_request("GET", f"{_HOSTS['string']}/{method}", params=params)
    request.headers["accept"] = "text/tab-separated-values"
    response = await client.send(request, stream=True)
    try:
        response.raise_for_status()
        body = bytearray()
        async for chunk in response.aiter_bytes():
            if len(body) + len(chunk) > _MAX_RESPONSE:
                raise ValueError("STRING response exceeds 2 MiB")
            body.extend(chunk)
        content_type = response.headers.get("content-type", "").lower()
        if "html" in content_type or "tab-separated-values" not in content_type:
            raise ValueError("STRING returned a non-TSV response")
        text = bytes(body).decode(response.encoding or "utf-8")
        return list(csv.DictReader(io.StringIO(text), delimiter="\t"))
    finally:
        await response.aclose()


async def _request_xml(provider: str, path: str, *, params: dict[str, Any]) -> ET.Element:
    if provider not in _HOSTS or path.startswith("/") or ".." in path.split("/"):
        raise ValueError("invalid fixed provider path")
    client = _client()
    request = client.build_request("GET", f"{_HOSTS[provider]}/{path}", params=params)
    request.headers["accept"] = "application/xml, text/xml;q=0.9"
    response = await client.send(request, stream=True)
    try:
        response.raise_for_status()
        body = bytearray()
        async for chunk in response.aiter_bytes():
            if len(body) + len(chunk) > _MAX_RESPONSE:
                raise ValueError("provider XML response exceeds 2 MiB")
            body.extend(chunk)
        if "xml" not in response.headers.get("content-type", "").lower():
            raise ValueError("provider returned a non-XML response")
        if re.search(rb"<!\s*(?:DOCTYPE|ENTITY)\b", body, re.IGNORECASE):
            raise ValueError("provider XML DTD and entity declarations are not accepted")
        return ET.fromstring(body)
    finally:
        await response.aclose()


def _clinvar_projection(root: ET.Element) -> dict[str, Any]:
    categories: dict[str, list[dict[str, Any]]] = {
        "germline": [],
        "somatic_clinical_impact": [],
        "oncogenicity": [],
    }
    review_statuses: list[dict[str, Any]] = []
    submitters: list[dict[str, Any]] = []
    classification_counts = dict.fromkeys(categories, 0)
    category_tags = {
        "GermlineClassification": "germline",
        "SomaticClinicalImpact": "somatic_clinical_impact",
        "OncogenicityClassification": "oncogenicity",
    }
    archive = next(
        (
            element
            for element in root.iter()
            if element.tag.rsplit("}", 1)[-1] == "VariationArchive"
        ),
        None,
    )
    clinvar_set = next(
        (element for element in root.iter() if element.tag.rsplit("}", 1)[-1] == "ClinVarSet"),
        None,
    )
    if archive is None and clinvar_set is None:
        raise ValueError("ClinVar returned XML without a VCV or RCV record")
    record_element = archive if archive is not None else clinvar_set
    assert record_element is not None
    clinvar_accessions = [
        element
        for element in record_element.iter()
        if element.tag.rsplit("}", 1)[-1] == "ClinVarAccession"
    ]
    rcv_accession = next(
        (element for element in clinvar_accessions if element.attrib.get("Type") == "RCV"), None
    )
    record_accession = (
        archive.attrib.get("Accession")
        if archive is not None
        else rcv_accession.attrib.get("Acc") if rcv_accession is not None else None
    )
    record_version = (
        archive.attrib.get("Version")
        if archive is not None
        else rcv_accession.attrib.get("Version") if rcv_accession is not None else None
    )
    scv_records = [
        {
            "accession": element.attrib.get("Accession") or element.attrib.get("Acc"),
            "version": element.attrib.get("Version"),
        }
        for element in clinvar_accessions
        if element.attrib.get("Type") == "SCV"
    ][:20]
    for element in root.iter():
        name = element.tag.rsplit("}", 1)[-1]
        text = (element.text or "").strip()
        fact = {
            "attributes": {key: str(value)[:64] for key, value in element.attrib.items()},
            "text": text[:96] or None,
        }
        category = category_tags.get(name)
        if category:
            classification_counts[category] += 1
            nested_facts = [
                {
                    "element": child.tag.rsplit("}", 1)[-1],
                    "attributes": {key: str(value)[:64] for key, value in child.attrib.items()},
                    "text": (child.text or "").strip()[:96] or None,
                }
                for child in element.iter()
                if child is not element and ((child.text or "").strip() or child.attrib)
            ][:2]
            if len(categories[category]) < 2:
                categories[category].append({**fact, "evidence": nested_facts})
        elif name in {"ReviewStatus", "ReviewStatusDescription"}:
            if len(review_statuses) < 2:
                review_statuses.append(fact)
        elif name in {"ClinVarSubmissionID", "SubmitterName", "SubmitterID"} and (
            text or element.attrib
        ):
            if len(submitters) < 2:
                submitters.append({"element": name, **fact})

    truncated = {
        "classifications": any(count > len(categories[name]) for name, count in classification_counts.items()),
        "review_statuses": sum(
            1
            for element in root.iter()
            if element.tag.rsplit("}", 1)[-1] in {"ReviewStatus", "ReviewStatusDescription"}
        )
        > len(review_statuses),
        "submitter_evidence": sum(
            1
            for element in root.iter()
            if element.tag.rsplit("}", 1)[-1]
            in {"ClinVarSubmissionID", "SubmitterName", "SubmitterID"}
            and ((element.text or "").strip() or element.attrib)
        )
        > len(submitters),
    }

    return {
        "record": {
            "record_type": "VCV" if archive is not None else "RCV",
            "accession": record_accession,
            "version": record_version,
            "variation_id": archive.attrib.get("VariationID") if archive is not None else None,
            "submission_count": record_element.attrib.get("NumberOfSubmissions"),
            "submitter_count": record_element.attrib.get("NumberOfSubmitters"),
            "scv_accessions": scv_records,
        },
        "classifications": categories,
        "classification_counts": classification_counts,
        "review_statuses": review_statuses[:20],
        "submitter_evidence": submitters[:20],
        "truncated": any(truncated.values()),
        "truncated_sections": [name for name, value in truncated.items() if value],
    }


def _ok(summary: str, provider: str, data: Any) -> dict[str, Any]:
    return _bounded(
        {"success": True, "summary": summary, "data": {"provider": provider, "result": data}}
    )


async def execute_research(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        if tool_name == "cygnusx_string_resolve":
            identifier = str(arguments.get("identifier", "")).strip()
            taxon_id = int(arguments.get("taxon_id", 0))
            limit = int(arguments.get("limit", 10))
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
            return _ok(
                "STRING identifier candidates",
                "string",
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

        if tool_name == "cygnusx_string_network":
            string_id = str(arguments.get("string_id", "")).strip()
            taxon_id = int(arguments.get("taxon_id", 0))
            network_type = str(arguments.get("network_type", ""))
            required_score = int(arguments.get("required_score", 400))
            limit = int(arguments.get("limit", 20))
            if (
                not _STRING_ID.fullmatch(string_id)
                or string_id.partition(".")[0] != str(taxon_id)
                or not 1 <= taxon_id <= 1_000_000
            ):
                raise ValueError("string_id must be a STRING identifier matching the explicit taxon_id")
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
            directional = network_type == "regulatory"
            return _ok(
                f"STRING {network_type} protein partners",
                "string",
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
                        if directional
                        else "Scores are STRING association confidence/evidence scores, not causal probabilities."
                    ),
                    "release": "12.5",
                },
            )

        if tool_name == "cygnusx_genome_lookup":
            species = str(arguments.get("species", "")).strip()
            identifier = str(arguments.get("identifier", "")).strip()
            if not _ID.fullmatch(species) or not _ID.fullmatch(identifier):
                raise ValueError("species and identifier are required and bounded")
            result = await _request("ensembl", f"lookup/id/{quote(identifier, safe='')}")
            returned_species = result.get("species") if isinstance(result, dict) else None
            if returned_species and returned_species.casefold() != species.casefold():
                raise ValueError(
                    f"requested species {species!r} does not match provider species {returned_species!r}"
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
            result = await _request(
                "ensembl",
                f"homology/id/{quote(species, safe='')}/{quote(identifier, safe='')}",
                params=params,
            )
            return _ok("Ensembl plant homology", "ensembl", {"species": species, "result": result})

        if tool_name == "cygnusx_genome_region":
            species = str(arguments.get("species", "")).strip()
            region = str(arguments.get("region", "")).strip()
            feature = str(arguments.get("feature", "gene"))
            if not _ID.fullmatch(species) or not re.fullmatch(
                r"[A-Za-z0-9_.-]+:[0-9]+\.\.[0-9]+(?::[-+1])?", region
            ):
                raise ValueError("species and region are invalid")
            if feature not in {"gene", "transcript", "cds", "exon", "variation"}:
                raise ValueError("unsupported region feature")
            result = await _request(
                "ensembl",
                f"overlap/region/{quote(species, safe='')}/{quote(region, safe=':')}",
                params={"feature": feature},
            )
            return _ok(
                "Ensembl region overlap",
                "ensembl",
                {"species": species, "region": region, "feature": feature, "result": result},
            )

        if tool_name == "cygnusx_genome_sequence":
            identifier = str(arguments.get("identifier", "")).strip()
            sequence_type = str(arguments.get("sequence_type", "cdna"))
            if not _ID.fullmatch(identifier) or sequence_type not in {
                "genomic",
                "cdna",
                "cds",
                "protein",
            }:
                raise ValueError("identifier or sequence_type is invalid")
            result = await _request(
                "ensembl",
                f"sequence/id/{quote(identifier, safe='')}",
                params={"type": sequence_type},
            )
            sequence = str(result.get("seq", "")) if isinstance(result, dict) else ""
            return _ok(
                "Ensembl sequence",
                "ensembl",
                {
                    "id": identifier,
                    "type": sequence_type,
                    "length": len(sequence),
                    "sequence_preview": sequence[:3000],
                    "truncated": len(sequence) > 3000,
                },
            )

        if tool_name == "cygnusx_plant_search":
            query = str(arguments.get("query", "")).strip()
            limit = int(arguments.get("limit", 10))
            if not query or len(query) > 2048 or not 1 <= limit <= 50:
                raise ValueError("query must be 1-2048 characters and limit 1-50")
            if any(char in query for char in ":()[]{}^~*?"):
                raise ValueError("plant search accepts literal terms, not raw Solr expressions")
            escaped = query.replace('"', '\\"')
            literal_query = f'"{escaped}"'
            result = await _request(
                "gramene",
                "search",
                params={"q": literal_query, "rows": limit, "wt": "json"},
            )
            return _ok(
                "Gramene plant search",
                "gramene",
                {
                    "release": "v69",
                    "query": literal_query,
                    "result": result,
                    "taxonomy_note": "Gramene taxon_id is provider-specific; do not treat it as NCBI taxid.",
                },
            )

        if tool_name == "cygnusx_plant_get":
            identifier = str(arguments.get("identifier", "")).strip()
            if not _ID.fullmatch(identifier):
                raise ValueError("identifier is required and bounded")
            result = await _request("gramene", "genes", params={"idList": identifier, "rows": 10})
            return _ok(
                "Gramene gene detail", "gramene", {"identifier": identifier, "result": result}
            )

        if tool_name in {"cygnusx_te_search", "cygnusx_te_get"}:
            if tool_name == "cygnusx_te_search":
                query = str(arguments.get("query", "")).strip()
                classification = str(arguments.get("classification", "")).strip()
                clade = str(arguments.get("clade", "")).strip()
                if not query and not classification:
                    raise ValueError("query or classification is required")
                te_params: dict[str, Any] = {
                    "format": "summary",
                    "limit": max(1, min(int(arguments.get("limit", 10)), 50)),
                }
                if query:
                    te_params["name"] = query[:200]
                if classification:
                    te_params["classification"] = classification[:512]
                if clade:
                    te_params["clade"] = clade[:256]
                result = await _request("dfam", "families", params=te_params)
                return _ok(
                    "Dfam family search",
                    "dfam",
                    {
                        "query": query,
                        "classification": classification,
                        "clade": clade,
                        "result": result,
                    },
                )
            accession = str(arguments.get("accession", "")).strip()
            if not _ID.fullmatch(accession):
                raise ValueError("Dfam accession is required")
            result = await _request(
                "dfam", f"families/{quote(accession, safe='')}", params={"format": "summary"}
            )
            return _ok("Dfam family detail", "dfam", {"accession": accession, "result": result})

        if tool_name == "cygnusx_expression_studies":
            provider = "sc_atlas" if bool(arguments.get("single_cell", False)) else "atlas"
            result = await _atlas_directory(provider)
            query = str(arguments.get("query", "")).strip().casefold()
            limit = max(1, min(int(arguments.get("limit", 20)), 50))
            studies = _atlas_experiments(result)
            if query:
                studies = [item for item in studies if query in str(item).casefold()]
            return _ok(
                "Expression Atlas study directory",
                provider,
                {"query": query, "studies": studies[:limit], "total_matches": len(studies)},
            )

        if tool_name == "cygnusx_expression_manifest":
            accession = str(arguments.get("accession", "")).strip()
            if not _ID.fullmatch(accession):
                raise ValueError("experiment accession is required")
            provider = "sc_atlas" if bool(arguments.get("single_cell", False)) else "atlas"
            result = await _atlas_directory(provider)
            studies = _atlas_experiments(result)
            matches = [item for item in studies if accession.casefold() in str(item).casefold()]
            return _ok(
                "Expression Atlas manifest metadata",
                provider,
                {"accession": accession, "matches": matches[:10], "found": bool(matches)},
            )

        if tool_name == "cygnusx_protein_resolve":
            query = str(arguments.get("query", "")).strip()
            organism = arguments.get("organism_id")
            if (
                not query
                or len(query) > 512
                or (organism is not None and not str(organism).isdigit())
            ):
                raise ValueError("query and optional numeric organism_id are required")
            expression = f"({query})"
            if organism is not None:
                expression += f" AND (organism_id:{organism})"
            result = await _request(
                "uniprot",
                "uniprotkb/search",
                params={
                    "query": expression,
                    "format": "json",
                    "size": 10,
                    "fields": "accession,id,protein_name,organism_id,length",
                },
            )
            return _ok("UniProt protein resolve", "uniprot", result)

        if tool_name == "cygnusx_protein_features":
            accession = str(arguments.get("accession", "")).strip()
            section = str(arguments.get("section", "all"))
            if not _ID.fullmatch(accession) or section not in {
                "all",
                "function",
                "location",
                "features",
            }:
                raise ValueError("accession or section is invalid")
            entry = await _request("uniprot", f"uniprotkb/{quote(accession, safe='')}.json")
            comments = entry.get("comments", []) if isinstance(entry, dict) else []
            features = entry.get("features", []) if isinstance(entry, dict) else []
            sequence = entry.get("sequence", {}) if isinstance(entry, dict) else {}
            if section == "function":
                comments, features = (
                    [item for item in comments if item.get("commentType") == "FUNCTION"],
                    [],
                )
            elif section == "location":
                comments, features = (
                    [
                        item
                        for item in comments
                        if item.get("commentType") == "SUBCELLULAR LOCATION"
                    ],
                    [],
                )
            elif section == "features":
                comments = []
            return _ok(
                "UniProt protein features",
                "uniprot",
                {
                    "accession": accession,
                    "primary_accession": entry.get("primaryAccession")
                    if isinstance(entry, dict)
                    else None,
                    "entry_type": entry.get("entryType") if isinstance(entry, dict) else None,
                    "organism": entry.get("organism") if isinstance(entry, dict) else None,
                    "genes": entry.get("genes") if isinstance(entry, dict) else None,
                    "sequence": {
                        "length": sequence.get("length") if isinstance(sequence, dict) else None,
                        "version": sequence.get("version") if isinstance(sequence, dict) else None,
                    },
                    "section": section,
                    "comments": comments[:100],
                    "features": features[:200],
                    "truncated": len(comments) > 100 or len(features) > 200,
                },
            )

        if tool_name == "cygnusx_protein_sequence":
            accession = str(arguments.get("accession", "")).strip()
            if not _ID.fullmatch(accession):
                raise ValueError("UniProt accession is required")
            text = await _request_text("uniprot", f"uniprotkb/{quote(accession, safe='')}.fasta")
            sequence = "".join(text.splitlines()[1:])
            if len(sequence) > 3000:
                return {
                    "success": False,
                    "summary": "Sequence exceeds inline budget; file export is disabled.",
                    "data": None,
                }
            return _ok(
                "UniProt FASTA sequence",
                "uniprot",
                {"accession": accession, "fasta": text, "length": len(sequence)},
            )

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
            result = await _request(
                "interpro",
                path,
                params={"page_size": max(1, min(int(arguments.get("limit", 20)), 50))},
            )
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
            version = await _request_text(
                "reactome", "database/version", accept="text/plain"
            )
            result = await _request("reactome", f"query/{quote(pathway_id, safe='-')}")
            return _ok(
                "Reactome pathway knowledge",
                "reactome",
                {
                    "pathway_id": pathway_id,
                    "release": version,
                    "result": result,
                    "note": "Knowledge lookup only; this is not enrichment analysis or causal direction.",
                },
            )

        if tool_name == "cygnusx_clinvar_search":
            query = str(arguments.get("query", "")).strip()
            if not query or len(query) > 1024:
                raise ValueError("query must be 1-1024 characters")
            result = await _request(
                "clinvar",
                "esearch.fcgi",
                params={"db": "clinvar", "term": query, "retmode": "json", "retmax": 20},
            )
            return _ok("ClinVar search", "clinvar", result)

        if tool_name == "cygnusx_clinvar_get":
            legacy_accession = str(arguments.get("vcv_accession", "")).strip()
            identifier_type = "VCV" if legacy_accession else str(arguments.get("identifier_type", ""))
            identifier = legacy_accession or str(arguments.get("identifier", "")).strip()
            if identifier_type == "AlleleID":
                raise ValueError("Allele ID is unsupported; it is not interchangeable with Variation ID")
            if identifier_type not in {"VCV", "RCV", "SCV", "VariationID"}:
                raise ValueError("identifier_type must be VCV, RCV, SCV, or VariationID")
            pattern = {
                "VCV": r"VCV[0-9]+(?:\.[0-9]+)?",
                "RCV": r"RCV[0-9]+(?:\.[0-9]+)?",
                "SCV": r"SCV[0-9]+(?:\.[0-9]+)?",
                "VariationID": r"[0-9]+",
            }[identifier_type]
            if not re.fullmatch(pattern, identifier):
                raise ValueError(f"identifier does not match {identifier_type} form")

            requested_id, separator, requested_version = identifier.partition(".")
            if identifier_type == "SCV":
                search = await _request(
                    "clinvar",
                    "esearch.fcgi",
                    params={
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
                    params={
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
                root = await _request_xml("clinvar", "efetch.fcgi", params=params)
            projection = _clinvar_projection(root)
            record = projection["record"]
            if identifier_type in {"VCV", "RCV"} and record["accession"] != requested_id:
                raise ValueError(f"ClinVar returned a different {identifier_type} accession")
            if identifier_type == "VCV" and record["record_type"] != "VCV":
                raise ValueError("ClinVar returned a non-VCV record")
            if identifier_type == "RCV" and record["record_type"] != "RCV":
                raise ValueError("ClinVar returned a non-RCV record")
            if separator and identifier_type in {"VCV", "RCV"} and record["version"] != requested_version:
                raise ValueError(f"ClinVar returned a different {identifier_type} version")
            if identifier_type == "VariationID" and record["variation_id"] != requested_id:
                raise ValueError("ClinVar returned a different Variation ID")
            if identifier_type == "SCV":
                match = next(
                    (item for item in record["scv_accessions"] if item["accession"] == requested_id),
                    None,
                )
                if match is None:
                    raise ValueError("ClinVar response does not contain the requested SCV accession")
                if separator and match["version"] != requested_version:
                    raise ValueError("ClinVar returned a different SCV version")
                if separator and match["version"] != requested_version:
                    raise ValueError("ClinVar returned a different SCV version")
            return _ok(
                f"ClinVar {identifier_type} evidence summary",
                "clinvar",
                {
                    "requested_identifier": identifier,
                    "identifier_type": identifier_type,
                    **projection,
                    "note": "Evidence categories are distinct and are not a clinical recommendation.",
                },
            )

        if tool_name in {
            "cygnusx_target_search",
            "cygnusx_target_associations",
            "cygnusx_target_evidence",
        }:
            if tool_name == "cygnusx_target_search":
                query = str(arguments.get("query", "")).strip()
                entity = str(arguments.get("entity", "target"))
                if not query or len(query) > 256 or entity not in {"target", "disease", "drug"}:
                    raise ValueError("entity and query are invalid")
                gql = "query Search($q:String!,$types:[String!]!,$page:Pagination!){search(queryString:$q,entityNames:$types,page:$page){total hits{id name entity}}}"
                variables: dict[str, Any] = {
                    "q": query,
                    "types": [entity],
                    "page": {"index": 0, "size": max(1, min(int(arguments.get("limit", 10)), 50))},
                }
            elif tool_name == "cygnusx_target_associations":
                target = str(arguments.get("target_id", "")).strip()
                if not re.fullmatch(r"ENSG[0-9]+", target):
                    raise ValueError("target_id must be an ENSG identifier")
                gql = "query TargetAssociations($id:String!,$page:Pagination!){target(ensemblId:$id){id approvedSymbol associatedDiseases(page:$page){count rows{disease{id name} score}}}}"
                variables = {
                    "id": target,
                    "page": {"index": 0, "size": max(1, min(int(arguments.get("limit", 10)), 50))},
                }
            else:
                target = str(arguments.get("target_id", "")).strip()
                disease = str(arguments.get("disease_id", "")).strip()
                if not re.fullmatch(r"ENSG[0-9]+", target) or not _ID.fullmatch(disease):
                    raise ValueError("target_id or disease_id is invalid")
                gql = "query TargetEvidence($id:String!,$disease:String!,$size:Int!){target(ensemblId:$id){id evidences(efoIds:[$disease],size:$size){count rows{datasourceId datatypeId score}}}}"
                variables = {
                    "id": target,
                    "disease": disease,
                    "size": max(1, min(int(arguments.get("limit", 10)), 50)),
                }
            result = await _request(
                "opentargets", "", payload={"query": gql, "variables": variables}
            )
            if isinstance(result, dict) and result.get("errors"):
                if not result.get("data"):
                    raise ValueError("Open Targets returned GraphQL errors without data")
                return _ok(
                    "Open Targets query returned partial data",
                    "opentargets",
                    {
                        "result": result,
                        "partial": True,
                        "warnings": ["GraphQL returned errors alongside partial data"],
                    },
                )
            return _ok("Open Targets query", "opentargets", result)

        if tool_name == "cygnusx_literature_get":
            source = str(arguments.get("source", "MED"))
            article_id = str(arguments.get("article_id", "")).strip()
            if source not in {"MED", "PMC"} or not _ID.fullmatch(article_id):
                raise ValueError("source must be MED or PMC and article_id is required")
            result = await _request(
                "europepmc",
                f"article/{source}/{quote(article_id, safe='')}",
                params={"resultType": "core", "format": "json"},
            )
            return _ok("Europe PMC article", "europepmc", result)

        if tool_name == "cygnusx_literature_annotations":
            article_ids = arguments.get("article_ids")
            if (
                not isinstance(article_ids, list)
                or not 1 <= len(article_ids) <= 20
                or any(
                    not re.fullmatch(r"(?:MED|PMC|PPR):[A-Za-z0-9_.-]{1,32}", str(item))
                    for item in article_ids
                )
            ):
                raise ValueError("article_ids must contain 1-20 source-qualified IDs")
            result = await _request(
                "europepmc",
                "annotationsByArticleIds",
                params={"articleIds": ",".join(article_ids), "format": "JSON"},
            )
            return _ok(
                "Europe PMC article annotations",
                "europepmc",
                {"article_ids": article_ids, "result": result},
            )

        return {"success": False, "summary": "Research tool is not registered", "data": None}
    except (httpx.HTTPError, RedisError, TimeoutError, ValueError, TypeError) as exc:
        return {
            "success": False,
            "summary": f"Research provider request failed ({type(exc).__name__}): {exc}",
            "data": None,
        }

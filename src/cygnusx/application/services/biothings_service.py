"""Shared bounded provider service for MyGene, MyVariant, and MyChem."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.parse import quote
from weakref import WeakKeyDictionary

import httpx

_PROVIDERS = {
    "gene": "https://mygene.info/v3",
    "variant": "https://myvariant.info/v1",
    "chem": "https://mychem.info/v1",
}
_DEFAULT_FIELDS = {
    "gene": "symbol,name,taxid,entrezgene,ensembl.gene",
    "variant": "dbsnp.rsid,dbsnp.hg19,dbsnp.hg38,clinvar",
    "chem": "chembl.pref_name,chebi.name,drugbank.name,unii",
}
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_MAX_TOOL_BYTES = 3000
_CLIENTS: WeakKeyDictionary[asyncio.AbstractEventLoop, httpx.AsyncClient] = WeakKeyDictionary()


def _provider_client() -> httpx.AsyncClient:
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


async def close_biothings_clients() -> None:
    clients = list(_CLIENTS.values())
    _CLIENTS.clear()
    for client in clients:
        await client.aclose()


def _fields(kind: str, fields: Any) -> str:
    if fields is not None and not isinstance(fields, str):
        raise ValueError("fields must be a comma-separated string")
    requested = [value.strip() for value in (fields or _DEFAULT_FIELDS[kind]).split(",")]
    if not requested or any(not value or len(value) > 128 for value in requested):
        raise ValueError("fields must contain comma-separated field names")
    if len(requested) > 30:
        raise ValueError("at most 30 fields may be requested")
    return ",".join(dict.fromkeys(requested))


async def _request(kind: str, path: str, params: dict[str, Any]) -> Any:
    response = await _provider_client().get(f"{_PROVIDERS[kind]}{path}", params=params)
    response.raise_for_status()
    if len(response.content) > _MAX_RESPONSE_BYTES:
        raise ValueError("provider response exceeds the 2 MiB response budget")
    if "json" not in response.headers.get("content-type", "").lower():
        raise ValueError("provider returned a non-JSON response")
    return response.json()


def _bound_result(result: dict[str, Any]) -> dict[str, Any]:
    serialized = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    if len(serialized.encode("utf-8")) <= _MAX_TOOL_BYTES:
        return result
    data = result.get("data", {})
    provider_result = data.get("result") if isinstance(data, dict) else None
    if isinstance(provider_result, dict):
        for key in ("hits", "results", "docs"):
            entries = provider_result.get(key)
            if isinstance(entries, list):
                provider_result[key] = entries[:2]
        for key, value in list(provider_result.items()):
            if isinstance(value, str) and len(value) > 300:
                provider_result[key] = value[:300]
    result["truncated"] = True
    serialized = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    if len(serialized.encode("utf-8")) <= _MAX_TOOL_BYTES:
        return result
    context = data.get("input_context") if isinstance(data, dict) else None
    if isinstance(context, dict):
        context = {
            key: value[:96]
            if isinstance(value, str)
            else [item[:64] if isinstance(item, str) else item for item in value[:5]]
            if isinstance(value, list)
            else value
            for key, value in context.items()
        }
    return {
        "success": True,
        "summary": result.get("summary", "BioThings query completed"),
        "data": {
            "provider": data.get("provider") if isinstance(data, dict) else None,
            "input_context": context,
            "truncated": True,
            "result_summary": "Provider response omitted because it exceeds the 3000-byte model budget",
        },
        "truncated": True,
    }


async def execute_biothings(
    database: str, action: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    if database not in _PROVIDERS or action not in {"search", "get", "resolve"}:
        return {"success": False, "summary": "Unknown BioThings operation", "data": None}
    allowed = {
        "search": {"query", "limit", "offset", "fields", "species", "assembly"},
        "get": {"identifier", "fields", "species", "assembly"},
        "resolve": {"identifiers", "scopes", "fields", "species", "assembly"},
    }[action]
    unknown = set(arguments) - allowed
    if unknown:
        return {"success": False, "summary": f"Unknown arguments: {', '.join(sorted(unknown))}", "data": None}
    try:
        fields = _fields(database, arguments.get("fields"))
        params: dict[str, Any] = {"fields": fields}
        if database == "variant":
            assembly = arguments.get("assembly")
            if assembly not in {"hg19", "hg38"}:
                raise ValueError("assembly is required and must be hg19 or hg38")
            params["assembly"] = assembly
        if database == "gene" and action in {"search", "resolve"}:
            species = arguments.get("species")
            if not isinstance(species, str) or not species.strip() or len(species) > 128:
                raise ValueError("species is required for gene search and mapping")
            params["species"] = species.strip()

        if action == "search":
            query = arguments.get("query")
            if not isinstance(query, str) or not query.strip() or len(query) > 2048:
                raise ValueError("query must contain 1 to 2048 characters")
            limit = arguments.get("limit", 10)
            offset = arguments.get("offset", 0)
            if type(limit) is not int or type(offset) is not int:
                raise ValueError("limit and offset must be integers")
            if not 1 <= limit <= 50 or not 0 <= offset <= 10000:
                raise ValueError("limit must be 1-50 and offset must be 0-10000")
            params.update(q=query.strip(), size=limit, **{"from": offset})
            result = await _request(database, "/query", params)
            input_context: dict[str, Any] = {"query": query.strip(), "limit": limit, "offset": offset}
        elif action == "get":
            identifier = arguments.get("identifier")
            if not isinstance(identifier, str) or not identifier.strip() or len(identifier) > 256:
                raise ValueError("identifier must contain 1 to 256 characters")
            result = await _request(
                database, f"/{database}/{quote(identifier.strip(), safe='')}", params
            )
            input_context = {"identifier": identifier.strip()}
        else:
            identifiers = arguments.get("identifiers")
            scopes = arguments.get("scopes")
            if not isinstance(identifiers, list) or not 1 <= len(identifiers) <= 100:
                raise ValueError("identifiers must contain 1 to 100 items")
            if any(
                not isinstance(value, str) or not value.strip() or len(value) > 256
                for value in identifiers
            ):
                raise ValueError("each identifier must contain 1 to 256 characters")
            if not isinstance(scopes, str) or not scopes.strip() or len(scopes) > 256:
                raise ValueError("scopes must explicitly name identifier fields")
            params.update(q=",".join(identifiers), scopes=scopes.strip(), size=100)
            result = await _request(database, "/query", params)
            input_context = {"identifiers": identifiers, "scopes": scopes.strip()}

        kind_name = {"gene": "MyGene", "variant": "MyVariant", "chem": "MyChem"}[database]
        output = {
            "success": True,
            "summary": f"{kind_name} {action} completed",
            "data": {
                "provider": _PROVIDERS[database],
                "input_context": input_context,
                "species": arguments.get("species") if database == "gene" else None,
                "assembly": arguments.get("assembly") if database == "variant" else None,
                "result": result,
            },
        }
        return _bound_result(output)
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        return {"success": False, "summary": f"BioThings request failed: {exc}", "data": None}


async def describe_biothings(database: str) -> dict[str, Any]:
    if database not in _PROVIDERS:
        return {"success": False, "summary": "database must be gene, variant, or chem", "data": None}
    try:
        metadata = await _request(database, "/metadata", {})
        fields = await _request(database, "/metadata/fields", {})
        if isinstance(fields, dict):
            original_count = len(fields)
            fields = dict(list(fields.items())[:500])
            truncated = len(fields) < original_count
        else:
            truncated = False
        return _bound_result(
            {
                "success": True,
                "summary": f"My{database.title()} metadata",
                "data": {
                    "provider": _PROVIDERS[database],
                    "default_fields": _DEFAULT_FIELDS[database],
                    "metadata": metadata,
                    "fields": fields,
                    "fields_truncated": truncated,
                },
            }
        )
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        return {"success": False, "summary": f"BioThings metadata failed: {exc}", "data": None}

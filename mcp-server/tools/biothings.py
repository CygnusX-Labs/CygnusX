"""Thin authenticated FastMCP bridge to the shared platform BioThings service."""

from __future__ import annotations

from typing import Any

from client.api_client import CygnusXAPIClient, CygnusXAPIError
from fastmcp import FastMCP

from tools.research_common import envelope


async def _call(
    api: CygnusXAPIClient,
    database: str,
    action: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    try:
        return await api.biothings(database, action, arguments)
    except (CygnusXAPIError, ValueError) as exc:
        return envelope(False, f"BioThings {database} {action} failed: {exc}")


def register(mcp: FastMCP, api: CygnusXAPIClient) -> None:
    @mcp.tool()
    async def cygnusx_gene_search(
        query: str, species: str, limit: int = 10, offset: int = 0, fields: str = ""
    ) -> dict[str, Any]:
        """Search MyGene by query. Species/taxonomy is required; limit is capped at 50."""
        return await _call(
            api,
            "gene",
            "search",
            {"query": query, "species": species, "limit": limit, "offset": offset, "fields": fields},
        )

    @mcp.tool()
    async def cygnusx_gene_get(identifier: str, fields: str = "") -> dict[str, Any]:
        """Get a MyGene record by Entrez or Ensembl gene identifier."""
        return await _call(api, "gene", "get", {"identifier": identifier, "fields": fields})

    @mcp.tool()
    async def cygnusx_gene_resolve(
        identifiers: list[str], scopes: str, species: str, fields: str = ""
    ) -> dict[str, Any]:
        """Map up to 100 gene identifiers using explicit scopes and species."""
        return await _call(
            api,
            "gene",
            "resolve",
            {"identifiers": identifiers, "scopes": scopes, "species": species, "fields": fields},
        )

    @mcp.tool()
    async def cygnusx_variant_search(
        query: str, assembly: str, limit: int = 10, offset: int = 0, fields: str = ""
    ) -> dict[str, Any]:
        """Search MyVariant. Assembly must explicitly be hg19 or hg38."""
        return await _call(
            api,
            "variant",
            "search",
            {"query": query, "assembly": assembly, "limit": limit, "offset": offset, "fields": fields},
        )

    @mcp.tool()
    async def cygnusx_variant_get(
        identifier: str, assembly: str, fields: str = ""
    ) -> dict[str, Any]:
        """Get a MyVariant genomic-HGVS or variant record for an explicit assembly."""
        return await _call(
            api,
            "variant",
            "get",
            {"identifier": identifier, "assembly": assembly, "fields": fields},
        )

    @mcp.tool()
    async def cygnusx_variant_resolve(
        identifiers: list[str], scopes: str, assembly: str, fields: str = ""
    ) -> dict[str, Any]:
        """Resolve up to 100 variant identifiers with explicit scopes and assembly."""
        return await _call(
            api,
            "variant",
            "resolve",
            {"identifiers": identifiers, "scopes": scopes, "assembly": assembly, "fields": fields},
        )

    @mcp.tool()
    async def cygnusx_chem_search(
        query: str, limit: int = 10, offset: int = 0, fields: str = ""
    ) -> dict[str, Any]:
        """Search MyChem for compound candidates; distinct salts/identities are preserved."""
        return await _call(
            api,
            "chem",
            "search",
            {"query": query, "limit": limit, "offset": offset, "fields": fields},
        )

    @mcp.tool()
    async def cygnusx_chem_get(identifier: str, fields: str = "") -> dict[str, Any]:
        """Get MyChem annotation by a supported chemical identifier."""
        return await _call(api, "chem", "get", {"identifier": identifier, "fields": fields})

    @mcp.tool()
    async def cygnusx_chem_resolve(
        identifiers: list[str], scopes: str, fields: str = ""
    ) -> dict[str, Any]:
        """Map up to 100 compound identifiers using explicit scopes."""
        return await _call(
            api, "chem", "resolve", {"identifiers": identifiers, "scopes": scopes, "fields": fields}
        )

    @mcp.tool()
    async def biothings_describe(database: str) -> dict[str, Any]:
        """Return the selected BioThings provider metadata and searchable field catalog."""
        return await _call(api, database, "describe", {})

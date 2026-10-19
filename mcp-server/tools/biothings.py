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
        """在 MyGene 中按 query 搜索基因候选；species 必填，limit/offset 控制分页（limit 上限 50），fields 可选定返回字段。结果保留候选匹配，不自动替用户选择唯一基因。"""
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
        """在 MyChem 中按 query 搜索化合物注释候选；limit/offset 控制分页，fields 可选定返回字段。不同盐型或化学身份作为独立候选保留；这不是结构相似性或药物对接搜索。"""
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

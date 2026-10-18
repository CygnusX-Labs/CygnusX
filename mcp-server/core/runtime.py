"""Shared MCP transport authentication and REST-client lifecycle."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from hmac import compare_digest

from client.api_client import api
from fastmcp import FastMCP
from fastmcp.server.auth import AccessToken, TokenVerifier
from tools.research_common import close_provider_clients

from core.config import settings


class LocalTokenVerifier(TokenVerifier):
    """Authenticate local HTTP callers, never reinterpret headers as platform owners."""

    async def verify_token(self, token: str) -> AccessToken | None:
        expected = settings.http_token.get_secret_value()
        if len(expected) < 32 or not compare_digest(token.encode(), expected.encode()):
            return None
        return AccessToken(token=token, client_id="local-mcp-client", scopes=[])


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[None]:
    try:
        yield
    finally:
        await api.aclose()
        await close_provider_clients()


def run_server(server: FastMCP, transport: str, port: int) -> None:
    if transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(
            transport="http" if transport == "streamable-http" else transport,
            host=settings.host,
            port=port,
        )

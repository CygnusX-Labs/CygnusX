"""独立 cygnusx-pipelines MCP Server 入口。"""

import sys

from client.api_client import api
from core.config import settings, validate_transport_security
from core.logger import logger
from core.runtime import LocalTokenVerifier, lifespan, run_server
from fastmcp import FastMCP
from tools.pipelines import register

mcp = FastMCP(
    "cygnusx-pipelines",
    instructions="CygnusX RNA-seq 与 ATAC-seq 完整分析流程 MCP 服务",
    auth=LocalTokenVerifier(),
    lifespan=lifespan,
)
register(mcp, api)


def main() -> None:
    transport = settings.transport
    port = settings.port
    args = sys.argv[1:]
    if "--transport" in args:
        index = args.index("--transport")
        if index + 1 < len(args):
            transport = args[index + 1]
    if "--port" in args:
        index = args.index("--port")
        if index + 1 < len(args):
            port = int(args[index + 1])

    if not settings.api_key:
        logger.warning("未设置 CYGNUSX_API_KEY，流水线 API 调用将失败")

    validate_transport_security(transport, settings.host)

    run_server(mcp, transport, port)


if __name__ == "__main__":
    main()

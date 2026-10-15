"""CygnusX MCP Server — 多组学分析平台统一 AI 助手操作接口

启动方式:
  stdio (默认): python main.py
  SSE:          python main.py --transport sse --port 8900

配置:
  编辑 config.yaml 修改连接、工具组开关等设置
  环境变量 (CYGNUSX_*) 优先级高于 config.yaml
"""

import sys

from client.api_client import api
from core.config import settings, validate_transport_security
from core.logger import logger
from core.runtime import LocalTokenVerifier, lifespan, run_server
from fastmcp import FastMCP
from prompts.workflows import register as register_prompts
from resources.catalog import register as register_resources
from tools import register_all_tools

mcp = FastMCP(
    settings.server_name,
    instructions=settings.server_description,
    auth=LocalTokenVerifier(),
    lifespan=lifespan,
)

register_all_tools(mcp, api)
register_resources(mcp, api)
register_prompts(mcp, api)


def main() -> None:
    transport = settings.transport
    port = settings.port

    args = sys.argv[1:]
    if "--transport" in args:
        idx = args.index("--transport")
        if idx + 1 < len(args):
            transport = args[idx + 1]
    if "--port" in args:
        idx = args.index("--port")
        if idx + 1 < len(args):
            port = int(args[idx + 1])

    if not settings.api_key:
        logger.warning("未设置 CYGNUSX_API_KEY，API 调用将会失败")

    validate_transport_security(transport, settings.host)

    logger.info(f"CygnusX MCP Server 启动 (transport={transport}, base_url={settings.base_url})")

    run_server(mcp, transport, port)


if __name__ == "__main__":
    main()

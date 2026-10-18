"""MCP Server 配置 — YAML 文件 + 环境变量覆盖

优先级: 环境变量 > config.yaml > 默认值
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import SecretStr
from pydantic_settings import BaseSettings

_CONFIG_DIR = Path(__file__).resolve().parent.parent
_CONFIG_FILE = _CONFIG_DIR / "config.yaml"


def _load_yaml_config() -> dict[str, Any]:
    if _CONFIG_FILE.exists():
        with open(_CONFIG_FILE) as f:
            return yaml.safe_load(f) or {}
    return {}


_yaml = _load_yaml_config()
_server = _yaml.get("server", {})
_connection = _yaml.get("connection", {})
_limits = _yaml.get("limits", {})
_tool_groups = _yaml.get("tool_groups", {})


class MCPServerConfig(BaseSettings):
    """服务配置。环境变量前缀 CYGNUSX_，覆盖 YAML 值。"""

    model_config = {"env_prefix": "CYGNUSX_"}

    # server
    server_name: str = _server.get("name", "CygnusX")
    server_description: str = _server.get(
        "description",
        "CygnusX 多组学分析平台 MCP Server — 任务管理、数据下载、流程分析、结果解读、沙箱执行",
    )
    transport: str = _server.get("transport", "stdio")
    host: str = _server.get("host", "127.0.0.1")
    port: int = _server.get("port", 8900)
    allow_non_loopback_http: bool = False
    http_token: SecretStr = SecretStr("")

    # connection
    base_url: str = _connection.get("base_url", "http://localhost:8000")
    api_key: str = _connection.get("api_key", "")
    request_timeout: int = _connection.get("request_timeout", 60)

    # limits
    max_file_preview_lines: int = _limits.get("max_file_preview_lines", 50)
    max_log_lines: int = _limits.get("max_log_lines", 100)
    sandbox_timeout: int = _limits.get("sandbox_timeout", 300)

    # MCP 工具固定化（阶段 3）：旧 RNA/ATAC 四件套发现开关。
    # true=旧工具可用（默认，现状/回退）；false=注册同名迁移 stub，
    # 客户端收到明确"已迁移"提示（固定工具 cygnusx_prepare/cygnusx_submit 接管）。
    # 与平台后端 Settings.legacy_pipeline_tools 同语义，需保持一致翻转。
    legacy_pipeline_tools: bool = _yaml.get("legacy_pipeline_tools", True)

    def is_tool_group_enabled(self, group_id: str) -> bool:
        return _tool_groups.get(group_id, True)


settings = MCPServerConfig()


def validate_transport_security(transport: str, host: str) -> None:
    """A configuration flag alone cannot establish trusted gateway authentication."""
    if transport not in {"stdio", "sse", "streamable-http", "http"}:
        raise ValueError("Unsupported MCP transport")
    if transport == "stdio":
        return
    if host not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        raise RuntimeError("MCP HTTP transport must bind to loopback; gateway mode is not implemented")
    if len(settings.http_token.get_secret_value()) < 32:
        raise RuntimeError("MCP HTTP requires a separate CYGNUSX_HTTP_TOKEN of at least 32 characters")

"""AI 助手可调用的工具 Schema 加载器。

与 tools_setting.yaml 解耦：本文件负责把 tools_schema.yaml 加载为 LLM 可消费的
OpenAI function schema，并支持 mtime 热重载。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from omichub.core.config import get_settings


class ToolAnnotation(BaseModel):
    """MCP Tool Annotations 语义标注。"""

    model_config = ConfigDict(extra="ignore")

    read_only_hint: bool = Field(default=False, alias="readOnlyHint")
    destructive_hint: bool = Field(default=False, alias="destructiveHint")
    open_world: bool = Field(default=False, alias="openWorld")
    idempotent: bool = Field(default=False)


class ToolSchema(BaseModel):
    """单个工具完整 schema（含执行元数据）。"""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    key: str
    name: str
    description: str
    category: str = ""
    invocation_mode: str = Field(..., alias="invocation_mode")
    service: str = ""
    method: str = ""
    shim_module: str = Field(default="", alias="shim_module")
    route: str = ""
    requires_confirm: bool = Field(default=False, alias="requires_confirm")
    annotations: ToolAnnotation = Field(default_factory=ToolAnnotation)
    input_schema: dict[str, Any] = Field(default_factory=dict, alias="input_schema")
    llm_result_fields: list[str] = Field(default_factory=list, alias="llm_result_fields")
    ui_result_fields: list[str] = Field(default_factory=list, alias="ui_result_fields")


class ToolsSchemaRegistry(BaseModel):
    """根配置模型。"""

    model_config = ConfigDict(extra="ignore")

    tools: list[ToolSchema] = Field(default_factory=list)


class ToolsSchemaLoader:
    """工具 Schema 加载器，支持 mtime 热重载。"""

    def __init__(self, config_path: str | Path | None = None) -> None:
        self.config_path = str(config_path) if config_path else get_settings().tools_schema_yaml
        self._config: ToolsSchemaRegistry | None = None
        self._mtime: float = 0.0
        self._tools_by_name: dict[str, ToolSchema] = {}

    def _load_yaml(self) -> dict[str, Any]:
        """读盘；文件不存在 / 解析失败时返回空 dict。"""
        path = Path(self.config_path)
        if not path.exists():
            return {}
        try:
            with path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except (yaml.YAMLError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    def _rebuild_index(self) -> None:
        """按 name 重建索引，并校验唯一性（后定义的覆盖先定义的，同时打警告）。"""
        self._tools_by_name = {}
        for tool in self._config.tools if self._config else []:
            if tool.name in self._tools_by_name:
                import logging

                logging.getLogger(__name__).warning(
                    f"tools_schema.yaml 中工具名重复: {tool.name}"
                )
            self._tools_by_name[tool.name] = tool

    def get_config(self) -> ToolsSchemaRegistry:
        """获取配置，自动检测文件变更并热重载；文件缺失返回默认空配置。"""
        path = Path(self.config_path)
        if not path.exists():
            self._config = ToolsSchemaRegistry()
            self._rebuild_index()
            return self._config

        try:
            current_mtime = path.stat().st_mtime
        except OSError:
            return self._config or ToolsSchemaRegistry()

        if self._config is None or current_mtime > self._mtime:
            raw = self._load_yaml()
            try:
                self._config = ToolsSchemaRegistry(**raw)
            except ValidationError:
                import logging

                logging.getLogger(__name__).exception("tools_schema.yaml 校验失败，降级为空配置")
                self._config = ToolsSchemaRegistry()
            self._mtime = current_mtime
            self._rebuild_index()

        return self._config

    def reload(self) -> ToolsSchemaRegistry:
        """强制重载配置。"""
        self._config = None
        return self.get_config()

    def list_tools(self) -> list[ToolSchema]:
        """返回全部工具 schema。"""
        return list(self.get_config().tools)

    def get_tool(self, name: str) -> ToolSchema | None:
        """按 name 查找工具 schema。"""
        self.get_config()
        return self._tools_by_name.get(name)

    def to_openai_tools(self, category: str | None = None) -> list[dict[str, Any]]:
        """转换为 OpenAI functions 格式；可传入 category 做两阶段过滤。"""
        tools = self.list_tools()
        if category:
            tools = [t for t in tools if t.category == category]
        result: list[dict[str, Any]] = []
        for tool in tools:
            schema = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema
                    or {"type": "object", "properties": {}},
                },
            }
            result.append(schema)
        return result

    def build_system_hint(self) -> str:
        """生成注入系统提示词的工具清单。"""
        lines = [
            "你是 OmicHub 生信平台的 AI 助手。当前可调用平台工具（function 名以 omichub_ 开头）："
        ]
        for idx, tool in enumerate(self.list_tools(), 1):
            lines.append(f"{idx}. {tool.name} — {tool.description}")
        lines.extend(
            [
                "规则：",
                "- 需要计算/出图时优先调用工具，不要只给操作说明。",
                "- 大文件用 upload://file_id，不要把整表 CSV 塞进参数。",
                "- 异步工具只负责提交；完成后引导用户根据 task_id / 任务中心查看。",
                "- 标注 requires_confirm 或 destructiveHint 的工具须先说明影响并等待用户确认。",
                "- 当用户确认执行时，请再次调用同一工具并在 arguments 中加入 \"_confirmed\": true。",
                "- 工具参数名为 data_text / gene_text 时，必须传入实际文本内容或 upload://file_id 引用；禁止留空。",
            ]
        )
        return "\n".join(lines)


# 全局单例
schema_loader = ToolsSchemaLoader()


def get_tools_schema_loader() -> ToolsSchemaLoader:
    """FastAPI 依赖用快捷函数。"""
    return schema_loader

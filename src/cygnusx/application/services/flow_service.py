"""Flow 应用服务 — 用例编排：列表、详情、JSON Schema、热重载。"""

from __future__ import annotations

from typing import Any

from cygnusx.application.schemas.flow import (
    FlowDetailDTO,
    FlowListResponse,
    FlowReloadResponse,
    export_flow_json_schema,
    flow_config_to_detail,
    flow_config_to_list_item,
)
from cygnusx.core.config import get_settings
from cygnusx.core.exceptions import NotFoundError
from cygnusx.domain.flow.entities import FlowConfig
from cygnusx.infrastructure.database.repositories import FileSystemFlowRepository


class FlowService:
    """流程应用服务"""

    def __init__(self, repo: FileSystemFlowRepository | None = None):
        self._repo = repo or FileSystemFlowRepository()

    def list_flows(
        self, category: str | None = None, limit: int | None = None, offset: int = 0
    ) -> FlowListResponse:
        """获取流程列表（可按分类过滤；limit/offset 供目录分页，不传返回全量）。"""
        configs = [c for c in self._repo.list_flows(category) if self._enabled(c.meta.id)]
        total = len(configs)
        if limit is not None:
            configs = configs[max(offset, 0) : max(offset, 0) + max(limit, 0)]
        items = [flow_config_to_list_item(c) for c in configs]
        return FlowListResponse(items=items, total=total)

    def list_ai_enabled_flows(self) -> list[FlowConfig]:
        """获取所有启用 AI 助手的流程配置。"""
        return [c for c in self._repo.list_flows() if c.ai and c.ai.enabled and self._enabled(c.meta.id)]

    def get_flow(self, flow_id: str) -> FlowDetailDTO:
        """获取流程详情"""
        config = self._get_or_404(flow_id)
        return flow_config_to_detail(config)

    def get_flow_config(self, flow_id: str) -> FlowConfig:
        """获取原始流程配置对象（供执行层使用）"""
        return self._get_or_404(flow_id)

    def get_flow_parameters(self, flow_id: str) -> list[dict[str, Any]]:
        """获取流程参数定义（前端动态表单用）"""
        config = self._get_or_404(flow_id)
        return [p.model_dump() for p in config.parameters]

    def get_flow_json_schema(self, flow_id: str | None = None) -> dict[str, Any]:
        """获取流程 JSON Schema。

        - 不传 flow_id: 返回 FlowConfig 顶层 Schema（用于前端类型生成）
        - 传 flow_id: 返回该流程的参数校验 Schema
        """
        if flow_id is None or flow_id == "_top":
            return export_flow_json_schema()

        config = self._get_or_404(flow_id)
        # 返回该流程参数的严格 JSON Schema。
        # 复用 FlowToolSchemaCompiler 的编译产物（真实类型/枚举/必填/条件），
        # 替代历史 "type": "any" 占位（"any" 不是合法 JSON Schema 类型，严格校验器会报错）。
        from cygnusx.domain.flow.value_objects import FlowAIConfig
        from cygnusx.tools.flow_schema_compiler import FlowToolSchemaCompiler

        ai = config.ai if (config.ai and config.ai.enabled) else FlowAIConfig(enabled=True)
        compiled = FlowToolSchemaCompiler()._compile_parameters(config, ai)
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": f"Flow parameters: {config.meta.id}",
            "type": "object",
            "description": "该流程参数定义的严格 JSON Schema（由 FlowToolSchemaCompiler 编译自 flows/*.yaml）",
            "properties": compiled.get("properties", {}),
            "required": compiled.get("required", []),
        }

    def reload(self) -> FlowReloadResponse:
        """热重载所有流程配置"""
        count = self._repo.reload()
        return FlowReloadResponse(loaded=count, message=f"已重新加载 {count} 个流程配置")

    @staticmethod
    def _enabled(flow_id: str) -> bool:
        return flow_id != "counts_deg" or get_settings().counts_deg_flow_enabled

    def _get_or_404(self, flow_id: str) -> FlowConfig:
        """获取流程配置，不存在抛 404"""
        config = self._repo.get_by_flow_id(flow_id)
        if config is None or not self._enabled(flow_id):
            raise NotFoundError(f"流程 '{flow_id}' 不存在")
        return config

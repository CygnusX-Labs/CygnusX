"""流程域服务 - YAML 解析、校验"""

import yaml
from pathlib import Path

from omichub.core.exceptions import YAMLConfigError
from omichub.domain.flow.entities import FlowDefinition, FlowParameter, FlowStep
from omichub.domain.flow.repositories import IFlowRepository
from omichub.domain.flow.value_objects import FlowCategory, ParamType, UIControl


class FlowDomainService:
    """流程域服务 - YAML 解析与校验"""

    def __init__(self, repo: IFlowRepository):
        self._repo = repo

    def parse_yaml(self, yaml_path: Path) -> dict:
        """解析 YAML 配置文件"""
        try:
            with open(yaml_path, encoding="utf-8") as f:
                return yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise YAMLConfigError(f"YAML 解析失败: {e}") from e

    def validate_dag(self, steps: list[FlowStep]) -> bool:
        """校验步骤依赖图无环（DAG）"""
        # TODO: 实现拓扑排序检测环
        return True

    async def load_from_yaml(self, yaml_path: Path) -> FlowDefinition:
        """从 YAML 文件加载流程定义"""
        data = self.parse_yaml(yaml_path)
        # TODO: 完整实现 YAML → FlowDefinition 转换
        raise NotImplementedError("待实现 YAML → FlowDefinition 转换")

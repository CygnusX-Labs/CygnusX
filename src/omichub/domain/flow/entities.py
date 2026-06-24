"""流程域实体 - 聚合根"""

from datetime import datetime
from uuid import UUID
from typing import Any

from pydantic import BaseModel, Field

from omichub.domain.flow.value_objects import FlowCategory, ParamType, UIControl


class FlowParameter(BaseModel):
    """流程参数定义"""

    name: str
    label: str
    type: ParamType
    default: Any = None
    required: bool = True
    ui_control: UIControl = UIControl.INPUT
    options: list[str] | None = None
    help_text: str = ""
    group: str = "default"
    depends_on: str | None = None  # 条件依赖


class FlowStep(BaseModel):
    """流程步骤 - Snakemake 规则引用"""

    order: int
    rule: str
    tool: str
    inputs: dict[str, str] = {}
    outputs: dict[str, str] = {}


class FlowDefinition(BaseModel):
    """流程定义聚合根 - YAML 配置的核心"""

    id: UUID
    name: str
    description: str = ""
    category: FlowCategory = FlowCategory.OTHER
    version: str = "1.0.0"
    parameters: list[FlowParameter] = []
    steps: list[FlowStep] = []
    ui_schema: dict[str, Any] = {}
    snakefile_path: str = ""
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

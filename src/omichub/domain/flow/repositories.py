"""流程域仓储接口"""

from typing import Protocol
from uuid import UUID

from omichub.domain.flow.entities import FlowDefinition


class IFlowRepository(Protocol):
    """流程仓储接口"""

    async def get_by_id(self, flow_id: UUID) -> FlowDefinition | None: ...

    async def list_flows(self, category: str | None = None) -> list[FlowDefinition]: ...

    async def save(self, flow: FlowDefinition) -> FlowDefinition: ...

    async def delete(self, flow_id: UUID) -> bool: ...

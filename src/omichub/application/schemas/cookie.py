"""饼干积分系统 DTO"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from omichub.application.schemas.base import OmicsHubBaseSchema


class CookieAccountDTO(OmicsHubBaseSchema):
    """账户信息"""

    id: int | None = None
    user_id: UUID
    balance: Decimal = Decimal("0")
    frozen_balance: Decimal = Decimal("0")
    available_balance: Decimal = Decimal("0")
    total_earned: Decimal = Decimal("0")
    total_spent: Decimal = Decimal("0")
    total_adjusted: Decimal = Decimal("0")
    status: str = "active"
    created_at: datetime | None = None


class CookieTransactionDTO(OmicsHubBaseSchema):
    """交易流水"""

    id: int | None = None
    user_id: UUID
    txn_type: str
    amount: Decimal
    balance_after: Decimal
    source_type: str = ""
    source_id: str = ""
    task_type: str = ""
    description: str = ""
    created_at: datetime | None = None


class CookiePricingDTO(OmicsHubBaseSchema):
    """定价策略"""

    id: int | None = None
    pricing_type: str
    resource_type: str = ""
    flow_category: str = ""
    base_cost: Decimal
    unit: str
    is_active: bool = True
    priority: int = 0
    description: str = ""
    effective_from: datetime | None = None
    effective_until: datetime | None = None


class CostEstimateDTO(OmicsHubBaseSchema):
    """费用预估"""

    flow_id: str
    estimated_cost: Decimal
    breakdown: list[dict] = []
    affordable: bool = True
    current_balance: Decimal = Decimal("0")


class CookieStatsDTO(OmicsHubBaseSchema):
    """系统统计"""

    total_accounts: int = 0
    active_accounts: int = 0
    total_balance: Decimal = Decimal("0")
    total_frozen: Decimal = Decimal("0")
    total_earned: Decimal = Decimal("0")
    total_spent: Decimal = Decimal("0")


class PricingCreateRequest(OmicsHubBaseSchema):
    """创建/更新定价策略请求"""

    pricing_type: str
    resource_type: str = ""
    flow_category: str = ""
    base_cost: Decimal
    unit: str
    priority: int = 0
    description: str = ""
    effective_until: datetime | None = None


class AdjustBalanceRequest(OmicsHubBaseSchema):
    """管理员调整余额请求"""

    amount: Decimal
    reason: str = ""


class AccountFreezeRequest(OmicsHubBaseSchema):
    """冻结/解冻请求"""

    reason: str = ""

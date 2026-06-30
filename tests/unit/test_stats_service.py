"""StatsService 单元测试 — 聚合 / 缺日补零 / flow_id→name 映射逻辑。

直接 mock 仓储层与缓存，验证服务编排逻辑（不依赖真实 DB / Redis）。
"""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from omichub.application.services.stats_service import StatsService
from omichub.domain.task.entities import Task

USER_ID = str(uuid4())


@pytest.fixture
def service() -> StatsService:
    """构造 StatsService，缓存走直通、仓储/流程服务全部 mock。"""
    svc = StatsService(db=MagicMock(), flow_service=MagicMock())
    svc._task_repo = AsyncMock()
    svc._user_repo = AsyncMock()
    svc._flow_service = MagicMock()

    async def _passthrough(_key, _ttl, factory):
        return await factory()

    with patch("omichub.application.services.stats_service.cached_json", _passthrough):
        yield svc


@pytest.mark.asyncio
async def test_user_overview_aggregates_status_and_samples(service):
    service._task_repo.count_by_status.return_value = [
        ("running", 2),
        ("success", 3),
        ("failed", 1),
    ]
    service._task_repo.sum_sample_count.return_value = 10

    result = await service.user_overview(USER_ID)

    assert result == {"running": 2, "total": 6, "samples": 10}
    service._task_repo.sum_sample_count.assert_called_once()


@pytest.mark.asyncio
async def test_user_trend_fills_missing_days(service):
    service._task_repo.count_trend_by_day.return_value = [
        (date.today(), 3, 5),
    ]

    result = await service.user_trend(USER_ID, days=7)

    assert len(result) == 7
    assert result[-1]["tasks"] == 3
    assert result[-1]["samples"] == 5
    # 其余 6 天补 0
    assert all(p["tasks"] == 0 for p in result[:-1])
    # 日期格式 MM/DD，首尾不同（7 天跨度）
    assert all(len(p["date"]) == 5 and p["date"][2] == "/" for p in result)
    assert result[0]["date"] != result[-1]["date"]


@pytest.mark.asyncio
async def test_user_progress_derives_steps(service):
    service._task_repo.count_by_status.return_value = [
        ("running", 1),  # 有运行 → step2 done
    ]

    result = await service.user_progress(USER_ID)

    steps = {s["number"]: s["done"] for s in result["steps"]}
    assert steps[1] is True  # 提交过任务
    assert steps[2] is True  # 运行过管线
    assert steps[3] is False  # 未成功
    assert result["current"] == 3


@pytest.mark.asyncio
async def test_admin_flow_usage_maps_names_and_sorts(service):
    service._task_repo.count_by_flow.return_value = [
        ("atac_seq", 2),
        ("rna_seq", 4),
    ]
    service._flow_service.list_flows.return_value = MagicMock(
        items=[
            SimpleNamespace(id="rna_seq", name="RNA-seq"),
            SimpleNamespace(id="atac_seq", name="ATAC-seq"),
        ]
    )

    result = await service.admin_flow_usage()

    assert result[0] == {"flow_id": "rna_seq", "name": "RNA-seq", "count": 4}
    assert result[1] == {"flow_id": "atac_seq", "name": "ATAC-seq", "count": 2}


@pytest.mark.asyncio
async def test_admin_user_stats(service):
    service._user_repo.count_total.return_value = 5
    service._task_repo.count_active_users_since.return_value = 3

    result = await service.admin_user_stats()

    assert result == {"total_users": 5, "active_users_7d": 3}
    service._task_repo.count_active_users_since.assert_called_once_with(7)


@pytest.mark.asyncio
async def test_admin_recent_failed_serializes(service):
    uid = uuid4()
    task = Task(
        id=uid,
        flow_id="rna_seq",
        user_id=uuid4(),
        name="崩溃的任务",
        status="failed",
        error_message="boom",
    )
    service._task_repo.list_recent_failed.return_value = [task]

    result = await service.admin_recent_failed(limit=10)

    assert len(result) == 1
    assert result[0]["id"] == str(uid)
    assert result[0]["flow_id"] == "rna_seq"
    assert result[0]["error_message"] == "boom"
    service._task_repo.list_recent_failed.assert_called_once_with(10, None)

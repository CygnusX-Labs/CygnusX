"""仪表板统计应用服务 — 个人指标 + 管理员全平台态势。

聚合查询落在仓储层（TaskRepositoryImpl / SqlAlchemyUserRepository），
本服务负责编排、缺日补零、flow_id→name 映射与 Redis 缓存包装。
"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from omichub.application.services.flow_service import FlowService
from omichub.domain.task.value_objects import TaskStatus
from omichub.infrastructure.cache.stats_cache import cached_json
from omichub.infrastructure.database.repositories.task_repository import (
    TaskRepositoryImpl,
)
from omichub.infrastructure.database.repositories.user_repository import (
    SqlAlchemyUserRepository,
)

# 各类缓存 TTL（秒）
_TTL_USER = 60  # 个人指标：1 分钟
_TTL_ADMIN = 300  # 管理员全平台指标：5 分钟


class StatsService:
    """仪表板统计服务"""

    def __init__(
        self,
        db: AsyncSession,
        flow_service: FlowService | None = None,
    ):
        self._db = db
        self._task_repo = TaskRepositoryImpl(db)
        self._user_repo = SqlAlchemyUserRepository(db)
        self._flow_service = flow_service or FlowService()

    # ------------------------------------------------------------------
    # 个人指标（当前用户）
    # ------------------------------------------------------------------

    async def user_overview(self, user_id: str) -> dict:
        """状态卡：运行中 / 总任务 / 累计样本数。"""

        async def _compute() -> dict:
            uid = UUID(user_id)
            statuses = await self._status_map(uid)
            total = sum(statuses.values())
            return {
                "running": statuses.get(TaskStatus.RUNNING.value, 0),
                "total": total,
                "samples": await self._task_repo.sum_sample_count(uid),
            }

        return await cached_json(f"stats:overview:{user_id}", _TTL_USER, _compute)

    async def user_trend(self, user_id: str, days: int) -> list[dict]:
        """近 N 天每日任务数 + 样本数（缺日补 0）。"""

        async def _compute() -> list[dict]:
            uid = UUID(user_id)
            rows = await self._task_repo.count_trend_by_day(days, uid)
            by_date = {row[0]: (int(row[1]), int(row[2])) for row in rows}
            result: list[dict] = []
            for i in range(days - 1, -1, -1):
                d = date.today() - timedelta(days=i)
                tasks, samples = by_date.get(d, (0, 0))
                result.append({"date": d.strftime("%m/%d"), "tasks": tasks, "samples": samples})
            return result

        return await cached_json(f"stats:trend:{user_id}:{days}", _TTL_USER, _compute)

    async def user_progress(self, user_id: str) -> dict:
        """动态用户引导画像：三步完成状态 + 当前步骤。"""

        async def _compute() -> dict:
            uid = UUID(user_id)
            statuses = await self._status_map(uid)
            total = sum(statuses.values())
            run_like = {
                TaskStatus.RUNNING.value,
                TaskStatus.SUCCESS.value,
                TaskStatus.FAILED.value,
            }
            has_run = any(s in statuses for s in run_like)
            has_success = statuses.get(TaskStatus.SUCCESS.value, 0) > 0
            steps = [
                {"number": 1, "title": "提交首个分析任务", "done": total > 0},
                {"number": 2, "title": "运行分析管线", "done": has_run},
                {"number": 3, "title": "获得分析结果", "done": has_success},
            ]
            current = next((s["number"] for s in steps if not s["done"]), None)
            return {"steps": steps, "current": current}

        return await cached_json(f"stats:progress:{user_id}", _TTL_USER, _compute)

    # ------------------------------------------------------------------
    # 管理员全平台指标
    # ------------------------------------------------------------------

    async def admin_status(self) -> dict[str, int]:
        """全平台各状态任务数。"""
        return await cached_json("stats:admin:status", _TTL_ADMIN, self._status_map)

    async def admin_flow_usage(self) -> list[dict]:
        """流程累计调用频次（按 count 降序，flow_id→name 映射）。"""

        async def _compute() -> list[dict]:
            rows = await self._task_repo.count_by_flow(None)
            flow_map = {f.id: f.name for f in self._flow_service.list_flows().items}
            usage = [
                {
                    "flow_id": row[0],
                    "name": flow_map.get(row[0], row[0]),
                    "count": int(row[1]),
                }
                for row in rows
            ]
            usage.sort(key=lambda x: x["count"], reverse=True)
            return usage

        return await cached_json("stats:admin:flows", _TTL_ADMIN, _compute)

    async def admin_user_stats(self) -> dict:
        """全平台注册用户数 + 近 7 天活跃用户数。"""

        async def _compute() -> dict:
            return {
                "total_users": await self._user_repo.count_total(),
                "active_users_7d": await self._task_repo.count_active_users_since(7),
            }

        return await cached_json("stats:admin:users", _TTL_ADMIN, _compute)

    async def admin_recent_failed(self, limit: int = 10) -> list[dict]:
        """近期失败任务（实时，不缓存）。"""
        tasks = await self._task_repo.list_recent_failed(limit, None)
        return [
            {
                "id": str(t.id),
                "name": t.name,
                "flow_id": t.flow_id,
                "user_id": str(t.user_id),
                "error_message": t.error_message,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in tasks
        ]

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    async def _status_map(self, user_id: UUID | None = None) -> dict[str, int]:
        """status -> count 映射。user_id 为 None 时为全平台。"""
        rows = await self._task_repo.count_by_status(user_id)
        return {str(row[0]): int(row[1]) for row in rows}

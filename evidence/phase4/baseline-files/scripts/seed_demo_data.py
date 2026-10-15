"""演示数据种子脚本 — 仪表板 / 任务中心 / 结果报告中心

为本地开发/演示环境造一批任务、样本与报告数据，让三个页面有内容可看：

- 仪表板：运行任务 N 个（status=running）、数据样本 M 条、任务提交趋势（按 tasks.created_at
  分布到过去 30 天，图表近 7 天/近 30 天均有数据）
- 任务中心：RNA-seq / ATAC-seq / 差异分析火山图 / 富集分析 / 数据下载 等命名的历史任务
- 结果报告中心：约 100 份报告（completed 为主，少量 generating/failed/expired，部分收藏、
  部分今日生成），task_id 关联到种子任务，便于「查看结果」跳转演示

用法:
  uv run python scripts/seed_demo_data.py
  docker exec cygnusx-web python scripts/seed_demo_data.py

环境变量（均有默认值）:
  CYGNUSX_SEED_USERNAME         目标用户名 (默认: root，即昵称 JIAN 的管理员)
  CYGNUSX_SEED_RUNNING_TASKS    运行中任务数 (默认: 40)
  CYGNUSX_SEED_SAMPLES          数据样本数 (默认: 1287)
  CYGNUSX_SEED_HISTORICAL_TASKS 历史任务数 (默认: 150)
  CYGNUSX_SEED_REPORTS          报告数 (默认: 137)

幂等性：所有种子任务带 idempotency_key=seed-demo-*，样本 meta.seed=demo-v1，
报告 task_id 只关联种子任务。重复执行会先清掉旧种子数据再重建。
"""

import asyncio
import os
import random
import sys
import uuid
from datetime import UTC, datetime, timedelta, timezone

SEED_MARKER = "demo-v1"
TASK_KEY_PREFIX = "seed-demo-"

FLOW_NAMES: dict[str, str] = {
    "rna_seq": "RNA-seq 差异表达",
    "atac_seq": "ATAC-seq 染色质可及性",
    "deg-analysis": "差异分析火山图",
    "kegg-enrichment": "GO/KEGG 富集分析",
    "ebi_download": "数据下载",
}

TASK_NAME_POOL: list[tuple[str, str]] = [
    ("rna_seq", "RNA-seq 差异表达分析 - 拟南芥热胁迫处理"),
    ("rna_seq", "RNA-seq 转录组定量 - 水稻盐胁迫"),
    ("rna_seq", "RNA-seq 差异表达分析 - 番茄果实发育"),
    ("rna_seq", "RNA-seq 基因表达谱分析 - 小鼠肝脏"),
    ("rna_seq", "RNA-seq 差异表达分析 - 肿瘤 vs 正常对照"),
    ("atac_seq", "ATAC-seq 染色质可及性分析 - 番茄果实发育"),
    ("atac_seq", "ATAC-seq Peak Calling - 小鼠肝脏"),
    ("atac_seq", "ATAC-seq 开放染色质分析 - 拟南芥光照处理"),
    ("deg-analysis", "差异分析火山图绘制 - 上调/下调基因"),
    ("deg-analysis", "差异分析火山图绘制 - 胁迫 vs 对照"),
    ("kegg-enrichment", "GO 富集分析 - 上调差异基因"),
    ("kegg-enrichment", "KEGG 通路富集分析 - 下调差异基因"),
    ("kegg-enrichment", "GSEA 富集分析 - 全基因排序"),
    ("ebi_download", "EBI 下载 PRJNA{acc}"),
]

SPECIES_POOL = ["拟南芥", "水稻", "番茄", "玉米", "小鼠", "人类", "大豆", "葡萄"]
TISSUE_POOL = ["叶片", "根", "果实", "种子", "茎", "花", "肝脏", "血液", "愈伤组织"]


def _local_tz() -> timezone:
    return datetime.now().astimezone().tzinfo or UTC  # type: ignore[return-value]


async def main() -> None:
    from cygnusx.core.config import get_settings
    from cygnusx.infrastructure.cache.stats_cache import invalidate
    from cygnusx.infrastructure.database.models.file import SampleModel
    from cygnusx.infrastructure.database.models.report import ReportModel
    from cygnusx.infrastructure.database.models.task import TaskModel
    from cygnusx.infrastructure.database.models.user import UserModel
    from cygnusx.infrastructure.database.session import get_session_factory
    from sqlalchemy import delete, select

    settings = get_settings()
    if settings.is_production:
        print("错误: 生产环境禁止运行演示数据种子脚本")
        sys.exit(1)

    username = os.getenv("CYGNUSX_SEED_USERNAME", "root").strip()
    n_running = int(os.getenv("CYGNUSX_SEED_RUNNING_TASKS", "40"))
    n_samples = int(os.getenv("CYGNUSX_SEED_SAMPLES", "1287"))
    n_historical = int(os.getenv("CYGNUSX_SEED_HISTORICAL_TASKS", "150"))
    n_reports = int(os.getenv("CYGNUSX_SEED_REPORTS", "137"))
    rng = random.Random(20261003)
    tz = _local_tz()
    now = datetime.now(tz)

    factory = get_session_factory()
    async with factory() as session:
        user = (
            await session.execute(select(UserModel).where(UserModel.username == username))
        ).scalar_one_or_none()
        if user is None:
            print(f"错误: 用户 '{username}' 不存在")
            sys.exit(1)
        user_id = user.id

        # ---- 清理旧种子数据（幂等）----
        old_task_ids = (
            (
                await session.execute(
                    select(TaskModel.id).where(
                        TaskModel.idempotency_key.like(f"{TASK_KEY_PREFIX}%")
                    )
                )
            )
            .scalars()
            .all()
        )
        if old_task_ids:
            await session.execute(delete(ReportModel).where(ReportModel.task_id.in_(old_task_ids)))
            await session.execute(delete(TaskModel).where(TaskModel.id.in_(old_task_ids)))
        await session.execute(
            delete(SampleModel).where(SampleModel.meta["seed"].as_string() == SEED_MARKER)
        )
        await session.flush()

        # ---- 1. 任务：运行中 + 历史（趋势图数据）----
        task_rows: list[TaskModel] = []

        def _make_task(
            key_idx: int,
            flow_id: str,
            name: str,
            status: str,
            created_at: datetime,
            progress: float,
            sample_count: int,
            started_at: datetime | None,
            finished_at: datetime | None,
        ) -> TaskModel:
            return TaskModel(
                id=uuid.uuid4(),
                flow_id=flow_id,
                user_id=user_id,
                name=name,
                status=status,
                progress=progress,
                sample_count=sample_count,
                parameters={"seed": SEED_MARKER},
                idempotency_key=f"{TASK_KEY_PREFIX}{key_idx:05d}",
                created_at=created_at,
                started_at=started_at,
                finished_at=finished_at,
            )

        # 1a. 运行中任务（仪表板「运行任务」计数 = status='running'）
        flow_cycle = list(FLOW_NAMES)
        for i in range(n_running):
            created = now - timedelta(minutes=rng.randint(5, 60 * 20))
            task_rows.append(
                _make_task(
                    i,
                    flow_cycle[i % len(flow_cycle)],
                    name=f"{FLOW_NAMES[flow_cycle[i % len(flow_cycle)]]} - 运行中 #{i + 1:02d}",
                    status="running",
                    created_at=created,
                    progress=round(rng.uniform(0.15, 0.9), 2),
                    sample_count=rng.randint(2, 12),
                    started_at=created + timedelta(minutes=rng.randint(1, 10)),
                    finished_at=None,
                )
            )

        # 1b. 历史任务：created_at 均匀撒到过去 30 天，撑起任务提交趋势图
        key_idx = n_running
        for _ in range(n_historical):
            days_ago = rng.uniform(0.0, 30.0)
            created = now - timedelta(days=days_ago, hours=rng.uniform(0, 12))
            flow_id, name_tpl = rng.choice(TASK_NAME_POOL)
            name = name_tpl.format(acc=rng.randint(100000, 999999))
            roll = rng.random()
            if roll < 0.8:
                status, progress = "success", 1.0
            elif roll < 0.92:
                status, progress = "failed", 0.0
            elif roll < 0.97:
                status, progress = "cancelled", 0.0
            else:
                status, progress = "queued", 0.0
            duration = timedelta(minutes=rng.randint(3, 240))
            task_rows.append(
                _make_task(
                    key_idx,
                    flow_id,
                    name,
                    status,
                    created_at=created,
                    progress=progress,
                    sample_count=rng.randint(2, 15),
                    started_at=created + timedelta(minutes=rng.randint(0, 5)),
                    finished_at=created + duration if status == "success" else None,
                )
            )
            key_idx += 1
        session.add_all(task_rows)
        await session.flush()

        # ---- 2. 数据样本（仪表板「数据样本」计数 = samples 表行数）----
        sample_rows = [
            SampleModel(
                id=uuid.uuid4(),
                user_id=user_id,
                name=f"数据样本-{i + 1:04d}",
                species=rng.choice(SPECIES_POOL),
                tissue=rng.choice(TISSUE_POOL),
                description="演示种子数据",
                meta={"seed": SEED_MARKER},
                file_ids=[],
                created_at=now - timedelta(days=rng.uniform(0, 30)),
            )
            for i in range(n_samples)
        ]
        session.add_all(sample_rows)

        # ---- 3. 结果报告（约 100 份，关联种子任务）----
        success_task_ids = [t.id for t in task_rows if t.status == "success"]
        rng.shuffle(success_task_ids)
        if len(success_task_ids) < n_reports:
            print(
                f"警告: 成功任务数 {len(success_task_ids)} 少于报告数 {n_reports}，部分报告将复用任务"
            )
        flow_weights = (
            ["rna_seq"] * 40
            + ["atac_seq"] * 20
            + ["deg-analysis"] * 15
            + ["kegg-enrichment"] * 15
            + ["ebi_download"] * 10
        )

        report_rows: list[ReportModel] = []
        for i in range(n_reports):
            flow_id = rng.choice(flow_weights)
            # 约 1/10 放今天，其余撒到过去 45 天
            if i % 10 == 0:
                created = now - timedelta(hours=rng.uniform(0, max(now.hour, 1)))
            else:
                created = now - timedelta(days=rng.uniform(0, 45), hours=rng.uniform(0, 12))
            roll = rng.random()
            if roll < 0.85:
                status = "completed"
            elif roll < 0.9:
                status = "generating"
            elif roll < 0.95:
                status = "failed"
            else:
                status = "expired"
            duration_sec = rng.randint(300, 7200)
            report_rows.append(
                ReportModel(
                    id=uuid.uuid4(),
                    task_id=success_task_ids[i % len(success_task_ids)],
                    user_id=user_id,
                    flow_id=flow_id,
                    flow_name=FLOW_NAMES[flow_id],
                    title=f"{FLOW_NAMES[flow_id]}分析报告 {created.strftime('%Y-%m-%d')} #{i + 1:03d}",
                    status=status,
                    sample_count=rng.randint(2, 15),
                    duration=duration_sec,
                    created_at=created,
                    completed_at=created + timedelta(seconds=duration_sec)
                    if status == "completed"
                    else None,
                    is_starred=rng.random() < 0.12,
                    version=1,
                )
            )
        session.add_all(report_rows)
        await session.commit()

        # ---- 4. 失效仪表板统计缓存（60s TTL，避免旧值）----
        await invalidate("stats:overview:")
        await invalidate("stats:trend:")

    print("✅ 演示数据种子完成")
    print(f"   用户:       {user.username} (nickname={user.nickname or '-'})")
    print(f"   运行中任务: {n_running}")
    print(f"   历史任务:   {n_historical} (状态分布见任务中心)")
    print(f"   数据样本:   {n_samples}")
    print(f"   报告:       {n_reports}")


if __name__ == "__main__":
    asyncio.run(main())

# CygnusX 记忆 embedding 模型切换与回填运行手册

> 2026-10-20；对应当前工作区代码。默认过滤/采样开关关闭，真实 PG、Provider、快照演练与质量验收未完成。本文记录已编写工具的操作契约，不代表已获生产灰度准入。
>
> 数据契约见 [记忆架构](CygnusX_memory_architecture.md)，全部发布门禁见 [优化实施方案](../docs/info/26.10.20/CygnusX_AI_记忆系统优化实施方案.md)。

## 1. 适用范围与前置条件

用于 `memory_facts`（默认）或显式选择的 legacy `agent_memories` 的向量维护。只更新向量与模型标识，不重写正文、不恢复 archived/superseded 状态，也不操作块/Studio 文件/受保护 mem0 残留。

在生产快照副本上先完成：实际 pgvector 迁移与备份恢复演练、Provider 真实 1024 维有限向量校验、阶段 0 的 25 案例基线，以及带模型过滤的 EXPLAIN/延迟测试。生产新开关还须满足观测、整理回滚和预发布门禁。当前这些运行证据不足，不能直接按本文开启生产。

DSN 和 Provider 凭据通过原 Secret 机制提供，不写入聊天、命令行、报告或提交。CLI 仅使用显式 `MEMORY_MAINTENANCE_DATABASE_URL`，不回退到 DATABASE_URL；apply 的 Provider 也从同一库选择（默认 active 默认 Provider，可用 `--provider-id` 指定同库的 active 配置），不会从平台默认库读取 Provider。

## 2. 当前实现的模型边界

- `MEMORY_EMBEDDING_MODEL_FILTER_ENABLED=false` 默认沿用旧检索。开启后向量 SQL 限定 `embedding_model = AGENT_MEMORY_EMBEDDING_MODEL`；空配置不比较向量。
- 旧模型、无标签或无向量的事实仍可按词面匹配；即便当前模型向量命中其他事实，也补取不兼容行的关键词候选。这里不是完整 RRF 混合检索，其效果仍需阶段 2-B 评测。
- 同维度不意味着同空间。模型标识按配置字符串精确比较；同名模型/别名背后的供应商版本或端点变化，当前代码不能自动识别。此类变化须单独规划标识和重建，不能据覆盖率 100% 推断向量空间正确。
- 新事实只写有效的“向量 + 非空模型名”配对；缺任一项均保留为无向量词面事实。历史不规范行不会在读取时被静默重标，需运维回填。

## 3. 采集修前证据

固定代码 SHA、未提交差异、数据快照、模型配置与评分口径。先用只读工具记录表与分区基线：

```bash
uv run --frozen python scripts/inspect_memory_baseline.py --output /tmp/memory-before.json
```

该命令使用单独的 `MEMORY_ACCEPTANCE_DATABASE_URL`，同样不回退到默认库。确认两个工具的显式 DSN 指向本次验收的同一副本，不在日志中展示 DSN。

随后配置待验证目标模型，先只做 dry-run（没有 Provider 调用、没有数据写入）：

```bash
uv run --frozen python scripts/backfill_memory_embeddings.py --storage facts --mode mismatch --dry-run --output /tmp/memory-model-dry-run.json
```

报告包含目标模型、active/compatible/missing/mismatched/pending 数量和 coverage。missing 为向量为空；mismatched 为模型标识与目标不同（包括 NULL）；pending 为两者并集，不重复计数。coverage 为兼容且有向量的 active 行占比，空表按 0 返回，不能用空表取得通过结论。报告不含正文、用户 ID 或向量。

没有显式 DSN、未配置模型、连接错误或其他阻断时返回非零退出状态；不要把 blocked/disabled 当作成功。dry-run 成功也只证明取得统计，不证明真实模型可用。

## 4. 预发布逐批重建

通过前置验证后，在隔离环境逐项启用过滤。此时旧向量不会参与当前模型比较，词面查询提供补位。先小批 apply：

```bash
uv run --frozen python scripts/backfill_memory_embeddings.py --storage facts --mode mismatch --limit 100 --apply --output /tmp/memory-model-batch-01.json
```

每次最多 500 行；命令没有自动循环，不会自行扩大成本。`--mode missing` 只补空向量，兼容旧任务语义；切换模型必须显式使用 mismatch（包括缺失及模型不匹配行）。legacy 仅在确需维护旧分支时显式选择 `--storage legacy`。

检查 updated/failed/skipped 和 after：失败项保留原向量/模型，后续可重试；若正文、拥有者、分区、状态、旧模型或旧向量已被其他操作改变，则条件更新跳过，避免覆盖用户归档/编辑或其他回填。每行 Provider 调用绑定本批目标模型，向量与标签成对更新。CLI 整批事务提交成功后才发布更新指标；提交失败则回滚。

failed >0 时 CLI 返回非零；skipped 表示并发变化，不等同模型错误，需核对后重新 dry-run。每批检查后再决定是否继续。不要只比较“处理行数”，应核对实际成功数和 pending 是否下降。

## 5. 监控、性能与切换判定

`MEMORY_EMBEDDING_COVERAGE_ENABLED=false` 默认关闭。单独启用后，Beat 默认每 300 秒向 analysis 投递只读采样；任务仍检查 v2 与站点管理开关。间隔由 `MEMORY_EMBEDDING_COVERAGE_INTERVAL_SECONDS` 配置。

| 指标 | 意义 |
| --- | --- |
| memory.embedding_model_mismatch_rows | 最近采样中 active 模型不匹配行数（含 NULL） |
| memory.embedding_model_coverage | 最近采样的兼容向量占比，0–1 |
| memory.embedding_coverage_sample_timestamp_seconds | 采样时间；须同时检查新鲜度，不能把停采后的旧值当实时值 |
| memory.embedding_backfill_rows | 已提交批次中的 updated/failed/skipped 数量 |

标签仅为 storage/result，不含用户/模型名。Worker 指标需按实际部署的 OTel 导出链路接入；不能假设 Web 的 /metrics 自动收集所有 Worker。完整看板、告警与接收渠道仍属阶段 3-D。

真实库上必须记录带 user/agent/project/status/model 过滤的向量 EXPLAIN 与 P95。小合成集可能选择顺序扫描，不能用它证明生产 HNSW 使用率；HNSW 后过滤也可能少于 LIMIT。本轮未擅自启用依赖特定 pgvector 版本的迭代扫描，也未凭空调整相似度阈值或排序权重。版本、候选数及性能方案须由真实证据决定。

阶段方案建议覆盖率 95%，但最终阈值须按基线裁定；满足覆盖率后仍须跑固定的 25 案例并对比注入/答案/隔离失败。不能用同模型标签一致替代模型质量证明。

## 6. 中止与回退

出现异常先停止后续 apply，关闭对应新开关，保留内容及报告。关闭过滤恢复旧查询行为，但不恢复已被重建覆盖的旧向量。要回到旧模型，需保留旧 Provider，配置旧目标后先 dry-run、再受控重新嵌入；或使用阶段 0 已演练的快照恢复。重嵌入需重新预算调用费用。

v2 新增数据不双写 legacy；关闭 v2 不是无损数据回退，也不会自动继续旧 Chat 注入。不通过删除模型标签、删除表或未经演练的 schema downgrade 来回退。

## 7. 可复用验收入口

```bash
uv run --frozen pytest tests/unit/test_memory_embedding_models.py tests/unit/test_memory_embedding_cli.py -q
uv run --frozen pytest tests/integration/test_memory_embedding_postgres.py -q
```

后者仅在显式 `MEMORY_TEST_DATABASE_URL` 指向 `memory_acceptance_test*` PostgreSQL 时创建临时 schema，要求预装 pgvector；覆盖真实模型过滤、关键词补位、重建和合成 EXPLAIN，不调用真实 Provider，也不代表全链快照迁移/P95 压测。缺 DSN 时 skipped，当前运行验收仍未完成。

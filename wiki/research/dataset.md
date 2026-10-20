# Dataset 与 Handoff

Dataset 是平台对“科研输入资产”的版本化模型：它把来源、文件、样本、人工审阅和执行交接分开记录，使一个 Flow 提交能够说明“用了哪个版本的哪些文件、哪些样本、经过谁审阅、还有哪些缺口”。

> **当前状态**：七表模型、版本冻结、GEO/ENA 只读证据、导入预案、文件校验与冻结 Handoff 已实现，迁移为 `bioopsphase3`。**运行准入仍 BLOCKED**：`worker_paths_verified=false`，导入/提交开关默认关闭，Task 写入还受 `WRITE_RUNTIME_ACCEPTED=False` 保护。

## 关系模型

```text
Project
  └─ Dataset                             资产集合的身份
       └─ DatasetVersion                 冻结版本
            ├─ DatasetSource             GEO/ENA/上传等来源与原始证据
            ├─ DatasetAsset              → FileRecord（文件引用，不复制）
            ├─ DatasetSample             → Sample（样本映射）
            ├─ DatasetIngestion          导入请求/审批快照/任务对账（version_id 可空）
            ├─ handoff（JSON 列）         版本内冻结交接契约
            └─ DatasetAnalysisLink       → TaskService 提交（version_id + handoff_hash）
```

- 共七张物理表：`datasets`、`dataset_versions`、`dataset_sources`、`dataset_assets`、`dataset_samples`、`dataset_ingestions`、`dataset_analysis_links`，物理表名与字段以迁移 `bioopsphase3` 和 ORM 为准。
- **Dataset Ingestion 是持久化实体**：`dataset_ingestions` 记录导入请求、审批快照、任务 ID 与状态，可在版本生成前创建并关联既有版本（`version_id` 可空）。
- **Handoff 是 DatasetVersion 内部的交接契约**：存于 `dataset_versions.handoff` JSON 列，**不对应独立物理表**；提交时 `dataset_analysis_links.handoff_hash` 固化其 SHA-256。
- 旧 FileRecord、Sample、Task、Project **不重建、不回填**；Dataset 只建立引用。
- 权限为当前代码可证明的 **owner-only**；不能推测共享 ACL。
- 每次挂接、审阅、Manifest、提交都重新检查 owner/project/模块/文件生命周期。

## 版本与冻结

| 规则 | 说明 |
| --- | --- |
| 版本冻结后不可编辑 | 资产、样本、来源和审阅记录都锁定 |
| 新版本复制来源与关联 | 重置资产校验，保留旧版本与人工审阅历史 |
| 人工用途独立 | 实验类型/用途由人选择，不能把未知矩阵提升为 raw counts |
| Handoff 稳定排序 | 对规范化 JSON 计算 SHA-256 |
| Handoff 内容 | 来源、文件实测 SHA-256、样本映射、人工审阅、缺口 |
| 不是数字签名 | 数据库不防管理员篡改；真实执行前必须复验文件 |

## 一次导入

```text
人类 JWT
  → discover / prepare（明确来源选择）
  → 绑定 owner/project/selection/budget/source hash
  → 返回 proposal + limitations（此时不创建下载 Task）
  → approve（只记录批准）
  → execute
       → Phase2 源码门禁 + Phase3 开关
       → 复核 scope/quota/source
       → 一次性消费批准
       → SUBMITTING 保留 → 原 DownloadService 提交
       → 事务提交后 enqueue
  → reconcile-only：检查既有 Task，验证 FileRecord 与内容
  → COMPLETED / PARTIAL / 需人工对账
```

- 批准快照保存 JWT 来源哈希、actor、摘要、版本与单消费证明；Redis 与持久记录必须一致。
- `SUBMITTING` 是持久保留状态；超时不自动重放，需人工对账。
- 定时 reconciler 在门禁关闭时**在创建 DB engine 前返回**，不重投下载、不处理歧义状态。

## 文件校验边界

校验限制总字节、行列、行长、解压数量/大小/比例；拒绝：

- 路径逃逸、硬链接/软链接、特殊文件、归档覆盖；
- 非有限/负数/分数 counts；
- 重复 feature/sample；
- 方向未知的矩阵。

整数外观但没有源处理证据时保留 `UNKNOWN`。以下内容不进入 raw counts DEG：

- TPM/FPKM/CPM/log 转换矩阵；
- Series Matrix；
- 单细胞容器；
- 未经权威证据说明的 processed 数据。

GEO/ENA 适配器只读：受信 HTTPS 主机、禁重定向、响应/样本/Run 上限、超时与缓存；每条证据保留 URL、获取时间与响应摘要。GSE/GSM metadata 不自动推导分组真值。

## Flow 交接

| 输入 | 目标 | 状态 |
| --- | --- | --- |
| FASTQ | 现有 RNAFlow（v2.3.0） | 显式参考/物种/链特异性、样本前缀与配对一致，不自动重命名 |
| raw integer counts | `pipelines/CountsDEGFlow` | 本地 R/DESeq2 与 Snakemake 合成验证通过；Worker/镜像/FlowFrame 监控认证未通过，默认不注册为可用能力 |

Handoff 通过 `AnalysisFlowToolService` 与原 Validator 进入 `TaskService`；`worker_paths_verified=false` 表示 Worker 路径尚未验收，**不是 READY**。

## 功能开关

| 开关 | 默认 | 作用 |
| --- | --- | --- |
| `DATASET_DISCOVERY_READONLY` | 只读发现 | 资产目录与 JWT 人工元数据登记/审阅；不代表数据库绝对只读 |
| `DATASET_IMPORT_WRITE` | false | Dataset 导入写入 |
| `ANALYSIS_SUBMIT_FROM_DATASET` | false | 从 Dataset 提交分析 |
| `COUNTS_DEG_FLOW_ENABLED` | false | counts DEG 流程可用性 |
| `WRITE_RUNTIME_ACCEPTED` | false（源码常量） | 所有 Task 写入的最终门禁 |

## 常见误区

1. “Dataset 版本存在” ≠ “可以执行”：还要 Handoff、Worker 路径和源码门禁。
2. “文件 SHA 一致” ≠ “内容适合该 Flow”：还要用途、方向、样本映射和人工审阅。
3. “审批已通过” ≠ “任务已创建”：execute 还要消费批准并通过业务门禁。
4. “reconcile 完成” ≠ “下载成功”：可能是 PARTIAL 或需人工对账。

## 代码锚点

| 组件 | 位置 |
| --- | --- |
| 迁移 | `bioopsphase3`（前驱 `bioopsphase2`） |
| Dataset 服务 | `src/cygnusx/application/services/` Dataset 相关服务 |
| Handoff 门禁 | `dataset_handoff_service.py` 的 `worker_paths_verified` |
| 分析提交 | `dataset_analysis_service.py`、`AnalysisFlowToolService` |
| 契约 | `docs/contracts/cygnusx-dataset-handoff-v1.md` |

## 关联文档

- 权威基线：[`CygnusX_dataset_architecture.md`](../../ARCHITECTURE_DESIGN/CygnusX_dataset_architecture.md)
- [数据发现与获取](data-discovery) · [科研交付链](delivery) · [Flow 运行时](../architecture/flow-runtime) · [科研能力与证据边界](evidence-boundaries)

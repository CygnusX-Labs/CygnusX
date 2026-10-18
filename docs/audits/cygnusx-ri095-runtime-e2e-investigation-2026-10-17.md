# RI09.5 真实运行与 E2E 验收调查报告

调查日期：2026-10-17（Asia/Shanghai）。本文是本次实际执行的调查报告，不是验收通过证明。

- Run ID：`ri095-20261017-attempt1`
- 仓库：`/home/zj/zj_code_libarary/OmicHub`
- 分支 / commit：`feat/research-agent-phase5` / `d9c92cf6ee1c`
- 方案依据：`docs/info/26.10.17/RI095-Runtime-E2E-Acceptance-Plan.md`、`docs/info/26.10.17/RI095-Runtime-Validation-Agent-Prompt.md`
- 证据目录：`evidence/runtime-acceptance/ri095-20261017-attempt1/`（69 个文件，SHA 索引见 `evidence/runtime-acceptance/artifact-index.json`）

## 1. 结论摘要

历史阻塞是 Docker socket 返回 `operation not permitted`。本次调查确认该阻塞已解除：当前用户 `zj` 属于 `docker` 组，Docker 28.3.3 可正常创建、运行和停止容器。据此启动了隔离验收环境并执行了真实运行。

| 层级 | 结论 |
|---|---|
| PASS_STATIC | 通过（离线六项拒绝回归 + 未授权变量拒绝） |
| PASS_RUNTIME | 核心 Gate 达成：PG/迁移、约束、并发、JWT、私有存储、报告 HTML、导出 ZIP |
| PASS_E2E | **未达成**（浏览器沙箱不可用） |

本次发现 2 个真实缺陷，均已给出最小修复并通过重跑验证。其余为环境或前置条件阻塞，未以任何方式伪造通过。

判定说明：Docker 能启动不等于 RI09.5 完成。浏览器、PDF、对象存储、corpus 相关业务验收仍为 BLOCKED。

## 2. 背景与历史基线

三份原始文档（SHA-256 已核对，与方案一致）：

| 文档 | 路径 | SHA-256（前 8 位） |
|---|---|---|
| 环境 | `docs/audits/cygnusx-runtime-acceptance-environment.md` | `18245dad` |
| 结果 | `docs/audits/cygnusx-ri095-runtime-e2e-results.md` | `d00e2b28` |
| 稳定化 | `docs/implementation/cygnusx-ri095-runtime-stabilization.md` | `3b73125f` |

历史基线：配置交付 PARTIAL，配置保护检查 PASS_STATIC；RA01–RA06、HTML/PDF、存储、JWT、M0→Report→M1→ZIP、浏览器全部 BLOCKED，无 PASS_RUNTIME、无 PASS_E2E。历史静态结果不自动继承为本次通过。

## 3. 准入门槛核查

| 核对项 | 状态 | 证据 |
|---|---|---|
| 仓库路径 / commit / 分支 | 已记录 | `baseline/repo.txt` |
| 源文档 SHA-256 | 与方案一致 | `baseline/source-docs-sha256.txt` |
| Docker 目标与身份 | unix socket，uid 1000 / docker 组 | `authorization/docker-target.txt` |
| 隔离资源清单 | project `cygnusx-ri095-acceptance` | `preflight/` |
| 镜像 digest | 全部固定 sha256 | `preflight/images-used.txt` |
| corpus 批准记录 | **缺失** | 见第 8 节 |

准入阶段的一个重要事实：`deploy/acceptance/` 目录及本次相关的迁移文件在 git 中为**未跟踪**状态（分支上既有的未提交工作，并非本次调查创建）。这解释了为何这些工具此前从未真正启动过，也解释了两个缺陷为何从未暴露。核查结果已记录于 `baseline/repo.txt` 的 tracking note。

## 4. 隔离环境与镜像

### 4.1 拓扑

Playwright → frontend:8080 → api:8000 → PostgreSQL；API → Redis DB1（队列 `ri095_acceptance`）→ Worker；Beat 仅调度项目 report/export reconcile；Worker → 独占私有卷。所有服务仅连接 internal 网络，无宿主发布端口。

### 4.2 镜像

要求所有镜像固定 digest。本地构建的镜像没有 RepoDigests，因此临时启动本地 registry（`127.0.0.1:5000`，仅回环）推送后取得 digest。registry 不属于验收拓扑，收尾时已移除。

| 用途 | digest |
|---|---|
| 应用（含迁移/data） | `ri095-app-ext@sha256:7bdd67546e96...` |
| 前端 | `ri095-frontend@sha256:38d2889c0106...` |
| PostgreSQL | `ri095-postgres@sha256:206431915c6d...` |
| Redis | `ri095-redis@sha256:41a05f1df0e4...` |
| 浏览器 | `ri095-browser@sha256:93174f73acae...` |

应用镜像基于 `Dockerfile.worker` 按当前源码重建（现有 `cygnusx-worker` 镜像的源码与 HEAD 不一致，161 行差异），再套用 `deploy/acceptance/Dockerfile` 补齐 `/app/data` 与 UID 10001 私有卷目录。前端镜像因 `frontend/package-lock.json` 与 `package.json` 不同步（lock 为 8 月，package.json 为 10 月）导致容器内 `npm ci` 失败，改用现有 `frontend/dist` 构建最小 nginx 镜像。

浏览器镜像在官方 Playwright 基础镜像之上补装匹配版本的 `playwright` npm 包（镜像自带 Chromium build 1148，对应 playwright 1.49.0）；基础镜像本身不含该 Node 包。

## 5. 缺陷调查

### 5.1 缺陷一：Compose tmpfs 解析错误

- 现象：`control.py start` 在启动 migrate 容器时报 `invalid mount path: 'gid=10001'`。
- 影响面：所有带 uid 10001 的容器，首次真实启动即失败。
- 根因：`compose.yml` 中 `tmpfs: [/tmp:uid=10001,gid=10001,mode=1777]` 使用 YAML 流式序列，逗号被解析为数组分隔符，得到 `['/tmp:uid=10001', 'gid=10001', 'mode=1777']` 三项，Docker 将 `gid=10001` 当作挂载路径。
- 最小修复：将该标量加引号改为 `tmpfs: ["/tmp:uid=10001,gid=10001,mode=1777"]`。三处同改。
- 验证：加引号后 `compose config` 解析为单个正确的 tmpfs 项。

### 5.2 缺陷二：全新库迁移顺序缺陷（真实代码缺陷）

这是本次调查最重要的发现。

- 现象：空库执行 `alembic upgrade head` 失败：

  ```
  sqlalchemy.exc.ProgrammingError / asyncpg UndefinedTableError
  relation "mcp_versions" does not exist
  [SQL: ALTER TABLE mcp_versions ADD COLUMN contract_digest VARCHAR(80) DEFAULT '' NOT NULL]
  ```

- 影响面：**全新 / 空数据库的首次部署无法完成**。这是环境无关缺陷，在隔离验收库中稳定复现。
- 已执行量：失败前已应用 42 个 revision；失败后整个事务回滚，库中 `public` schema 表数为 0，`alembic_version` 不存在。

根因：

Alembic 对并行分支按自身启发式排序（不是按提交时间）。在本次线性化中：

| revision | 作用 | 依赖 |
|---|---|---|
| `c1d2e3f4b5a6` | `ALTER mcp_versions ADD contract_digest` | `down_revision = a5b6c7d8e9f0` |
| `h6i7j8k9l1m3` | `CREATE TABLE mcp_versions`（add_mcp_builder_tables） | `down_revision = g4h5i6j7k8l9` |

两者互不为祖先。它们仅在 `mcpdigestmerge01` 汇合，而 `h6i7j8k9l1m3` 所在的链经另一条 merge 路径到达该 mergepoint。没有任何依赖边强制「CREATE 先于 ALTER」。

实测顺序（来自运行日志）：

- 失败运行：`c1d2e3f4b5a6` 位于第 42 个（最后一个执行），`h6i7j8k9l1m3` **从未执行**（计数 0）。
- 修复后运行：`h6i7j8k9l1m3`（CREATE）位于第 49 个，`c1d2e3f4b5a6`（ALTER）位于第 55 个，顺序正确。

为何既有门禁未发现：

- `make check-migrations` 与 alembic autogenerate 只校验拓扑连通与 head 唯一，两者均通过；它们不校验语句级的表存在性顺序。
- 已存在的数据库在其历史中已创建过 `mcp_versions`，因此永远不会重新走到这个错误顺序。缺陷只在真正空库上暴露。

最小修复：将 `c1d2e3f4b5a6` 的 `down_revision` 由 `a5b6c7d8e9f0` 改为 `h6i7j8k9l1m3`，使 ALTER 分支从 CREATE 分支派生。修复后 head 仍唯一（`projectreport01`）。

验证：空库从 0 升级到 head，共应用 111 个 revision，最终 `alembic current` = `projectreport01`，`state.sql` 输出正常（`attempt2-fixed/`）。失败记录与修复记录并存，未覆盖（`attempt1-freshfail/`、`attempt2-fixed/`）。

## 6. 逐 Gate 结果

### 6.1 RA01 迁移

- 状态：FAIL → 最小修复后 PASS_RUNTIME。
- 证据：`ra01/attempt1-freshfail/`（含 `FINDING-migration-order.md`、失败日志）、`ra01/attempt2-fixed/`（修复后日志、`state.sql.out`）。
- 说明：README 要求「空库升级 head 不能替代旧模型升级验收」。真正的旧模型升级验收需要已批准的脱敏旧模型制品/记录作为 corpus，本次 corpus 缺失，故**旧模型升级路径本身仍为 BLOCKED**；本节仅证明空库全新部署路径在修复后可用。

### 6.2 RA02 真实 PostgreSQL 约束

- 状态：PASS_RUNTIME。
- 环境：真实 PostgreSQL 14.23（非 SQLite）。
- 证据：`ra02/ra02-results.txt`。

| # | 场景 | 预期 SQLSTATE | 实测 |
|---|---|---|---|
| 1 | `report_files` XOR 双 NULL | 23514 | 23514 |
| 2 | `report_files` XOR 双非空 | 23514 | 23514 |
| 3 | FK 指向不存在的 `file_record` | 23503 | 23503 |
| 4 | XOR 恰一项（合法） | 无错误 | 00000 |
| 5 | 变更冻结的 export manifest | P0001 | P0001 |
| 6 | 变更冻结的 report identity | P0001 | P0001 |
| 7 | `status=ready` 但缺 html 字段 | 23514 | 23514 |
| 8 | export 状态越出枚举 | 23514 | 23514 |
| 9 | report 状态越出枚举 | 23514 | 23514 |
| 10 | `attempt_count < 0` | 23514 | 23514 |
| 11 | 重复 `(user,project,source_digest)` | 23505 | 23505 |
| 12 | 合法更新 | 无错误 | 00000 |

冻结语义由触发器函数实现并给出自身错误消息：「Frozen project export scope cannot change」「Frozen project report identity cannot change」。

### 6.3 RA03 并发 / 锁 / 项目保留

- 状态：PASS_RUNTIME（部分范围）。
- 证据：`ra03/RA03-RESULT.md`、`ra03-race-8concurrent.txt`、`job-count.txt`。
- 方法：真实 FastAPI + 真实 JWT（owner A），对 `POST /api/v1/projects/{id}/scientific-summary` 发起 8 个并发请求，`request_key` 互不相同、`source_manifest_job_id` 相同。

结果：

| 观测项 | 结果 |
|---|---|
| HTTP 状态 | 8 个全部 200 |
| 返回的 job id | 8 个全部相同：`99323137-44f8-4bea-ad62-b65ad10d3962` |
| 响应中可见状态 | queued / validating / publishing / ready（实时推进） |
| 库中创建的 job 数 | 1（唯一约束 `(user_id, project_id, source_digest)` 生效） |
| `attempt_count` | 1（单次执行，无重复发布） |

即：唯一约束 + 幂等创建把并发竞争收敛到同一 job，未产生重复发布。

Advisory lock 原语在真实 PG 上验证：同会话可重入、可释放（`advisory-lock-mech.txt`）。报告任务路径在该锁保护下执行并在 `finally` 释放（`project_reports.py`）。

未覆盖：README 要求的「8 个不同来源版本」变体，以及项目删除 / 停用后的保留语义——这两项依赖存在于已完成任务 corpus 中的多来源版本，corpus 缺失，BLOCKED。

### 6.4 RA04 / RA05 / RA06 Celery

- 状态：PARTIAL。
- 证据：`ra04/RA04-06-RESULT.md`、`worker-registry.txt`、`worker-dispatch-roundtrip.txt`、`duplicate-dispatch*.txt`、`ra06/`。

必须说明的定义缺口：三份原始文档只把 RA04–06 合称为「RA04–06 Celery」，**未给出逐 Gate 完整定义**。执行提示词要求「找不到、互相冲突或执行器缺失时明确 BLOCKED，不自行重新分配编号」。因此本节只报告可观测的 Celery 行为，不声称覆盖了原始的逐 Gate 断义。

已观测：

- Broker 为 Redis DB1、队列 `ri095_acceptance`；Worker 注册表精确限定为 4 个任务；Beat 调度仅保留 2 个 reconcile，每 60 秒触发一次，Worker 正常消费。
- 真实派发往返：`send_task` → broker → Worker「received」→「started」→「finished」，均有真实 task id（如 `acec9765-...`）。
- 故障关闭（fail-closed）：写门禁关闭时 `generate_project_report` 抛出 `DependencyUnavailableError`（「Project scientific report generation is not admitted」），在接触数据库前即拒绝。
- 重复投递幂等：对已 ready 的 job 重复派发 3 次，`attempt_count` 仍为 1，`status` 仍为 ready，`html_sha256` 不变，无重复发布。
- Beat reconcile 恢复：将 job 置为陈旧 queued（`updated_at` 早于 10 分钟），`reconcile_project_reports` 重新派发（`dispatched: 1`），随后重新执行并按预期记录失败 `error_code=invalid_evidence`。

未覆盖：精确到阶段（validating / rendering / publishing）的故障注入。README 明确「发布成功 / 提交失败需要受控、可复核注入点，此处尚未实现」。未以随机 kill 冒充。

### 6.5 HTML 报告

- 状态：PASS_RUNTIME。
- 证据：`report/`。
- 真实 Worker 生成 6635 字节 HTML，`html_sha256 = 1d89e889399a611a708e1528e8c1be44b033a022d1b09fbc12f5e69bc999c33a`，磁盘、数据库、HTTP 下载三处 SHA 一致。HTML 含中文内容与 provenance 标签。
- PDF：**BLOCKED**。`control.py versions` 探测同一 Worker 镜像内 `pandoc` / `typst` / `fc-list` 全部 MISSING（`report/versions.log`），`pdf_status=PDF_NOT_GENERATED`。

### 6.6 私有存储

- 状态：PASS_RUNTIME（本地后端范围）。
- 证据：`storage/`。
- 原子发布 → 回读校验通过：FileRecord（owner = user A）与 ReportFile 正确关联，磁盘 / 数据库 / 下载摘要一致。
- 对象存储：**BLOCKED**。无授权的独立测试 Bucket。结论只能称「本地存储范围通过」，对象存储状态未被掩盖。

### 6.7 JWT 与授权

- 状态：PASS_RUNTIME。
- 证据：`auth/`。

| 场景 | 结果 |
|---|---|
| JWT 访问 `/auth/me` | 200 |
| JWT 创建 API key | 201 |
| API key 访问 JWT 专用路径 | 401（按契约拒绝） |
| 无认证访问 | 401 |
| 跨 owner 读取 A 的项目 / 下载 A 的报告 | 404 |
| B 的项目列表 | `[]`（无泄露） |
| 停用用户后复用既有 JWT | 401（`/auth/me` 与下载均拒绝，未泄露文件内容） |

说明：按 README 使用真实 `/auth/register`（默认 `status=pending`）创建用户；为取得可用身份，在隔离 disposable 库中直接将状态提升为 active / admin，密码仍为真实注册哈希。响应状态码以仓库契约为准，未臆定一律 403。

### 6.8 M0 → Report → M1 → ZIP

- 状态：PASS_RUNTIME（机制层面），含已记录缺口。
- 证据：`chain/`。
- 真实 Worker 生成的导出 ZIP 为 7372 字节，`archive_sha256 = e8ad747148b1b17842cab7d4067938c52023a0a3ca8ca966b1e067c4d5b11c37`，磁盘与数据库一致。成员：`ProjectDeliveryManifest.json`、`README.md`、`checksums.sha256`、`verify_project_delivery.py`。
- 使用仓库自带的 stdlib 验证器 `cygnusx.domain.project_delivery_archive.verify_archive` 校验该 ZIP，返回 OK。manifest 中 `evidence_status="partial"` 如实声明，`gaps` 列出 `HISTORICAL_ASSOCIATION_COVERAGE_NOT_RECORDED` 与 `REPRODUCTION_NOT_RUN`。

已记录缺口：

1. 生成的 HTML 科学报告**未包含在导出 ZIP 内**。本次使用的是默认 `ExportSelection`（`kind=evidence`，task / report id 为空），因此 `files[]` 仅有 README 与验证器。要包含项目报告需使用 `ExportSelectionV2`（显式指定 `source_manifest_job_id` 与 `project_report_job_ids`），属另一种显式选择的导出。
2. 「M0 → M1」版本跃迁比较，以及「旧 M0 / 旧 ZIP 字节在多轮之间不变」的验证，需要已批准的、含冻结历史 M0 与 ZIP 基线的完成任务 corpus。仓库中不存在该 corpus。

### 6.9 浏览器 E2E

- 状态：BLOCKED。
- 证据：`browser/BLOCKED-reason.md`、`browser-probe-BLOCKED.log`。
- 现象：Chromium 无法启动，`FATAL:zygote_host_impl_linux.cc(128) No usable sandbox!`。
- 根因：宿主 `kernel.apparmor_restrict_unprivileged_userns=1`（Ubuntu 23.10+ 起 AppArmor 限制非特权 user namespace），内核 6.8.0-147-generic。
- 处置：README 明确「保留 Chromium sandbox；若宿主 seccomp / userns 不支持，标 BLOCKED，不加 `--no-sandbox` 伪造成功」。本次遵守，未加绕过参数。

## 7. 收尾与回滚

| 步骤 | 结果 | 证据 |
|---|---|---|
| 私有 env 的 READS / WRITES / PDF 置 false | 已置 false | `rollback/flags-closed.txt` |
| 关闭状态下 preflight | PASS_STATIC | `rollback/preflight-closed.txt` |
| 停止本专用 project | 6 容器全部 Exited(0) | `rollback/containers-after-stop.txt` |
| 保留 PG / Redis / 私有卷 | 3 个卷保留 | `rollback/volumes-retained.txt` |

未执行 `down -v`、未执行迁移 downgrade、未执行 prune。开发栈（22 个 `cygnusx-*` 容器）与生产默认值未受影响。收尾前已保存最终只读 `state.sql` 快照（`rollback/state-final.sql.out`）。

## 8. 阻塞项与解除条件

| 阻塞项 | 原因 | 解除条件 |
|---|---|---|
| corpus 相关业务验收 | 仓库中不存在已批准的既有完成任务 / 制品 corpus | 提供 corpus 来源、owner、任务状态、访问授权与可信预期哈希，以隔离副本导入 |
| RA01 旧模型升级路径 | 同上（需脱敏旧模型制品 / 记录） | 随 corpus 一并提供 |
| 存储漂移 / 丢失 / 符号链接 / 配额注入 | 需可信基线的预期摘要 | 随 corpus 提供基线摘要 |
| M0 / M1 版本跃迁与旧制品不变 | 需冻结的旧 M0 与旧 ZIP 基线 | 随 corpus 提供 |
| PDF | Worker 镜像缺 pandoc / typst / fc-list | 在受控构建中补齐并固定版本后重探 |
| 对象存储 | 无授权的独立测试 Bucket | 授权独立 Bucket / 凭据 / 前缀 |
| 浏览器 E2E | 宿主 AppArmor 限制非特权 userns | 在支持 user namespace 的宿主或受控 runner 上执行 |
| RA04 / RA05 / RA06 逐 Gate 定义 | 原始文档未给出逐 Gate 定义 | 提供原 Gate 原文定义 |
| 阶段级故障注入 | 未实现受控、可复核的注入点 | 实现最小故障注入工具并审查其目标与清理方式 |

## 9. 失败与修复清单

| 编号 | 现象 | 根因 | 修复 | 状态 |
|---|---|---|---|---|
| D1 | tmpfs 挂载路径非法 | YAML 流式序列把逗号当分隔符 | 标量加引号 | 已修并重跑通过 |
| D2 | 空库迁移失败 `mcp_versions does not exist` | ALTER 分支未依赖 CREATE 分支 | `c1d2e3f4b5a6.down_revision` 改为 `h6i7j8k9l1m3` | 已修并重跑通过（111 revision 到 head） |

两个修复当前仅存在于本次构建的镜像与工作树文件中，**尚未提交**。`deploy/acceptance/compose.yml` 与 `alembic/versions/c1d2e3f4b5a6_*.py` 在 git 中均为未跟踪状态。是否需要提交由负责人决定。

## 10. 范围边界与未主张事项

- 本次未触及生产 `.env`、生产数据库、生产凭据，未改变生产默认门禁，未修改旧 Manifest / ZIP。
- 对象存储状态单独列出为 BLOCKED，未以本地后端通过替代。
- 未把 PASS_STATIC、探针、空库迁移、SQL 并发或合成配置外推为真实业务通过。
- 本次**不构成 RI09.5 完整验收通过**。浏览器 E2E、PDF、对象存储、corpus 相关业务验收仍为 BLOCKED。

## 11. 证据索引

完整清单见 `evidence/runtime-acceptance/artifact-index.json`（69 个文件，含 SHA-256）。关键入口：

```
results.md                              本次逐项结果
ra01/attempt1-freshfail/FINDING-*.md    缺陷 D2 完整分析
ra01/attempt2-fixed/                    修复后迁移到 head
ra02/ra02-results.txt                   12 项约束断言
ra03/RA03-RESULT.md                     8 并发收敛为单 job
ra04/RA04-06-RESULT.md                  Celery 行为与定义缺口
report/versions.log                     PDF 前置缺失
chain/CHAIN-RESULT.md                   ZIP 生成与缺口
auth/AUTH-RESULT.md                     鉴权正负场景
browser/BLOCKED-reason.md               浏览器阻塞原因
rollback/                               门禁关闭与停止记录
```

原始证据保留于受控私有目录 `/home/zj/ri095-private/`（含凭据的私有 env 权限 600）。仓库内证据副本已剔除 JWT 与 API key 原文。

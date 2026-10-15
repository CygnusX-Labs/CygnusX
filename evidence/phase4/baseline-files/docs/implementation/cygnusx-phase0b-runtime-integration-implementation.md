# CygnusX BioOps Phase 0B Runtime Integration Implementation

审计日期：2026-10-14（Asia/Shanghai）。范围：本地源码、宿主机只读版本探针、隔离测试。
本报告不是生产部署证明，未进入 Phase 1。状态仅使用 PASS / FAIL / BLOCKED /
SKIPPED / NOT TESTED；证据层级为 Unit / Contract / Integration / Runtime Smoke / E2E。

## 1. Executive Summary

已实施最小修复、可重跑测试及版本清单，交付工作完成；运行验收未全部通过。
最终聚焦 pytest：**62 PASS、1 BLOCKED（pytest skipped）、5 SKIPPED（quarantine
过滤）**。独立 MCP unittest：**2 PASS、4 BLOCKED（unittest skipped）**。
合计已完成自动化用例：64 PASS、0 FAIL、5 BLOCKED；另有 5 项 quarantine 未执行。
此数量不包含工具链检查、手工启动探针和被中止的扩大回归。

主要成果：Redis 故障不再回退内存；确认 CAS 失败方不能执行；task 审批先原子占用再提交；
API-Key 提交/取消分析与提交下载不能省略人工凭证；最终路径和下载文件归属加固；
FastMCP 真实注册及进程内 Client 调用通过，修复 Seqout 导入 NameError；
HTTP/SSE 强制独立入站 token、非回环模式禁止、退出关闭 REST client。

关键发现：寻宝鼠默认镜像 tag 与构建源码不一致；宿主机实际下载程序为旧版 1.4.0；
Worker 挂载的 RNAFlow/ATACFlow 来源不同于主仓子模块。Docker、真实 Redis 与外部
MCP 传输无法完成验收。因此 **Phase 1 受控写工具接入：BLOCKED**。

## 2. Baseline & Git Status

读取了附件、`ARCHITECTURE_DESIGN/README.md`、MCP/Flow 权威文档及
`mcp-server/ARCHITECTURE.md`。Phase 0A 指定路径不存在，实际基线为
`docs/audits/cygnusx-phase0a-implementation-2026-10-13.md`；可行性基线为
`docs/audits/cygnusx-unified-research-agent-feasibility-audit-2026-10-13.md`。

执行 `git status --short`、`git diff --stat`、`git branch --show-current`、
`git rev-parse HEAD`、`git submodule status --recursive`、remote 查询。
主仓分支 `feat/reproducible-report-phase0`，HEAD
`c68ea9e0d6ecb63cb5678444ad3dd1e2a8a00407`，remote
`git@github.com:xsx123123/omichub.git`。工作树原本即脏，已有 Phase 0A、报告系统、
前端和子模块成果。未 reset/clean/checkout、未提交或推送、未改子模块内容。
已有报告模型、迁移和前端变更均不是本阶段实施成果。

完整仓库路径、branch、remote、HEAD、dirty_paths 见 Runtime Manifest。
HEAD + dirty=true 不构成可复现构建来源，本报告不以 HEAD 代替部署版本。

## 3. Repository / Image / Binary Version Matrix

| 对象 | 本地源码/配置 | 实际运行证据 | 状态/层级 |
|---|---|---|---|
| OmicHub | `c68ea9e0`，脏工作树 | 应用容器 SHA 未取得 | BLOCKED / Runtime Smoke |
| Treasure 子模块 | `88dae95e`，干净 | 镜像未知 | FAIL / Contract（与默认 tag 漂移） |
| Treasure 同级仓 | `1ea2f79c`，干净 | 不是 Compose 当前 build context | PASS / Contract（仅来源盘点） |
| EBIDownload 子模块 | `b351e03d`，源码 VERSION 1.4.0 | 宿主机输出 1.4.0，commit 绑定未知 | PASS / Runtime Smoke（仅宿主机） |
| 同级 EBIDownload/Polariseq | `a29971b0`，脏，VERSION 1.4.3 | 未执行或替换该版二进制 | NOT TESTED / Runtime Smoke |
| RNAFlow 子模块 | `19f5068c`，脏 | Worker 来源不应由该 SHA 推定 | BLOCKED / Runtime Smoke |
| ATACFlow 子模块 | `4a68b347`，脏 | 同上 | BLOCKED / Runtime Smoke |
| Worker 配置 RNAFlow | `/home/zj/pipeline/RNAFlow`，`b83c27d0`，脏 | snakefile 存在并计算摘要，容器未知 | PASS / Contract；BLOCKED / Runtime Smoke |
| Worker 配置 ATACFlow | `/home/zj/pipeline/ATACFlow`，`8a173fbb`，干净 | snakefile 存在并计算摘要，容器未知 | PASS / Contract；BLOCKED / Runtime Smoke |
| FlowFrame | `977ad657`，脏 | 不改子模块 | PASS / Contract（盘点） |
| bioreport 同级仓 | `cb2911a2`，脏 | 本阶段未改报告能力 | NOT TESTED / Runtime Smoke |

`../polariseq` 不存在，新 Polariseq 源码实际在 `../EBIDownload`。
`deploy/image-mapping.yaml` 当前有 17 个条目，不能照搬历史“14 镜像”说明。
主服务仍有 dev tag；image ID、digest、revision label 未取得，全部标为 Unknown/null。
未批量 retag 或升级镜像，以免违反镜像清单多处同步和既有部署约束。

## 4. Treasure Mouse Runtime Verification

两服务默认分别为 `cygnusx-treasure-mouse-{chat,web}:1ea2f79`，构建上下文却为
`pipelines/Treasure-Seeking_Mouse`（`88dae95e`）。**配置来源漂移 FAIL**。
实际 tag 可以被环境覆盖，本轮没有读取生产覆盖值，因此不把默认值视为部署值。

Dockerfile：`deploy/Dockerfile`，targets `chat` / `web`。chat 基于 Node 24 Alpine，
命令 `node server/local.mjs`，8787 仅 expose 到 app_net，named volume `/app/data`。
web 是 pnpm frozen-lockfile 构建后 nginx 1.27 Alpine 静态服务；构建参数
`VITE_CHAT_API=/treasure-mouse/chat-api`、`VITE_BASE_PATH=/treasure-mouse/`。
chat 健康检查为本地 `/stats`；web 等待 chat healthy。

平台 nginx 将 `/treasure-mouse` 重定向到带斜杠地址，代理 web 并剥掉前缀；
子服务 nginx `/chat-api` 代理 `chat:8787`，主 Compose 已声明 `chat` 网络 alias。
该路由静态闭合 PASS / Contract，实际健康检查、静态资源及 API 请求 BLOCKED。

`docker version` 因 Docker socket 操作不被允许失败，无法 inspect 镜像/容器。
未构建、重启、拉取或推送镜像。最小后续方案：选定干净来源，按镜像规范同步 tag，
记录构建时 SHA/time 与 digest，再从实际容器回读；不能只改 tag 掩盖漂移。

## 5. Polariseq / EBIDownload Runtime Verification

真实宿主机执行：`/data/omichub/bin/EBIDownload --version` 与 `download --help`。
文件存在且可执行，输出 **`ebidownload-cli 1.4.0`**。SHA-256：
`6628ad8fd489eee68b9ebd58299f32c021812b386435a82193911c4494e219c4`。
配置 YAML 存在并计算摘要，未读取/输出其内容。

路径来自 `get_download_config()`：tool YAML 明确 binaries 优先，其次由 Settings
STORAGE_PATH 派生，再由 Worker 的 Settings fallback 补空值。本机选中上述路径。
Worker 构造：`--yaml <config> --log-format json download -A <accession> -o <dir>
-d <method> -p <threads> -t <aws_threads> --progress-port <port>
--write-progress-key [--dry-run]`。旧版 download help 支持这些参数（包括其 Global Options
区段的 --yaml/--log-format），method 为 ftp/prefetch/aws/auto，不含 aspera。
Manifest 的 worker_required_flags 本轮全部为 true，仅证明参数出现在 help 中，
不是实际网络下载行为的验证。

新版源码 VERSION 1.4.3 保留这些 Worker 参数，但未执行新版程序，也未替换生产文件。
同版本号不足以证明二进制来自某个 commit。Worker 容器内的文件、可执行位、version、
digest 和开发/容器一致性均 **BLOCKED**，宿主机证据不得提升为容器证据。

| Accession | 证据与结论 |
|---|---|
| GSE / GSM | 两份 Rust 源码均未找到 GEO 展开路径；运行支持 NOT TESTED，不宣称可直接下载 |
| PRJNA / SRR | Contract：原样交给 ENA read_run filereport；实际元数据/下载 NOT TESTED |

没有数据源访问或下载；dry_run 仅是 Service 测试队列参数，并未启动 Rust 下载。
后续应显式选定兼容版本和摘要、经隔离测试与审批固定 Worker 产物，不直接替换现网二进制。

## 6. MCP Startup & Tool Registration

使用已有隔离 `mcp-server/.venv`：Python 3.13.12、FastMCP 3.4.4，与本地 uv.lock
锁定项一致；未升级依赖或改锁。尝试 frozen/offline 安装受到缓存写权限限制，复用现有环境。
主后端测试环境为 Python 3.11.14，不能把两个环境混为一谈。

发现 `tools/seqout.py` 在模块级使用未定义 `mcp` 的 decorators，导致真实导入 NameError。
移除这 26 个重复 decorators，保留既有 `register(mcp, api)` 和唯一 registry。
主入口实测注册 **71** 工具，与 tools.yaml 自校验一致，无工具集合差异；pipeline
入口实测 **10** 工具，Schema 可序列化，真实进程内 FastMCP Client 能发现全部工具。

真实 Client 验证 `confirmation_id` schema、布尔自证拒绝、缺参数 ToolError、
模拟下游 503 的结构化 success=false、lifespan 退出后 httpx client 已关闭。
独立 token verifier 拒绝伪造 token，合法隔离 token 仅返回固定本地 client identity；
旧非回环开关设为 true 仍不能绑定 0.0.0.0。

真实 STDIO 子进程已启动并输出注册日志，但 JSON-RPC initialize 未完成，超时后清理进程。
随后测试在受限 I/O 环境明确 skip。loopback bind 返回 Operation not permitted，
HTTP/SSE 外部测试也明确 skip。**启动/注册 PASS；外部 Transport 验收 BLOCKED**，
进程内 Client 不是 STDIO 或 HTTP 证明。未开放公共监听。

## 7. Authentication & Confirmation Integration Tests

`test_phase0b_http.py` 使用真实 FastAPI routes、ASGITransport 和真实 JWT 签名/校验，
secret 全为隔离常量。DB active-user 与 API-Key owner resolver 为 stubs；
因此 API-Key 存储查验和生产 middleware/RBAC 并未被运行验收覆盖。
身份链为 MCP 本地 caller token → 配置平台 API Key → 绑定 owner → 同 owner 人类 JWT
批准 → 参数哈希匹配的同 owner 执行。X-User-Id 不能改变绑定 owner。

| 场景 | 已执行结果 / 副作用 |
|---|---|
| API-Key 无凭证、仅布尔、不存在凭证 | 拒绝；business.submit 未调用 |
| PENDING、API-Key 自行审批 | 拒绝；business.submit 未调用 |
| 其他用户 JWT 审批、伪造 JWT/Header | 拒绝；business.submit 未调用 |
| APPROVED + 同参 + owner 相同 | 到达业务调用边界一次 |
| 篡改、过期、跨 owner、已消费 | 拒绝；无新增业务调用 |
| 同时消费两次 | 一次到达业务边界，另一次拒绝 |
| task 审批强制双读竞态 | 一次真实状态占用、一次 TaskService stub 调用 |

HTTP 正向测试用自定义 202 表示“已到达 stub 副作用边界”，**不是实际 Task Created**。
实际 TaskService 建立配置/样本表/任务对象及投队由 §9 单独验证，不能拼装称为 live E2E。
负向 HTTP 测试检查未调用业务；Service 负向测试进一步检查无 repo.save、队列、目录。
未消耗真实确认凭证，日志没有添加凭证原值或敏感 body。

## 8. Redis / Multi-worker Consistency

生产默认必须 `_RedisStore`；初始化、get/save/transition 中 RedisError/OSError/TimeoutError
统一返回 503 `CONFIRMATION_STORE_UNAVAILABLE`。无静默 `_MemoryStore` 回退；测试显式注入。
初始化失败不缓存假存储，恢复后可重新选择 Redis；已缓存连接故障也失败关闭。
Lua expected-status CAS 与 TTL 保留，新增 expires_at 检查，changed=false 不再被当成成功消费，
并修复 cjson 对象解码。task 审批 PENDING→SUBMITTING 抢占发生在业务调用之前。

Unit PASS：强制竞态、单消费者、布尔不能批准、已批准凭证过期、Redis 故障/恢复、CAS
失败方与对象解码。**真实 Redis Lua、多 Worker 进程、TTL/restart 验收 BLOCKED**。
本机未发现 redis-server；新增测试只会自行启动 port=0 的临时 Unix socket Redis、两独立
消费进程，绝不连接配置中的 Redis；缺二进制或 socket 权限时清楚 skip。

仍非跨 Redis/DB/queue 的 exactly-once：副作用已发生但状态写回失败，或提交中进程退出，
可留下 SUBMITTING/已执行待对账状态。采用拒绝重复执行、人工按 task_id 对账；
不能自动重新创建任务。TTL 到期仍可丢失确认事实，须按业务记录恢复而非重用凭证。

## 9. Analysis Task Submission Integration

真实 `TaskService` + `FlowService` + `FlowSubmissionValidator` + `GenericFlowBuilder`，
仅 repo/队列/目录登记为隔离 doubles，磁盘 YAML/CSV 落在 pytest tmp_path。
RNA 2.3.0、ATAC 0.1.0 合法输入创建 queued 任务对象、正确队列参数、owner 查询、
幂等键保留且重复提交仅投队一次；跨 owner 查询 NotFound。
两种 Flow 的非法 genome、输入路径、交付路径、空样本表和比较组均在 save/入队前拒绝。

修复最终提交的 SECTION 参数展平和 Schema 白名单（AI prepare 仍遵守 AI whitelist），
空/非对象样本行拒绝；path/FILE/path-widget 参数在最终提交解析到 owner 根目录，
禁止绝对外部路径、父目录和符号链接逃逸。TaskSubmitRequest model_copy 保留 idempotency_key。
Phase 0A 文件引用解析回归、Flow Schema 回归、内外 MCP 名称契约测试通过。
已有 AI prepare→确认→提交测试显式注入内存，验证真实服务组合但 TaskService.submit 为 stub。

Web/REST/MCP 均汇入最终 TaskService（Contract），隔离 service 测试证明最终门生效；
没有执行带真实上传文件的全入口 live E2E。数据库事务、真正 Celery delivery/status
reconcile、并发 idempotency DB 唯一性、真实 Worker 权限均未声称通过。

Worker 配置 shared_data_dir `/data/omichub`，pipeline_dir `/home/zj/pipeline`，在容器映射
到 `/opt/cygnusx/pipelines`（只读）；Snakefile 均存在且摘要入清单。Flow 使用 --use-conda。
宿主机 PATH 探针 Snakemake 9.19.0、Python 3.11.10、R 4.5.1，**不是 Worker 版本**。
Worker Python/R/Snakemake、参考挂载、Conda 实际环境、输出权限均 BLOCKED。

## 10. Download Service Integration

真实 DownloadService 在隔离存储创建合法 dry_run 任务、投 stub 队列、更新/查询状态和
owner；另一用户无法查任务。拒绝绝对路径、..、反斜杠及符号链接逃逸，且无 repo/queue 副作用。
不再把不安全路径静默 strip 成看似合法路径，目录创建前先确认解析结果属于 owner。

直接运行真实 `_register_downloaded_files`：临时 tiny FASTQ 正确登记 owner/storage_path/
logical Directory 并计配额；逃逸 symlink 跳过，跨 owner work_dir 拒绝，已有记录不重复登记。
session/repositories 是 doubles；文件扫描 to_thread 在测试中 inline，以避开 sandbox thread I/O。
实际 DB commit、运行中的 Rust Worker 和在线下载状态服务 NOT TESTED；未下载科研数据。

## 11. Deployment Configuration Changes

没有改 Compose、Dockerfile、镜像清单、生产密钥或卷。确定性修复集中在运行入口配置
校验、入站 auth、确认失败关闭与只读 preflight，未凭空挑选生产镜像或二进制新版本。
Compose main/worker 使用 /dev/null 和 synthetic 环境、`config --quiet --no-env-resolution`
均 PASS，仅为配置语法检查，不加载生产 env_file 内容，不表示依赖健康或容器启动通过。
源码声明有 PostgreSQL/Redis/Celery 依赖、存储 bind 和健康检查；真实依赖连通性 BLOCKED。

本轮修改文件索引（同文件可能包含原有 Phase 0A 改动，不能整文件回滚）：

- 后端：`api/deps.py`、`api/v1/{tasks,downloads}.py`、`core/exceptions.py`；
  `application/services/{tool_confirmation,task,download}_service.py`；
  `domain/flow/submission_validator.py`；`infrastructure/celery_app/tasks/download.py`。
- 外部 MCP：`core/{config,runtime}.py`、`{main,pipelines_main}.py`、`client/api_client.py`、
  `tools/{seqout,downloads}.py`。Seqout 仅修注册，未改查询逻辑。
- 测试：`tests/unit/test_phase0b_confirmation.py`、`tests/integration/test_phase0b_{http,services,redis}.py`、
  `mcp-server/tests/test_phase0b_runtime.py`；存量 `tests/unit/tools/test_{analysis_flow_tool,tool_bridge}.py`
  增加显式测试存储，避免 Redis 网络依赖。
- 治理：`scripts/audit_runtime_provenance.py`、本报告、Runtime Manifest、
  `ARCHITECTURE_DESIGN/CygnusX_mcp_architecture.md`、`mcp-server/{README,ARCHITECTURE}.md`。

所有 src 路径以上相对 `src/cygnusx/`。本轮没有新增平台数据库模型/迁移/前端业务。

## 12. Runtime Provenance Manifest

交付 `docs/audits/cygnusx-runtime-provenance-manifest.json`。结构化采集 repositories、
递归 submodules、Compose build context/mounts/healthcheck、image inventory、binary
摘要/help/version、worker paths、Flow 配置/Snakefile 摘要和宿主机版本。
expected_version、configured_version、observed_runtime_version、verification_status 分开；
未知字段为 null，容器未观察值不借用宿主机值。remote HTTP 凭据脱敏，不输出 Token/JWT/
真实 env 内容；二进制配置仅记录路径及摘要。

重跑：`.venv/bin/python scripts/audit_runtime_provenance.py --output
docs/audits/cygnusx-runtime-provenance-manifest.json --strict`。
本轮实际生成，退出 **2** 表示运行门禁未解决（预期失败关闭），普通采集退出 0。
这是保守审计/preflight，不是能自动授予部署许可的健康检查；即使 Docker 可用仍需独立
inspect/transport/Redis 证据，脚本不会自动部署、执行写任务或解除 blocker。

## 13. Tests Executed & Results

| 命令/用例 | 层级 | 实际结果 | 真实服务范围 |
|---|---|---|---|
| 最终 pytest（下方完整命令） | Unit / Contract / Integration | 62 PASS，1 BLOCKED，5 quarantine SKIPPED | 路由/JWT/应用服务真实，持久化与队列隔离 |
| MCP `.venv/bin/python tests/test_phase0b_runtime.py -v` | Integration / Runtime Smoke | 2 PASS，4 BLOCKED | FastMCP 进程内 Client 真实，外部传输未通过 |
| pipeline entry import + Client.list_tools | Integration | PASS：10 工具/schema | 无平台连接 |
| Python compileall（本轮范围及 mcp-server） | Contract | PASS，exit 0 | 不运行平台 |
| 聚焦 Ruff 新文件及安全/校验文件 | Contract | PASS，exit 0 | 不运行平台 |
| 其余 touched runtime 文件 Ruff --select I,F | Contract | PASS，exit 0 | 不运行平台 |
| 其余 touched runtime 文件全规则 Ruff | Contract | FAIL：存量 Seqout 风格、API client ASYNC109、下载 FTP B023 | 不扩大改动清理 |
| mypy 确认服务 + 最终校验器 --follow-imports=silent | Contract | PASS：2 files | 非全仓 strict gate |
| main/worker Compose synthetic config | Contract | PASS，exit 0 | 不访问 Docker daemon |
| Docker version/server attestation | Runtime Smoke | BLOCKED：socket 权限 | 未 inspect/运行容器 |
| git diff --check | Contract | PASS，exit 0 | 包含当前 tracked diff |
| binary --version / --help | Runtime Smoke | PASS：宿主机 1.4.0 | 无下载 |
| full ToolBridge 扩大回归 | Unit | BLOCKED：受限 I/O 下停滞，已中止并清理 | 只计最终完成子集 |
| live 平台/Worker/DB/Redis E2E | E2E | NOT TESTED / BLOCKED | 未接入生产 |

最终 pytest 命令（主仓已有 .venv）：

```bash
.venv/bin/pytest tests/unit/test_phase0b_confirmation.py \
  tests/unit/test_phase0a_security.py tests/unit/domain/test_flow_submission_validator.py \
  tests/integration/test_phase0b_http.py tests/integration/test_phase0b_services.py \
  tests/integration/test_phase0b_redis.py tests/unit/test_mcp_dual_surface_parity.py \
  tests/unit/test_download_service.py tests/unit/tools/test_analysis_flow_tool.py \
  tests/unit/tools/test_tool_bridge.py::test_requires_confirm_returns_confirm_card \
  -q -m 'not quarantine'
```

Ruff PASS 范围：新增 script/test 文件、MCP runtime、后端 deps/tasks/downloads endpoints/
exceptions/confirmation service/validator。其余文件只做 I/F 范围修复；全规则 FAIL 未隐藏。
compileall 已覆盖修改的后端服务/路由/validator/worker、script/tests 和 mcp-server。
全仓 mypy、全量 CI、真实 integration/前端构建未运行；本轮未提交，不声明全量门禁通过。
pytest 有既有 Pydantic class Config deprecation warning。扩大测试首次在默认确认存储处
停滞后中止，改为显式隔离存储；之后全 ToolBridge 又在受限 I/O 处中止，最终安全子集通过。

## 14. Remaining Risks & Blockers

| 优先级 | 状态 | 问题 | 解除条件 |
|---|---|---|---|
| P0 | BLOCKED | 无真实 Redis 多进程 Lua/TTL/restart 验收 | 在隔离 Redis 运行新增双进程用例和重启/故障恢复测试 |
| P0 | BLOCKED | STDIO initialize 超时、回环 HTTP/SSE socket 禁止 | 非受限隔离机器运行真实 Client，验证 401/合法调用/停止清理 |
| P0 | FAIL | Treasure 默认 tag/build source 漂移 | 干净来源重建审批、tag/SHA/digest/运行 label 一致 |
| P0 | BLOCKED | Worker 实际二进制、流程来源及共享路径未知 | 从实际 Worker 回读摘要/version，核查挂载/权限/refs |
| P1 | BLOCKED | Redis/DB/queue 非同一事务 | 明确人工对账 runbook，后续设计 outbox/幂等治理需另行授权 |
| P1 | NOT TESTED | API-Key DB 查验与完整 middleware/live owner 链 | 非生产隔离 DB + 全栈联合验收 |
| P1 | NOT TESTED | GSE/GSM GEO 展开、真实 PRJNA/SRR metadata | 后续 Adapter 范围评审，不能声称现下载程序已支持 |
| P1 | FAIL | 存量 Ruff 全规则不绿 | 独立维护范围处理；本阶段未无关重构 |

本阶段仅加固列出的提交/取消/下载及 MCP 写入口，未声称审计完所有 REST 写端点（例如
任务删除、沙箱策略等仍需独立权限评审）。现有 JWT 人类 Web 表单无 MCP 凭证仍兼容。
确认存储现在严格依赖 Redis，部署前必须落实可用性；这是有意的安全行为变化，不能以
恢复内存回退解决可用性。改用独立 MCP HTTP token 也要求客户端配置同步。

## 15. Rollback Strategy

未部署、未迁移、未改卷/生产二进制，因此无需线上数据回滚。当前工作区混有原有成果，
不得 git checkout/reset 整文件；如撤销只能按本轮 diff hunks 逐项审核还原，新增文件另行处理。
代码发布前应先在独立环境验证，按仓库镜像同步流程发布已知 SHA/digest；出现问题优先
禁用受控写入口，保留只读能力、Redis 记录及审计/任务事实。不能回滚成布尔批准或内存
回退，不应重放不确定是否已执行的请求。
任务副作用已经发生时按 owner/task_id/queue 记录对账；保留 SUBMITTING 状态，人工判定，
不得自动重复创建。版本探针和测试无业务副作用，所有测试子进程已结束/清理。

## 16. Phase 1 Readiness Decision

| 准入项目 | 状态与边界 |
|---|---|
| 平台认证边界可信 | PASS / Integration（JWT/routes）；完整部署链 NOT TESTED |
| MCP 运行可用 | PASS / 进程内；外部传输 BLOCKED |
| 工具确认不可绕过 | PASS / Unit+Integration；跨进程共享验收 BLOCKED |
| 分析最终提交校验一致 | PASS / Contract+隔离 Service；live E2E NOT TESTED |
| 用户文件路径隔离有效 | PASS / 隔离路径/归属；Worker 真实挂载 BLOCKED |
| 运行版本可追溯 | 宿主机 PASS；镜像/Worker BLOCKED；Treasure 配置漂移 FAIL |
| Agent 工具调用可审计 | 已有 task_id/error_code 链复用；live 审计落库 NOT TESTED |
| 下载与分析基础能力可用 | PASS / 隔离服务模拟；真实 Worker BLOCKED |

**最终决定：BLOCKED。当前不适合开放寻宝鼠受控工具执行。** 必须先完成 Redis 双进程、
真实 MCP 传输、镜像来源/digest 与 Worker 版本/挂载核验，再做非生产全栈 owner/审批/
任务/审计闭环验收。只读方案研究不等于批准 Phase 1 实施；本轮到此停止，等待后续指令。

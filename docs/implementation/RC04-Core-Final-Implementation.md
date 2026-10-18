# RI09.5 RC04-Core 最终实施记录

日期：2026-10-18（Asia/Shanghai）  
状态：**未签收；准备阶段和可离线工作已完成，真实运行验收被环境阻断。**

## 结论

本轮未达到 `RC04-Core Accepted`。当前主仓 `HEAD=621bf678c58eae1e527d6dc5a105c561a4655130`，分支 `main`；工作树有 36 条状态记录，暂存区为空。Docker socket `/var/run/docker.sock` 存在但属于 `nobody:nogroup`、权限 `srw-rw----`；`docker info` 返回 operation not permitted。当前没有可用的验收 env 文件，Compose `ps` 在配置解析阶段因缺 `ACCEPTANCE_APP_IMAGE` 失败。因此数据库/Redis/卷/持久 flags/进程均不能现场确认，不能执行安全关闭、PG、Browser、FI、Docker build 或报告交付运行。

未发现仓库内同名 `RI095-RC04-Release-Candidate-Evidence-Closure-Plan.md`。FI 阶段和操作约束按 [RI095 Runtime E2E Acceptance Plan](../info/26.10.17/RI095-Runtime-E2E-Acceptance-Plan.md) 与 [RI095 Final Runtime Acceptance](../info/26.10.17/RI095-Final-Runtime-Acceptance.md) 的原文核查；原文明确 RA04/05/06 的逐项定义待核对，且精准阶段注入器尚缺。

## D1–D4 当前源码检查

| 缺陷 | 当前 HEAD 证据 | 本轮检查 | 结论 |
|---|---|---|---|
| D1 tmpfs YAML | `deploy/acceptance/compose.yml` 的三个服务使用完整单一字符串 `"/tmp:uid=10001,gid=10001,mode=1777"`；`control.py:validate` 拒绝拆分格式 | `deploy/acceptance/run-checks.sh` 内离线检查拆分负例通过 | `PASS_STATIC`；未启动容器 |
| D2 Alembic 顺序 | `alembic/versions/c1d2e3f4b5a6_add_contract_digest_to_mcp_versions.py` 的 `down_revision="h6i7j8k9l1m3"` | 迁移链离线门禁历史有记录；本轮未连接/迁移数据库 | `PASS_STATIC`；当前数据库应用状态未知 |
| D3 PDF cwd/TMPDIR | `report_audit_pdf_renderer.py` 给 Pandoc 设 `HOME/TMPDIR=temp` 且 `cwd=temp` | 当前源码静态确认；不等于当前 Worker 镜像运行 | `PASS_STATIC` |
| D4 request_key | HEAD `621bf678` 包含 `ProjectResearchDelivery.vue:create()` 空 `requestKey` fallback 和共用 `generateId()`；prepare 后生成幂等键 | 当前前端文件无工作树差异；全量 Vitest 88 files / 597 tests 通过，`vue-tsc --noEmit` 通过，生产 build 通过，均使用已安装依赖 | `PASS_ISOLATED`；历史 PG/Browser 有旧源码运行，当前 HEAD 未重新运行 |

## 本轮最小修复

恢复 RA02 遗漏的正向断言：`deploy/acceptance/ra02_runner.py` 追加 `12_legal_attempt_count_update`，把已 seed 的 `project_report_jobs.attempt_count` 从 0 更新到 1，预期 SQLSTATE `00000`。该用例直接对应早期真实运行记录中的 RA02_12；之后期 runner 的 11 项中缺失。Ruff check、format、`py_compile` 和 diff whitespace 静态检查通过。没有 `RA02_DSN` 或授权 PG，故该断言尚未执行，状态仅为 `PASS_STATIC`。

没有改动生产配置、运行门禁、数据库迁移状态、容器或历史证据。当前工作树已有的前端、G3 admission、FlowFrame/RNAFlow/Treasure Mouse/tools 等 dirty 内容未被覆盖或整理。

## 离线验证

| 检查 | 结果 | 范围 |
|---|---|---|
| `ruff check deploy/acceptance` | PASS_STATIC | 验收目录 |
| `ruff format --check deploy/acceptance` | PASS_STATIC | 验收目录 |
| `python deploy/acceptance/checks.py` | PASS_STATIC | Compose 保护负例及合成 Worker 注册表；脚本明确 runtime NOT_RUN |
| `node --check deploy/acceptance/browser-preflight.cjs` | PASS_STATIC | 语法，不是浏览器执行 |
| `npx vitest run` | 597 passed / 88 files | 当前 frontend 源文件与 HEAD 一致；使用已有 node_modules |
| `npm run type-check` | PASS | 当前 frontend 源文件与 HEAD 一致；使用已有 node_modules |
| `npm run build` | PASS | 当前 frontend 源文件与 HEAD 一致；使用已有 node_modules；无 Docker image build |
| clean `npm ci` | BLOCKED | `/tmp` 中从 HEAD 导出的前端快照安装依赖时 registry `registry.npmmirror.com` DNS 返回 `EAI_AGAIN`；未改 package-lock |
| Docker / PostgreSQL / Redis / Worker / Browser | BLOCKED / NOT_RUN | Docker socket 拒绝；没有隔离 env |
| Docker build / image digest | NOT_RUN | 尚无获确认冻结源快照；无 image digest |

## 候选冻结范围（等待负责人确认）

拟以主仓 `621bf678c58eae1e527d6dc5a105c561a4655130` 和下列递归 Gitlink pins 创建独立、干净 RC 源码快照；子仓本地 dirty 内容不纳入。该基线含有兼容旧浏览器的 `generateId()` 提交（8 个 frontend 文件）。提议的新增源码差异仅为 `deploy/acceptance/ra02_runner.py` 的第 12 项断言；四份指定交付物及两份脱敏历史日志作为验收结果证据，不纳入运行镜像源码。当前没有创建候选快照、提交、tag 或镜像。

| 子模块 | Pin |
|---|---|
| `Protocol/FlowFrame` | `977ad657bbe7d49f2200a5f3f550b70f25234f3d` |
| `pipelines/ATACFlow` | `4a68b347ba3b9497a86eed2603b6577afc3c2f27` |
| `pipelines/ATACFlow/container_env` | `a41746e5712ea5898e2bf599356d86d5ed4e2711` |
| `pipelines/ATACFlow/report` | `4b9f6254d7f967cb9d35391a92b684cb2b113ac1` |
| `pipelines/ATACFlow/src` | `80e8ded2f958f2e26a8ada3587dffc0c8b54912f` |
| `pipelines/EBIDownload` | `b351e03dfc845d229102d90f9bd88d6ca731f0de` |
| `pipelines/RNAFlow` | `19f5068c4f9370ea27cb6fe554a3f061a1b62a51` |
| `pipelines/RNAFlow/report` | `c4a0cae8e129918ccfbd4e031da808b85abffbb4` |
| `pipelines/RNAFlow/src` | `f973d5f86de11a0efa156b7ecd2aa6b02c7ee17f` |
| `pipelines/Treasure-Seeking_Mouse` | `88dae95e7294dea5004330203f56e4211776fd74` |
| `pipelines/scrna` | `b5066338fba47b1ed3fbee042f1cb43859cff882` |
| `pipelines/tools` | `24ecb6ce75657c5ce188603b54ac7bf10ffb6d46` |

> 其他工作树与子模块 dirty 内容均排除；recursive Gitlink pins以本表为准，不包含子模块工作树差异。

## Required next step

The owner must confirm the proposed clean HEAD + Gitlink snapshot and RA02 runner change, or name a different file scope. After that confirmation, create the isolated snapshot and run the current-source checks. RC04 remains unaccepted until environment access is provided and RC04-00 through RC04-04 are executed with linked source SHA, image digest, Run ID and output evidence. See [Gate Results](RC04-Core-Gate-Results.md), [Evidence Index](../../evidence/rc04-core/RC04-Core-Evidence-Index.json), and [Remaining Blockers](RC04-Core-Remaining-Blockers.md).

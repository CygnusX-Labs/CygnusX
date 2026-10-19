# IAT-R3 Research Workflow Closure

本轮状态：SOURCE / ISOLATION 增量完成，真实运行与浏览器验收 **BLOCKED**。未签发 R3_READ_PREPARE_PASS_RUNTIME 或 R3_PRODUCT_PASS_E2E。未启动服务、访问生产、执行外部元数据请求、下载或 Agent 写任务；门禁未改动，未提交或推送。

## 基线与文件所有权

依据资料包 `02_IATR3_Implementation.md`、对应 Prompt、活动架构 `CygnusX_agent_tool_gateway.md` / `CygnusX_treasure_mouse_architecture.md` 和 2026-10-18 audit 逐项核对。实测基线主仓 HEAD 为 `e78fd1efa1df3ebfcb098be973e81e193b1db224`；早先审计 SHA 不代表本次源码。完整主仓状态、递归子模块 SHA/dirty、diff SHA、核心源码与锁文件 SHA 见 `evidence/iat-r3-runtime/baseline.json`。共享树仍在演进，验收必须重新冻结镜像和源码指纹。

本轮前端增量修改 `frontend/src/components/research/adapters/useResearchWorkflow.ts` 及原 `researchWorkflow.test.ts`；后续补充了 `research_treasure_service.py` 的跨进程取消信号持久化及对应隔离回归。未修改 Node 子仓、共享 Task/Download/DatasetImport/Admission。

后续静态安全检查发现 BFF 到 Node 的详情与 SSE 请求使用 HTTPX 默认环境继承，会读取宿主代理变量。两个请求客户端现显式设置 `trust_env=False`，避免服务凭据和研究载荷被环境代理改道；SQLite/MockTransport 回归验证两条路径均不继承代理配置。该隔离验证不改变下方 Runtime 验收状态。

## 实际缺口与修复

原 adapter 在目录刷新失败后只清空 permissions/proposals/tasks/assets/datasets，旧 sources、候选 files、samples、relations、reports、workflows 与 accession/hash 仍能留在显示树；成功刷新返回更少 scope 时也保留历史投影。现改为清空全部科研投影及关联版本映射，并保留可见错误。成功但缩减工具目录也先失效历史数据，再投影当前权限。每次动作仍走原 catalog/Gateway、generation 与 session/project 校验；没有新增业务接口或执行路径。

回归断言覆盖权限拒绝后所有科研字段清空、成功返回空目录后旧报告与来源清空、迟到跨项目响应拒绝、合法 prepare 不自动批准/提交以及 transport executionAllowed 永为 false。

委托控制面新增 JWT claim 类型校验：`sub/session_id/jti` 必须为非空字符串，`project_id` 必须为空或 UUID 字符串，`scopes` 必须为非空字符串列表，`token_version` 必须为非负整数；签名有效但 claims 形状异常的令牌在进入 Gateway/Redis 防重放前即拒绝。4 个 malformed-claim 回归与原 delegation 套件通过，仍属于离线 SQL/Redis double 证据。

## 本轮隔离验证

命令、工作目录、退出码及原始日志见 `evidence/iat-r3-runtime/commands.json`。

- `npx vitest run src/components/research`：9 文件、51 项通过。
- `npx vue-tsc --noEmit`：最终结果见 commands.json；首次检查发现 optional allowedTools，已修正并重跑。
- `cd frontend && npm run type-check`：通过；`npm test -- --run`：90 文件、611 项通过；
  `npm run build`：通过（含 `vue-tsc -b` 与 Vite production build）。这些是源码/构建门禁，
  不提升 RA08–RA13 的真实 Chromium 或服务运行状态。
- `node --test functions/seqout-chat/tests/platform-tools.test.ts`：退出码 0，Node runner 报告一个测试文件通过；不将其冒充真实 HTTP 或完整 Node chat 轮次。测试以替换 fetch 验证固定 callback、redirect:error、凭据不进 schema、危险工具剔除与失败不重试。

未启动监听 API/Node、PG/Redis 或 Chromium，未构建运行镜像。已有源码接线：Node index.ts 经 platformToolAdapter 注入工具和正式模型 loop。取消请求现在在无本地 producer 时写入现有 streaming assistant message 的 metadata，producer 每个事件周期重读该标记并发布终止事件；这闭合了跨 web 进程的取消信号传递，但不等于跨进程重启接管或 OS 级停止。取消 API 的 `accepted` 只代表信号已记录，仍不代表任务已经终止；无 streaming generation 时返回 `unknown`。搜索优化的 Redis 可选缓存现在在主机解析失败时先进入 30 秒熔断，避免异步连接取消遗留事件循环任务并回退进程内缓存；这只改善离线可用性，不构成 Redis 运行验收。源码接线不计运行通过。

## RA01–RA14 验收矩阵

逐项状态 CSV 见 `evidence/iat-r3-runtime/acceptance.csv`，均为 **BLOCKED**：RA01 Legacy、RA02 LangGraph、RA03 Node 原聊天、RA04 Node 隔离、RA05 metadata、RA06 assets/FileRegistry、RA07 合法持久 prepare、RA08 React 实际 mount、RA09 cards/digest、RA10 撤权、RA11 SSE 断流重连、RA12 待人审且零下载、RA13 faults/i18n/widths、RA14 restart。共同缺少本轮明确授权的独立非生产环境。RA10/RA11/RA12 有本轮前端隔离支撑，不能升级为 PASS_RUNTIME/PASS_E2E。RA14 的取消信号传递已有源码隔离回归，但跨进程重启恢复仍未验。

旧 120 Test IDs 维持原审计统计，不与本轮 51 个 Vitest 断言相加。原弱断言纠偏仍成立：AG14 的 Python URLError 不等于 Node 网络故障；AG15 空列表类型断言不等于 200 版本上界；BR04 的 401 不等于合法 Prepare，BR06 重复首页不等于跨项目迟到帧，BR08 首页刷新不等于 cursor 恢复；本轮没有伪造这些运行通过。RA14 的取消信号传递现有 `tests/unit/test_treasure_native_access.py` 隔离回归，但跨进程重启恢复仍未验。

## 后续 Runtime Artifact 对账

共享工作树随后出现 `evidence/runtime-acceptance/P0A-IATR3-G3E2-Runtime-Acceptance.md` 与 `20261018-local/`。该报告记录 disposable PostgreSQL/Redis 已启动并停止，但 app/frontend 使用 `d9c92cf6ee1c` 镜像，和其记录的源码 HEAD `54718c476816c0045e433d45148c0140784ebbce` 不同；迁移在镜像提供的 `a5b6c7d8e9f0 -> c1d2e3f4b5a6` 路径因缺 `mcp_versions` 失败，故 API、Node、Chromium 业务链未启动。它是后续失败尝试，不改变本报告所述 IAT-R3 的 BLOCKED 结论。

当前 checkout 的 `c1d2e3f4b5a6` 明确以 `h6i7j8k9l1m3` 为前驱，后者创建 `mcp_versions`；当前静态迁移图通过 `scripts/check_migrations.py` 且单 head。结合镜像 tag/source SHA 不同，现有日志只能说明旧镜像的迁移路径失败，不能证明当前 checkout 的该迁移有缺表缺陷。升级当前源码镜像并重新验迁移仍未完成。

该 Runtime artifact 的 `SHA256SUMS` 曾有一条旧的重复 summary hash 未匹配；修正 P0-A 汇总后已同步两条 hash，`sha256sum -c` 当前全部通过。P0-A 汇总现已按原始 `p0a-isolated.log` 修正为 82 项；未来重建镜像时仍需重新冻结整套 manifest，不影响其明确的 IAT/G3 `BLOCKED` 与总 `NO-GO` 结论。

## 运行准入与回滚

资料包要求明确的非生产 role/db、Redis namespace、API/Node 端口、测试账号/项目、存储与清理权限，并禁止继承旧授权；本轮未得到这些资源授权。后续须先冻结本次源码和镜像，再用正式 ProviderManager、agent_templates、Gateway audit/nonce、真实 FileRegistry SHA、合法 proposal 与零新增下载 Task、Chromium mount/HAR/截图关联同一请求身份。不得仅使用现有单元日志签发准入。

源码回滚仅逆向本轮 adapter/test hunks，保留其他共享 dirty 和历史事实，不 reset/clean。没有运行服务或创建测试数据库，因此无容器或数据清理动作；证据保留。下载、人类执行、Agent write 与 worker_paths_verified 门禁保持原 false/未认证。

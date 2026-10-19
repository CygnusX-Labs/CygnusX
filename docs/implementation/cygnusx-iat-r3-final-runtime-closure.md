# IAT-R3 Agent Research Workflow Runtime Closure

交付日期：2026-10-20（测试于 2026-10-19 夜间开始）。

**最终状态：S5-C2 BLOCKED；当前源码的定向隔离回归与前端构建通过，真实运行闭环及科研业务 E2E 未获验收。** 本报告不是 READ_PREPARE_PASS_RUNTIME 或 PRODUCT_PASS_E2E。未采用其他日期、其他源码版本的运行记录替代本轮证据。

## 本轮完成与代码核实

复核了现有 Treasure-Seeking_Mouse、platform-tools、React Presentation、Vue TreasureResearchWorkbench、AgentToolGateway、DatasetImportService 及 Legacy/LangGraph 工具循环，沿用已有实现。本轮没有另建聊天系统。

发现并修复了一个实际构建断点：子仓已将平台 Island 配置和适配器移入 `archive/island/`，父仓构建脚本仍调用已不存在的根配置。`frontend/scripts/build-treasure-island.mjs` 现在优先兼容根配置；缺失时在临时目录组合归档适配器和当前共享组件，复用子仓已安装依赖执行 Island TypeScript 检查与 Vite 构建，随后清理临时目录。公开产物仍移除包含本地路径的模块清单。

这次修改没有改动子仓或归档代码、依赖锁文件、Agent 配置及下载开关；子仓内部工作区检查为空。父仓原有大量未提交改动和子模块指针保留。同步更新唯一架构权威文档 `ARCHITECTURE_DESIGN/CygnusX_treasure_mouse_architecture.md` 的 D4 构建说明。

| 已有能力 | 本轮核实结果与边界 |
|---|---|
| Node → platform-tools → FastAPI Gateway | 现有适配器使用受信任委派上下文与固定回调入口；本轮 Node 隔离测试通过，未实际监听服务并跨进程调用 |
| Gateway 权限重验 | 代码会重新读取用户、会话、项目与权限，校验委派 token 版本和 scopes；隔离测试覆盖，不等于真实 PostgreSQL 撤权实验 |
| Redis 防重放 | 现有调用以 Redis NX/TTL 登记调用身份，异常拒绝；本轮使用替身，未取得真实 Redis 记录 |
| Legacy/LangGraph 工具循环 | 确定性 Provider 的共享工具轮次测试通过，包含结果回灌与 ASGI SSE；Agent Template 和请求装配存在测试替身，未验证持久化合法模板的真实 PostgreSQL 全链路 |
| GEO → DatasetCard → inspect → Import Prepare | 存在发现、卡片、候选校验和准备服务；分段隔离测试通过，尚未将整个科研业务链在真实服务中串联验收 |
| 人工审批等待 | 准备逻辑生成 PREPARED 状态和待确认凭证，`runtime_verified=False`，不等于已执行下载；本轮没有真实数据库准备记录 |
| React 展示与 Vue 嵌入 | Island 类型检查、Vite 产物及 Vue 构建命令通过；卡片、Literature、ToolTrace、Grounding、Prepare、上下文和恢复仍需真实浏览器确认 |
| SSE/恢复 | 现有解析、重放与持久化相关隔离测试通过；未验证实际代理网络断流、刷新及进程重启恢复 |

确定性 Provider 的结果仅支持其覆盖范围内的编排和调用正确性，不构成外部模型推理质量认证。相关测试的共享工具轮次不能单独证明 GEO 科研链路已通过。

## 本轮证据

证据目录：[`evidence/iat-r3-final-20261019/`](../../evidence/iat-r3-final-20261019/)。所有测试命令、工作目录、退出码见 [`commands.json`](../../evidence/iat-r3-final-20261019/commands.json)，原始输出按同名 `.log` 保存；浏览器启动命令另见 `chromium-preflight.command.json`。

| 检查 | 结果 | 证据 |
|---|---|---|
| 后端 7 个定向单测文件 | 135 passed，退出码 0 | `backend-isolated.log` |
| 子仓 `npm test` | 16 个 Node 测试文件子测试通过，退出码 0 | `node-isolated.log` |
| 子仓 `npm run typecheck` | 退出码 0 | `react-typecheck.log` |
| 前端 research 定向 Vitest | 9 个文件、53 项通过，退出码 0 | `frontend-isolated.log` |
| 前端 `npm run build` | prebuild Island 类型检查/Vite 及主构建命令退出码 0 | `frontend-build.log` |
| 真实 Chromium 启动预检 | 退出码 1；业务 E2E 未开始 | `chromium-preflight.log`、`chromium-preflight.json` |

前端测试命令额外传入的 `src/utils/__tests__/researchAgentSse.test.ts` 路径不存在；实际通过的 9 个文件来自 research 目录，不将不存在的文件算作执行记录。没有运行提交前全量门禁，也没有提交或推送。本轮仅完成上述定向验证；Island 大 bundle 的 Vite 警告仍存在。

源码摘要：`5452ec298846cd4fa0e4a0a93ba8348124e93ee3f84e2078085a3f7240a25247`。`source-manifest.json` 记录 2175 个文件的 SHA-256，覆盖后端源码、前端源码/脚本、单测、子仓受版本管理文件及指定锁文件/架构说明；不是整个仓库的摘要。算法、父子仓 HEAD、构建产物摘要、开关值见 [`source-and-environment.json`](../../evidence/iat-r3-final-20261019/source-and-environment.json)。该摘要对应测试后的 dirty worktree，不以 HEAD 代替未提交代码。`worktree-status.txt` 保存工作区快照，`build-script.patch` 保存本轮脚本补丁。

## 真实运行与浏览器验收缺口

当前沙箱连 `127.0.0.1` 的临时端口监听也被拒绝，返回 `Operation not permitted`，因此无法在这里启动完整 Node/FastAPI HTTP 服务。初次检查时没有收到专用非生产连接。后续发现 `20261019-235848-bootstrap` 隔离 Compose 的新增启动记录（退出码 0）及其私有配置文件位置；这修正了“完全没有环境配置”的判断。但当前会话对该项目执行只读 `docker ps` 仍因 Docker socket 的 `operation not permitted` 失败，无法确认容器存活、服务健康或使用其 PostgreSQL/Redis。未使用生产环境或读取、输出私有凭据；本轮没有重复 G3 Linux 执行器调查。

已实际调用缓存 Chromium 可执行文件进行启动预检；浏览器在 crashpad socket 的 `setsockopt` 操作被拒绝后以 SIGTRAP 退出。完整错误保存在预检日志。这不是页面访问结果，也没有首页截图冒充业务验收。 新增 Compose 启动记录不能证明当前服务可用，且尚未证明其包含 Node Research Runtime；只读核实失败的命令与状态见 `evidence/iat-r3-final-20261019/compose-followup.json`。没有将启动命令成功计为科研链路通过。

| 科研业务 E2E 项目 | 本轮结果 |
|---|---|
| 用户登录 | NOT_RUN / BLOCKED |
| GEO 数据集发现 | NOT_RUN / BLOCKED |
| DatasetCard 展示 | NOT_RUN / BLOCKED |
| 文件候选查看 | NOT_RUN / BLOCKED |
| 来源证据展示 | NOT_RUN / BLOCKED |
| 独立合法数据的 Import Prepare → 人工审批等待 | NOT_RUN / BLOCKED |
| 项目隔离 | NOT_RUN / BLOCKED |
| 用户撤权后拒绝调用 | NOT_RUN / BLOCKED |
| SSE 断流恢复 | NOT_RUN / BLOCKED |
| 页面刷新恢复 | NOT_RUN / BLOCKED |

本轮真实 PostgreSQL 记录、Gateway Audit、Redis 消费记录、业务截图和 Network HAR **均未生成**；证据元数据明确记为 null 或空列表。独立业务数据尚未在真实环境准备。隔离测试、SQLite/Redis 替身和 ASGI 内存调用不计入这些验收项。

要解除阻塞，仍需在授权非生产环境以当前源码启动 Node/FastAPI/PostgreSQL/Redis，登记合法模板与独立测试身份/项目，运行两类 Runtime 完整轮次及科研发现/准备链，再执行表中 Chromium 用例，并补齐数据库、审计、截图、HAR 与对应源码摘要。未执行任何真实下载。

## 安全状态与回滚

静态读取源码确认：

```text
DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED = False
WRITE_RUNTIME_ACCEPTED = False
```

未开放 Agent 自动下载，没有生产环境写入或数据库迁移。本轮没有提升 S5-C2、下载执行器、写操作或视觉发布的验收状态。

回滚只需反向应用 `build-script.patch` 中的构建脚本修改，并撤回架构文档 D4 中本轮新增的归档构建说明；重新构建前端即可替换生成的 Island 产物。最终报告和本轮证据可保留用于追溯。不得整仓 reset，也不得整体还原已有修改的架构文档或子模块指针。本轮没有数据库变更需要回滚。

按任务要求，在交付此报告后停止；真实运行验收缺口保持显式阻塞。

# Treasure Native P0：访问边界与统一入口

状态：代码与隔离验证完成，G-P0 审查为 CONDITIONAL；全仓门禁未绿、现场归因尚未确认，不可发布为 READY。P0 依赖工作未放开；后续仅推进任务书允许的完全隔离 UI PoC，见 `treasure-react-island-poc.md`。

## 基线与变更范围

基线 HEAD `51011118535f782f5282f638b4a54649c79bf6d6`，工作分支 `feat/research-agent-phase5`。工作区原有大量 Phase5 与子模块未提交改动；本次未提交、未推送、未部署、未修改子模块或依赖锁文件。原始相关文件、hash 与 Git 状态见 `evidence/treasure-native/baseline/manifest.json`。前序调查见 `docs/audits/cygnusx-treasure-mouse-ui-regression-and-mcp-integration-audit-2026-10-15.md`。

| 文件 | 本次增量 |
|---|---|
| `frontend/src/views/TreasureMouseView.vue` | 单原生入口，移除 iframe/双模式 |
| `frontend/src/views/TreasureResearchWorkbench.vue` | capability 首屏预检、中文状态、撤权刷新、请求代际隔离、停止接收说明 |
| `frontend/src/api/researchAgent.ts` | 能力 DTO、预检 API、安全错误映射 |
| `src/cygnusx/api/v1/research_agent.py` | capability 读取真实用户；业务授权、SSE 开始前校验 owner 与 provider |
| `src/cygnusx/application/services/research_treasure_service.py` | active/模块校验；能力快照；项目错误码；修正不存在的 DTO 转换调用和消息必填 content_type；隐藏异常细节 |
| `src/cygnusx/application/schemas/research_agent.py` | 细粒度 capability 与恒 false 写执行字段；修正默认值类型 |
| `deploy/docker/nginx/nginx{,.prod}.conf` | 关闭旧公开子应用路径，内网 Node 不变 |
| `tests/unit/test_treasure_native_access.py` | JWT+ASGI+隔离 SQLite 权限与流式落库回归 |
| `frontend/src/components/research/__tests__/Treasure*.test.ts` | 原生入口、首屏预检、撤权与会话隔离回归 |
| `docs/adr/treasure-native-entry-and-capabilities.md` | 入口选择、能力契约与回退 |
| `ARCHITECTURE_DESIGN/CygnusX_frontend.md` | 回写当前入口与请求顺序 |

## 403 证据分级与请求路由

**现场故障仍为 Suspected**：没有取得原报错浏览器的 Network、真实后端 build SHA、实际运行配置或 image digest，不将单测复现冒充事故根因。

隔离 Verified：关闭 `treasure_native_ui_enabled` 时业务路由返回 `403 FEATURE_DISABLED`；模块撤销时返回 `403 MODULE_LOCKED`（即便 native 同时关闭也优先按模块拒绝）；非 owner 项目 `403 PROJECT_FORBIDDEN`；非 owner 会话 404；JWT 缺失、失效、版本错误或 inactive 401；非法 UUID 422；无可用 provider 503。SSE 内 Node 错误属于流事件，不能等同 HTTP 403。

新首屏顺序经 DOM 测试的调用序号验证：

1. `GET /api/v1/research-agent/capabilities`。
2. 仅 `read_sessions=true` 后请求 `GET /api/v1/projects`（projects API 的分页实现沿用平台）。
3. `GET /api/v1/research-agent/sessions`，再恢复当前会话 messages。
4. 用户发送后 `POST /api/v1/research-agent/sessions/{id}/messages:stream`。

native=false 时不请求 projects/sessions，显示入口未启用；preflight 请求失败显示会话“未加载”，不显示“暂无”。无 token 日志。Axios 统一 baseURL `/api/v1`，fetch SSE 使用相同前缀。开发 Vite 的 `/api` 仍转发 :8888；旧 `/treasure-mouse/` 代理仍可抵达 Nginx，但 Nginx 配置返回 404。仅静态核查，未验证正在运行的代理。

## 能力与安全边界

capabilities 在关闭 native 时仍需有效平台 JWT。读取 active 用户和 `disabled_modules`；admin 仅沿用模块豁免，不获得跨 owner 项目访问权。模块与 native 都允许才开放会话；Node URL+internal token 的配置前提满足才声明 read_discovery。prepare 额外依赖 Gateway 只读开关、Dataset 只读开关与 files/downloads/flows 模块许可。

该快照不是健康检查，不承诺模型、Redis 或 Node 可达。prepare 仍需服务端 owner 项目和现有 Gateway 再验；不支持写执行。实际会话路由在请求时重新取用户状态，owner 在服务层检查，不依赖按钮隐藏。全局 project=null 按独立查询返回，无默认项目副作用。

平台历史 DTO 直接校验现有 ORM；修复原实现调用不存在的 `ChatService._to_msg_dto`。流式消息通过现有 SessionService 写入，补齐必填 `content_type=text`。跨进程取消尚未实现，capability 明示 `browser_abort_only`，UI 明示停止接收，不能承诺服务端任务已停止。

`WRITE_RUNTIME_ACCEPTED=False`、`worker_paths_verified=false` 未修改。没有 Task/下载执行、生产凭据、数据库迁移或真实分析副作用。

## 验证与限制

证据目录 `evidence/treasure-native/` 仅保留本地验证，不进入提交。

| 检查 | 结果 | 证据 |
|---|---|---|
| P0 后端 + 既有 Phase1 合约 | 32 passed | `p0-backend-tests.log` |
| 寻宝鼠前端三组 | 12 passed | `p0-frontend-tests.log` |
| 前端类型检查 | PASS | `p0-frontend-types.log` |
| 前端 npm run build | PASS | `p0-frontend-build.log`（Vite 配置 logLevel=error） |
| 修改后端三文件 mypy | PASS，follow-imports=silent，非全仓 strict 结论 | `p0-backend-types.log` |
| 本次后端文件 Ruff | PASS | `p0-ruff-focused.log` |
| 迁移链检查 | PASS，单 head | `p0-migrations.log` |
| 全仓 Ruff | FAIL，295 项 | `p0-ruff-full.log` |
| 前端全套 | FAIL，541 passed / 7 failed，79 文件 | `p0-frontend-full-tests.log` |

前端失败涉及 `agent-teams-room-send` 五项、`deep-thinking-stream` 一项、`live-stream-render` 一项；未改这些业务文件，也未以此证明它们在基线就失败。全仓 Ruff 涉及其他领域，同样不擅自清理。后端全套运行 90 秒后超时（exit 124），停在约 11%，已出现 `test_agent_config_consistency.py` 失败；日志 `p0-backend-full-tests.log`。未获取最终汇总，不将局部通过推导全量通过。全仓 mypy、bridge 和真实集成验证未完成。未运行真实 PG/Redis/Worker、MCP 双进程或浏览器 E2E；没有现场 403、镜像运行证据，不宣称部署可用。

## Gate 与下一步

| 阶段 | 状态 | 原因 |
|---|---|---|
| G-P0 隔离功能 | PASS | 权限负例、全局只读历史、能力预检与入口测试通过 |
| G-P0 整体审查 | CONDITIONAL / NOT RELEASE READY | 现场证据缺失、全仓门禁未绿，待人工审查 |
| G-P1A | ISOLATED POC / BLOCKED | 已有隔离展示 PoC；浏览器 socket 被拒绝，无截图与人工视觉确认 |
| G-P1B / G-P1C / G-P2 | NOT STARTED | 依赖前序 Gate；旧卡片协议、完整历史与受控交接尚未验收 |
| G-R | BLOCKED | 真实基础设施、镜像/Worker/审批执行证据未闭合 |

下一项是审查 P0 diff 与隔离证据、补现场归因及全仓失败基线；之后可按任务书进入完全隔离的 P1-A PoC。P1-A 需旧新版截图与人工视觉确认，未通过不得进入完整迁移。

# CygnusX BioOps · Phase 1 实施任务书

## 科研寻宝鼠深度嵌入、统一身份、项目上下文与结构化发现结果

**实施模式：** Existing-code-first / Incremental Integration / Implementation + Tests + Documentation  
**优先级：** P1（身份与权限边界为 P0）  
**阶段性质：** 产品与业务边界集成，不是 Agent Runtime 重写  
**核心原则：** One Platform Identity · One Project Context · One Discovery Experience · No Unauthorized Side Effects

---

## 0. 执行前提与准入控制（必须首先执行）

你是熟悉 Vue、React、Node.js、FastAPI、SSE、科研 Agent、认证与多租户安全的资深工程师。需要**实际实施** CygnusX BioOps Phase 1，交付代码、自动化测试和实施报告；不得仅输出新的调查文档。

必须先读取并核对当前工作树中的：

1. `docs/audits/cygnusx-unified-research-agent-feasibility-audit-2026-10-13.md`
2. `docs/audits/cygnusx-phase0a-implementation-2026-10-13.md`（如实际路径不同，应搜索）
3. `docs/implementation/cygnusx-phase0b-runtime-integration-implementation.md`（如实际路径不同，应搜索）
4. `docs/implementation/cygnusx-phase0b-closure-implementation.md`、Phase 0B Closure Gate Matrix（如果已经存在）
5. `docs/audits/cygnusx-runtime-provenance-manifest.json`
6. `ARCHITECTURE_DESIGN/README.md` 及项目现行的前端规范、认证、Agent、会话、API 设计文档。

**先决安全事实：** 在已知 2026-10-14 Phase 0B 实施报告里，Phase 1 受控写工具接入为 `BLOCKED`。不得假设 Closure 已完成。必须读取最新 Gate 证据：

- 如果与拟实现路径相关的 Phase 0B P0 Gate 全部通过，可实施完整 Phase 1 **只读/界面/认证/会话**范围；写工具仍不属于 Phase 1。
- 如果 Gate 仍为 BLOCKED 或无法核实，本任务仅授权在**隔离开发环境**实施和测试原生 UI、认证桥、项目上下文、会话、只读发现、发现结果 DTO；不可部署给真实用户，不可开启真实下载、分析提交、取消或其他有副作用的 Agent 工具。
- 如果开发会触及无法保证身份隔离的服务，先安全禁用对应入口，提交隔离实现和阻断说明；不要通过降低鉴权绕开 Gate。
- 不得将进程内 FastMCP 测试视为真实 STDIO/HTTP Transport 验收通过。

本轮不允许：`git reset --hard`、`git clean -fd`、无授权 `git push`、生产部署、使用生产密钥、改动真实用户历史、运行大规模下载和生信计算。先记录 Git branch/HEAD/dirty paths/submodule 版本，严格保护已有未提交工作。

---

## 1. 已知基线及需要现场复核的事实

原可行性审计指出：

- CygnusX 主前端使用 Vue，`frontend/src/router/index.ts` 包含寻宝鼠入口；`frontend/src/views/TreasureMouseView.vue` 采用 `iframe` 指向 `/treasure-mouse/`。
- 寻宝鼠是独立 React/TypeScript 前端 + Node Chat 服务，常见入口包括 `pipelines/Treasure-Seeking_Mouse/src/routes/index.tsx`、`server/local.mjs`、`server/account-api.mjs`。
- 寻宝鼠现有 SSE 事件含 `delta`、`tool`、`cards`、`polariseq`、`grounding`、`end`；数据卡片包含 accession、title、summary、meta 等字段。
- 寻宝鼠拥有独立账号/聊天历史/模型设置，不使用平台可信 `project_id`；曾有 `DownloadBoostCard` 只提供 CLI 或项目链接而非平台实际下载。
- 平台已有 User/Project、ChatSession、Agent/MCP 基础设施和 TaskService；平台有能力执行分析任务，但这不意味着寻宝鼠已接入。
- 旧寻宝鼠构建 tag 与子模块源码存在漂移；先核实实际代码与镜像，严禁把某个历史 SHA 假定为现网来源。

这些为**过去报告事实**，须在实施前按实际版本核对文件/函数，不要机械依赖旧行号。发现不同版本时记录差异与方案影响。

---

## 2. Phase 1 最终目标与验收边界

目标：用户在 CygnusX 的「科研寻宝鼠」页面，使用平台既有登录身份和当前有权限的 Project，直接提问、获得工具过程与可信来源卡片、恢复会话，并能在平台内连续查看发现结果。

用户感知层面：

1. 不再看到 iframe 内嵌的另一套导航、登录页、模型/品牌布局。
2. 进入科研寻宝鼠不需要再次注册/登录。
3. 当前项目可见；切换项目后项目绑定明确且安全，不会静默串会话。
4. 现有“数据发现、文献检索、下一铲”等能力不丢失。
5. 发现卡片与证据来源可查看、复制 accession、继续提问。
6. 离开页面重新进入，可以恢复自己的历史与结构化结果。
7. 页面稳定支持流式输出、取消、失败重试、响应式布局、键盘访问。
8. Phase 2 将来可基于同一结构化发现结果生成下载/分析提案，但本阶段绝不实际触发这些写操作。

**非目标：** 合并 Node 到 FastAPI；完全迁移 Agent Loop；新增 Dataset 表；GEO processed-data adapter；counts-only DEG；整合下载/分析 MCP；BioReport 改造；重写主平台导航和主题系统。

---

## 3. WP1-0：确认前端集成路线（先定方案，再动代码）

请比较并依据实际工程选定最小风险方案：

**A — Vue Shell + React Island（优先候选）**：将现有寻宝鼠 React 的聊天核心作为嵌入式页面组件挂载到 Vue 页面中，不使用 iframe；仅保留内容区，复用 CygnusX 全局 Layout/路由/主题，尽量复用现有 Composer、Message、DatasetCard、ToolTrace。需核查打包、ReactDOM root、CSS 隔离、Vite 构建、依赖版本与组件卸载清理。

**B — Vue Native Chat View + Node Discovery API**：如果 React Island 会明显增加依赖冲突或长期维护成本，可以用平台 Vue 组件实现同等原生交互，复用寻宝鼠服务端 Agent 和流式 API。必须保留真实 tool trace、cards、grounding 和下一铲机制，不能为了迁移牺牲功能。

**C — iframe 延续**：只允许作为限时回退/兼容方案，不得作为本阶段“深度嵌入”的最终交付，也不得在 iframe 中简单伪造平台身份。

输出简短 ADR：为何选 A/B、放弃方案的成本、预计修改边界、回滚方式。**不能因为“统一技术栈”而默认全部 React → Vue，也不能以 React Island 代替后端统一身份。**

---

## 4. WP1-1：统一平台身份与服务端信任边界

### 4.1 认证链

目标架构（字段与 API 路径按现有项目契约实现，不机械照搬）：

```text
Browser (CygnusX authenticated session)
    → CygnusX authenticated backend/BFF
    → verified platform principal + authorized project context
    → internal Research Treasure Agent adapter
    → existing Node tool-calling / external public data sources
```

要求：

- 复用平台现有 CurrentUser/JWT/Session/RBAC，不创建第二套用户认证系统。
- 页面端不得让用户填写寻宝鼠账号，不从 URL、query string、localStorage 或 Agent 文本推导可信 `user_id`。
- 不将平台长期 JWT、API Key 或任何管理员凭据嵌入 React bundle、URL、SSE payload 或日志。
- 若需要内部服务委托，采用项目现有可信服务认证或短时、作用域受限、受众明确的 server-to-server 断言；由平台后端签发/校验，并确保 Node 入口只能受信任调用。不要发明一个前端可任意构造的 `X-User-Id` 认证替代品。
- 每个会话读取/写入、历史查询、对话请求、项目切换都必须后端核对 owner/project 权限；前端当前项目只用于 UI，不代表授权。
- 防止原独立 `/auth`、`/history`、直连 chat endpoint 从反向代理或外部路径绕过平台授权。检查 Nginx、网络和直连入口，不得只在 Vue 路由加 requiresAuth。
- 保留原账号/数据作为兼容与恢复来源，先设计映射/迁移，不删除用户数据、不自动合并相同邮箱的账号。
- 若存在自托管账号与 Supabase 双模式，分别定义处理策略。无法证明归属的数据不自动迁移。

### 4.2 身份切换与错误

必须处理：未登录 401、无项目权限 403、会话 owner 不符、登出后撤销访问、平台 token 过期、项目被删除或权限变更、内部服务故障、上游模型故障。返回可诊断的错误码，但不得泄漏凭据和跨用户记录。

---

## 5. WP1-2：Project Context 契约

平台提供受信任的上下文，包括但不限于：

- `principal_id`：由平台后端认证得出；
- `project_id`：由平台查询并鉴权的项目标识；
- `session_id`：绑定当前用户和项目的会话标识；
- `model_selection`：经平台能力和权限检查的模型配置（如果现有系统支持）；
- `request_id` / `correlation_id`：可追溯请求标识。

**不要让模型决定 owner/project；不要仅凭字符串类型的 `projects/<slug>` 路径认定权限。**

场景：

1. 未选择项目：按产品现行规则允许“全局只读发现”或提示选择项目；不得擅自把结果归入默认项目。
2. 选定项目：用户和项目真实存在，当前用户有权限；新会话绑定项目。
3. 切换项目：已有会话保持其原项目绑定；建议提示创建新会话/显式切换，禁止静默把旧会话重定向到新项目。
4. 无权限项目或被删除的项目：拒绝访问，并提供返回项目选择器的操作。
5. 直接打开深链：服务端仍检查权限，不因路由 ID 存在而放行。
6. 后续共享项目：以实际 RBAC/ProjectModel 支持为准，不预设多人协作已经实现。

若 Agent 检索提示词需要了解项目主题，只传经过筛选的非敏感上下文；不要把用户项目中的所有文件、会话、秘钥或未授权数据自动塞入模型消息。

---

## 6. WP1-3：统一流式对话接口与事件契约

### 6.1 优先适配现有服务

调查真实 Node Chat 请求（messages/model/stream/lang 等）和 SSE 事件，构建轻量 BFF/Adapter，不重写既有科研检索工具链。

若需要新增平台路由，采用项目已有 API 命名和依赖注入方式；以下为候选能力而非必须照抄的路径：

- `POST /api/v1/research-agent/sessions`：创建当前 owner/project 会话；
- `GET /api/v1/research-agent/sessions`：仅列出自己的历史；
- `GET /api/v1/research-agent/sessions/{id}`：读取会话和事件；
- `POST /api/v1/research-agent/sessions/{id}/messages:stream`：流式对话；
- `POST /api/v1/research-agent/sessions/{id}/cancel`：取消当前流式请求（不是取消平台 Task）；
- `GET /api/v1/research-agent/capabilities`：只读可用模型/功能信息。

如项目已有 Chat Session API 能安全复用，优先扩展而非创建平行会话 CRUD。若 Node 已有可用 API，也可通过已有后端 BFF 代理；必须保留平台身份审计。

### 6.2 SSE 兼容

至少支持映射并展示：

- `delta`：增量消息；
- `tool`：工具状态/轨迹；
- `cards`：结构化数据集卡片；
- `polariseq`：原有工具结果或提示，只读展示，不自动执行下载；
- `grounding`：Accession 和证据来源；
- `end`：请求正常完成；
- error/cancel：错误与用户中止（按实际协议定义）。

采用明确版本的事件 DTO/Schema，保存时不得丢失关联字段。无效上游负载应拒绝或安全降级；不要直接渲染未清洗 HTML。支持逐 token 更新、Abort/cancel、断连、超时、重入、重复 end、事件顺序异常、刷新后恢复；如无法真正恢复 token 流，需明确呈现“流中断”而非伪称任务继续生成。

为工具调用和外部数据源内容保留可信/不可信边界：证据卡片的外部文本不是执行命令，提示注入文本不得获得项目权限或业务工具能力。

---

## 7. WP1-4：原生页面体验与设计规范

### 7.1 布局

保持 CygnusX 现有侧栏、顶部导航、面包屑、字体、间距、颜色和响应式规则。研究寻宝鼠应是一个**完整的主平台页面**，不是嵌在内部再有一套导航栏的“小网站”。

建议：

- 顶部简洁说明区：标题“科研寻宝鼠”、一句价值说明、当前项目标识；
- 中心对话区：初始状态显示常用科研探索示例，开始对话后切换为消息流；
- 会话历史：复用平台导航模式或自适应侧面板，不让导航元素跨度过大；
- 结构化结果：数据集卡片、来源链接、证据状态、继续检索/“下一铲”；
- 对话 Composer：固定在内容容器底部、文本域自动增高，Enter/Shift+Enter 行为明确；
- 流式状态：工具调用、检索中、完成、取消、失败可感知；
- 空状态/首次进入/无项目/无权限/无结果/网络中断均有统一样式。

请先检查并严格遵循仓库已有前端设计规范和组件库。不要自行引入新的大型 CSS 框架替换现有样式体系。

### 7.2 UX 细节

- “数据发现”等场景按钮**一次点击即可填充并启动或进入明确的对话流程**，不要让用户重复点击另一层“下一铲”才能真正开始；如果直接执行会产生模型费用，按已有交互规范提供明确触发行为。
- 保留已有真正有效的科研能力：数据库检索、文献、证据来源、下一铲、数据卡片；不可通过静态 Mock 代替。
- 统一模型入口优先读平台模型能力表；在无法兼容时可阶段性锁定经平台配置的后端模型并隐藏独立设置，但不可悄悄改变模型语义或偷偷转发用户凭据。
- 卡片与外链均须做 URL 白名单或安全策略、转义，避免 XSS、危险协议和伪造平台操作链接。
- 响应式宽度、侧栏折叠、长标题/长 accession、超宽表格、深色模式（如平台支持）、键盘导航与 `aria-live` 流式消息提示。
- **禁止虚假可执行按钮**：若下载、导入项目、提交分析尚未接入，只能展示明确的“未开放/下一阶段”说明或隐藏，不生成假 Task ID、不显示假进度。

### 7.3 UI 验收尺寸

在至少 desktop 宽屏、普通笔记本和移动窄屏三类 viewport 验证；避免内外双滚动、输入框遮挡、标题与导航重复、结果卡溢出。建议截图比较现有 Vue 主平台与原寻宝鼠页面，并记录改变前后差异。

---

## 8. WP1-5：会话历史、数据归属与兼容策略

### 8.1 新会话

每条会话必须具有可验证的 owner 及明确的 project scope（允许按产品规则为 null），存储消息与结构化事件、创建/更新时间和最终完成状态。优先复用现有平台 ChatSession/事件存储；若语义不同，建立明确适配层，不混写格式不兼容的 Agent 会话。

明确处理：

- 会话列表分页/排序；
- 继续对话与上下文恢复；
- 重命名/归档/删除（仅在复用现有授权 API 后实施；删除是有副作用操作，须独立授权和确认，不属于 Agent 写工具）；
- 流中断与失败事件；
- SSE cards/grounding 重开后仍可复现；
- 多浏览器标签页同时续聊的版本冲突与重复消息；
- 退出登录后的会话缓存清除/不可访问；
- 避免共享会话 URL 意外泄漏私人项目数据。

### 8.2 历史数据迁移

寻宝鼠独立 `account-api`/local history/Supabase 的历史归属不是平台账户的天然映射。**不得通过用户名/邮箱碰撞自动合并，也不得删除旧库。**

推荐：先实现新平台会话，原历史只读兼容或不迁移；如需要迁移，另设经用户认证、可追溯、幂等且可回滚的显式导入过程，记录映射关系、来源、冲突与失败，不混淆两套身份。迁移工具本身不得绕过 Phase 1 的只读发现边界而操作科研 Task。

### 8.3 数据隐私

对话、项目名称、检索问题和证据卡可能包含未发表科研计划；所有持久记录依平台数据隔离、日志脱敏、备份与保留策略处理，不得自动变成公开共享链接。

---

## 9. WP1-6：Discovery Proposal / Evidence DTO（不是 Dataset）

将寻宝鼠发现结果整理成**平台可消费的只读结构化提案**，为 Phase 2/3 做输入契约准备。

建议定义类似：

```yaml
schema_version: "1.0"
proposal_id: "generated-by-platform"
source: "GEO"
accession: "GSEXXXXXX"
title: "..."
summary: "..."
organism: null
assay_type: null
sample_count: null
metadata_status: "unverified"
source_links: []
evidence_refs: []
retrieved_at: null
project_id: null
conversation_id: null
provenance:
  agent: "research-treasure-mouse"
  tool_name: null
  verification_level: "source_not_verified"
next_actions:
  - "inspect_metadata"
  - "refine_search"
```

**这只是候选 schema，须以现有 DatasetCard、grounding 和平台模型核对。**

要求：

1. Accession、源数据库、URL、论文与样本数等字段不可臆造。
2. 区分数据源声称、Agent 推断、平台实际验证。
3. 明确“已发现研究编号”不等于“已找到正确实验设计”。
4. 明确 DiscoveryProposal **不等于**已经下载或登记的 Dataset、FileRecord、Artifact。
5. 不在 Phase 1 产生下载 Task/分析 Task，不通过名字相同就将数据卡片映射为项目资产。
6. 保留工具名称、检索时间、外部来源和会话关联，至少支持从卡片回到证据来源。
7. `next_actions` 为 UI 只读意图；任何未来写操作必须走 Phase 2 安全确认。
8. 结构化 DTO 提供 JSON Schema / Pydantic / TypeScript 类型中的适当组合，并有兼容旧卡片的映射测试。

不必在 Phase 1 引入全新的科研 Dataset 数据库表。必要的提案持久化优先利用现有授权的聊天消息/事件存储。

---

## 10. WP1-7：兼容、开关、可观测与回滚

### 10.1 功能开关

建议使用现有 feature flag/config 体系提供两种独立能力控制：

- `treasure_native_ui_enabled`：决定在隔离环境启用原生入口；
- `treasure_agent_write_tools_enabled`：决定是否有资格使用平台写工具，**本阶段强制后端 false**。

名称仅作候选，按仓库既有配置命名。前端按钮隐藏不算后端禁用。即便请求伪造写操作，也必须在可信后端拒绝。未来打开写功能还须 Phase 0B P0 Gate READY 和 Phase 2 的独立验收，不得因打开原生 UI 自动开放。

### 10.2 双轨回退

保留原 iframe 作为受控短期回退路径，但必须走可信平台访问控制；不可因为回退而再次暴露独立登录绕权入口。新旧会话数据不可相互覆盖。若原旧模式不满足平台安全边界，则只能在开发环境访问，不能作为正式回退功能。

### 10.3 可观测性

复用平台现有 request_id、session_id、trace/Tool event 等记录；若可安全关联，记录 project_id、工具来源和事件类型。不得记录 access token、API Key、原始确认凭证或全部未经脱敏的研究文本。

对于性能与稳定性，观测：首 token 延迟、总响应时长、检索工具耗时、上游错误率、SSE 中断率、会话恢复成功率。无性能基线时记录实测，不捏造 SLO。

---

## 11. 必须补充的自动化测试与手工验收

### 11.1 身份 / 项目安全（P0）

| Case | 预期 |
|---|---|
| AUTH-01 未登录访问页面 API | 401，不能获取对话 |
| AUTH-02 用户 A 读取 B 会话 | 403/404，不泄漏内容 |
| AUTH-03 用户 A 指定 B 项目 | 403/404，不创建会话 |
| AUTH-04 前端伪造 owner/project/header | 可信服务端不接受伪造身份 |
| AUTH-05 登出或身份失效 | 新请求拒绝，旧缓存不可再读取 |
| AUTH-06 原独立 chat/history 直连 | 无法绕过平台认证读取他人记录 |
| AUTH-07 项目切换 | 不偷偷修改旧会话所属项目 |
| AUTH-08 旧账号/Supabase 模式 | 无自动合并、无历史丢失 |

### 11.2 流式对话 / UI

| Case | 预期 |
|---|---|
| CHAT-01 单轮/多轮 | 正常调用真实工具并显示结果 |
| CHAT-02 delta/tool/cards/grounding/end | UI 和存储映射完整 |
| CHAT-03 下一铲 | 可续聊且保持合适上下文 |
| CHAT-04 上游断连或模型超时 | 错误可见，无虚假 completed |
| CHAT-05 用户取消流 | 当前流终止，无孤儿网络请求 |
| CHAT-06 页面刷新/会话恢复 | 消息和结构化卡片保留 |
| CHAT-07 两标签页并发 | 无混写/重复消息或有明确冲突机制 |
| CHAT-08 外部 HTML/危险链接 | XSS/危险 URL 被拦截 |
| CHAT-09 宽屏/笔记本/窄屏 | 无双滚动、组件溢出、输入框遮挡 |

### 11.3 Agent 写工具门禁

| Case | 预期 |
|---|---|
| WRITE-01 寻宝鼠请求下载 | 后端拒绝；不创建下载 Task |
| WRITE-02 寻宝鼠请求分析提交 | 后端拒绝；不创建分析 Task |
| WRITE-03 寻宝鼠请求取消平台任务 | 后端拒绝；不更改任务状态 |
| WRITE-04 React/浏览器伪造开启 feature flag | 无法覆盖后端门禁 |
| WRITE-05 只读检索/下一铲 | 保持可用（在授权的隔离环境） |

### 11.4 回归 / 构建

- Vue 主平台 build/typecheck/lint 与原有路由回归；
- React 内核或新 Vue 页面 build/typecheck/lint 与组件测试；
- Node Chat 工具事件契约回归；
- FastAPI BFF/会话权限单测和集成测试；
- CI 中所有与本次 diff 相关的已启用检查；
- 若测试基础设施缺失，列出 BLOCKED，不能声称 E2E PASS。

不得调用大规模公共组学下载或生产计算。建议在 Mock 外部数据服务下测试卡片、在已允许的测试环境用小型只读检索作 smoke。

---

## 12. 分阶段实施顺序与可独立验收的 PR

建议避免一个巨大 PR。若当前没有实际 PR 权限，则按逻辑子阶段和改动清单组织，禁止自动 push。

**P1-A · Contract & ADR**：确认当前版本、前端路线、BFF 边界、会话/发现事件协议、原账号策略。产出 ADR 和测试基线。

**P1-B · Platform Auth + Project Context**：完成可信后端桥、owner/project 校验和未授权负例。先让纯只读请求安全工作。

**P1-C · Stream & Session**：SSE 转发/适配、取消/超时、历史会话/事件持久化与恢复。先做后端契约测试，再接 UI。

**P1-D · Native UI**：替换默认 iframe 产品入口，接入 React Island 或 Vue 原生视图；复用 CygnusX 布局和设计系统，消除重复登录/导航/模型设置。

**P1-E · Discovery Proposal & Evidence**：将卡片/grounding 映射为可追溯 DTO，展示只读下一步操作，不创建 Dataset/Task。

**P1-F · Regression & Gate Review**：双用户/双项目、SSE/历史/安全写门禁、响应式/无障碍、构建、回滚演练、实施报告；根据 Phase 0B Gate 只做隔离验收或可发布只读功能的判断。

每个子阶段必须包含：修改文件、兼容策略、自动化测试、实际运行结果、已知阻断。不得跳过 P1-B 身份边界先公开新 UI。

---

## 13. 代码落点（核对实际路径后实施）

主要候选：

```text
frontend/src/router/index.ts
frontend/src/views/TreasureMouseView.vue
frontend/src/components/...
frontend/src/api/...

pipelines/Treasure-Seeking_Mouse/src/routes/index.tsx
pipelines/Treasure-Seeking_Mouse/src/services/seqoutChat.ts
pipelines/Treasure-Seeking_Mouse/src/components/...
pipelines/Treasure-Seeking_Mouse/server/local.mjs
pipelines/Treasure-Seeking_Mouse/server/account-api.mjs
pipelines/Treasure-Seeking_Mouse/functions/seqout-chat/index.ts

deploy/docker/docker-compose.yml
deploy/docker/nginx/nginx.conf

src/cygnusx/api/v1/...
src/cygnusx/application/services/...
src/cygnusx/domain/models/chat.py
src/cygnusx/domain/models/project.py
src/cygnusx/infrastructure/mcp/...
```

这些是**定位线索**，不是要求逐一改动。优先遵从最新仓库模块结构、命名约定、API 注册和已有前端规范。相关子模块如需修改，应明确其独立 Git 状态和发布链，不要以主仓未提交工作遮盖子模块版本漂移。

---

## 14. 交付文档与完成定义

建议写入现有文档体系：

1. `docs/implementation/cygnusx-phase1-treasure-mouse-integration.md`：完整实施报告。
2. `docs/architecture/cygnusx-treasure-agent-integration-adr.md`：React Island / Vue Native 选型、BFF、会话与鉴权设计；若已有 ADR 目录按实际调整。
3. `docs/contracts/research-discovery-proposal-v1.md`：事件、卡片与只读发现提案 Schema；如已有协议目录则更新原文件。
4. 相关前端、后端、Node 单元/集成测试与 UI 回归。
5. 改动文件索引、Phase 0B Gate 引用、feature flag 与回滚说明。

### Phase 1 验收门槛

- **G1 身份**：单点登录；所有 BFF/会话请求后端身份校验；独立服务入口不可绕过。
- **G2 项目**：project/session/owner 绑定可信，双用户/双项目负例通过。
- **G3 原生页面**：生产候选 UI 默认不使用 iframe；保留 CygnusX Layout，不出现第二套登录/导航。
- **G4 核心功能**：数据检索、文献、下一铲、ToolTrace、卡片和 grounding 功能保持。
- **G5 SSE**：增量、取消、异常、恢复与结构化事件通过测试。
- **G6 历史**：新会话可恢复；旧历史不丢失、不误合并。
- **G7 Proposal**：可序列化、有证据、不等于 Dataset；数据来源不虚构。
- **G8 安全**：所有下载/分析/取消 Agent 写入口后端关闭，负例无 Task 副作用。
- **G9 质量**：构建、类型检查、相关回归通过，失败/阻断如实报告。
- **G10 可回滚**：原入口回退不会复活独立账号绕权路径，不删历史。

最终 Phase 1 判定：

- **COMPLETE (read-only integration)**：G1–G10 全部在授权隔离环境通过；已得到 Phase 0B 相关发布门禁支持，才可考虑发布只读功能。
- **IMPLEMENTED / RELEASE BLOCKED**：代码和隔离测试通过，但 Phase 0B 相关运行门禁尚未通过；禁止面向真实用户开放。
- **PARTIAL / BLOCKED**：身份、权限、流协议、历史或关键构建验收失败；不能宣称完成。

**阶段完成不等于允许 Phase 2 写操作。** Phase 2 还需要共享受控工具层、用户确认和真实下载/分析的专项验收。

---

## 15. Codex 最终回复要求

执行完成后请报告：

1. Phase 1 实际实施状态与是否仍受 Phase 0B Gate 限制。
2. 选用 React Island 还是 Vue Native，以及为什么。
3. 平台身份 → BFF → Node 的可信调用路径和对应代码文件。
4. Project Context 与会话数据如何持久化和隔离。
5. 原 SSE 事件与数据卡片映射是否保留完整。
6. 旧账号和历史数据的处理方案（迁移与否、是否可能丢失）。
7. 原生 UI 实际运行截图或可复核说明、响应式/无障碍验收情况。
8. 写工具的后端拒绝测试结果，是否产生任何 Task 副作用。
9. 修改文件列表、测试 PASS/FAIL/BLOCKED/SKIPPED、测试命令及运行环境。
10. 数据库迁移、兼容风险、回滚策略、未完成问题和 Phase 2 准入建议。
11. 实施报告、ADR、契约文件位置。

不要再次只提交一份静态调查报告；在符合安全边界的隔离环境中完成可以完成的代码和测试。若部分能力因环境/权限阻断，必须报告证据与解除条件，不能假装通过。

---

## 最终架构原则

**Embed the experience. Reuse the agent. Trust the platform identity. Preserve scientific evidence.**

让科研寻宝鼠成为 CygnusX 的原生科研发现入口，而不是重新造一个独立应用；把 Agent 发现结果沉淀成有项目上下文和来源证据的结构化科研线索，为 Phase 2 的安全 MCP 工具编排、Phase 3 的 GEO 数据导入及后续可复现报告交付奠定基础。

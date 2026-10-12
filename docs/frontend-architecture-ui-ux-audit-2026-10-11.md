# CygnusX Frontend Architecture & UI/UX Audit - v1.0

审计日期：2026-10-11  
范围：`frontend/` 当前源码、路由、依赖、主题与公共组件。  
方法：静态代码审计与仓库内现有审计结果交叉核对；未启动浏览器、未截图、未修改业务代码。

## 1. Executive Summary

CygnusX 前端是一个 Vue 3 + TypeScript + Vite 的单一 Vite 应用。路由、Pinia 状态、Naive UI 组件和 API/composable 层已经形成可运行的基础；页面路由使用动态 import，AI 对话、Studio、文件管理和寻宝鼠拥有明确的专用组件边界。

当前不一致主要来自多套样式来源同时存在，而不是缺少任何 UI 库：`tokens.css`、`global.css`、`chat-theme.css`、Tailwind utilities、Naive UI 主题覆盖，以及页面 scoped CSS/inline style 共同决定最终样式。`global.css` 仍保留 Arco 命名变量和面向硬编码浅色样式的深色补丁，导致主题治理依赖选择器顺序和 `!important`。

主要结论：

- **基础成熟度：中等偏高。** 有令牌、`PageHeader`、`EmptyState`、任务/报告卡片、主题 store、Naive UI 组件和页面级懒加载。
- **统一性：中等。** 常规业务页大多共享 `DefaultLayout` 和 `.page-container`；寻宝鼠、文件、AI、Studio 通过 `fullscreen` 进入不同滚动和内边距契约。
- **最高风险：** 主题令牌绕行、超大 SFC、全局 CSS 覆盖、缺少全局错误/路由 chunk 恢复，以及任务/报告/项目之间的上下文未由单一导航上下文统一管理。
- **不应保留的误区：** 不建议一次性重写页面。应先冻结 token/布局契约，再按科研工作流迁移高频页面。

## 2. Repository Architecture

### 2.1 技术栈证据

| 项目 | 当前实现 | 证据 |
|---|---|---|
| 框架/语言 | Vue 3 + TypeScript strict toolchain | `frontend/package.json`、`src/main.ts` |
| 构建 | Vite 5、Vue plugin、PostCSS、Tailwind | `package.json`、`vite.config.*` |
| UI | Naive UI 2.38，`@vicons/ionicons5`/Carbon 图标 | `src/main.ts`、各页面 imports |
| 状态 | Pinia；按域拆分 auth/chat/agentHub/modules/theme 等 store | `src/stores/` |
| 路由 | Vue Router 4，`createWebHistory`，页面动态 import | `src/router/index.ts:1-48` |
| CSS | 全局 CSS + CSS variables + Tailwind utilities + SFC scoped CSS；无 CSS Modules | `src/styles/*.css`、各 `.vue` |
| 图表 | ECharts/vue-echarts、Plotly、phylotree 等按业务使用 | `package.json`、`src/components/charts`、工具页 |
| AI 渲染 | markdown-it/DOMPurify/highlight.js，自定义 Kimi 消息、工具调用、审批、计划、任务卡 | `src/components/ai-chat/`、`src/components/MarkdownRenderer.vue` |
| 响应式 | SFC `@media` 分散定义；壳层以 768/1024 为主要断点 | `DefaultLayout.vue:136-145`、各页面 style |
| 主题 | Pinia `data-theme=dark/light`，CSS variables；默认 dark | `src/stores/theme.ts`、`src/styles/tokens.css` |

### 2.2 实际目录和入口

- 入口：`src/main.ts`，注册 Pinia、Router、Naive UI、MotionPlugin、全局指令和三组全局样式。
- 应用壳层：`src/App.vue` → `src/layouts/DefaultLayout.vue`；认证页面使用 `AuthLayout.vue`。
- 页面：`src/views/`；公共展示/业务组件分布在 `src/components/` 下的 `ai-chat`、`studio`、`data-management`、`task`、`report`、`bio-tools` 等域。
- API 边界：`src/api/`；通用请求 composable 在 `src/composables/useApi.ts` 等文件。
- 状态边界：`src/stores/`，页面通过 Pinia 和路由参数交接会话、任务、项目、文件 ID。

```mermaid
flowchart TD
  Browser[Browser] --> Main[src/main.ts]
  Main --> Router[Vue Router]
  Main --> Pinia[Pinia stores]
  Main --> Naive[Naive UI + vicons]
  Router --> Auth[AuthLayout]
  Router --> Default[DefaultLayout]
  Default --> Header[Top nav]
  Default --> Sidebar[Sidebar 220/80px]
  Default --> Content[Naive layout content]
  Content --> Standard[Standard page views]
  Content --> Fullscreen[Fullscreen views: files / AI / Studio / treasure]
  Standard --> Shared[PageHeader / EmptyState / TaskTable / ReportCard]
  Standard --> API[src/api + composables]
  Fullscreen --> Domain[AI chat / Studio / file explorer components]
  Shared --> Theme[tokens.css + global.css + chat-theme.css]
  API --> Backend[/api/v1]
```

主平台是共享入口的单一 Vite 应用；另有同源 `/treasure-mouse/` iframe 子应用，`TreasureMouseView.vue` 只负责加载/错误提示和 iframe 容器，子应用源码不在 `frontend/src` 内。`/studio/shared/:token` 是主应用中的分享路由。

## 3. Global Layout Audit

### 3.1 壳层关系

`DefaultLayout` 提供顶部导航、桌面侧边栏、移动抽屉、通知抽屉、上传浮球、全局 AI 助手和内容区域。侧边栏固定宽度 220px，折叠宽度 80px（`DefaultLayout.vue:542-550`）；窗口小于 1024px 自动折叠，小于 768px 进入移动端模式（`DefaultLayout.vue:136-145`）。

内容内边距不是单一契约：普通路由为 24px，工具箱区域为 0，由工具页自行提供内边距，全屏路由也为 0（`DefaultLayout.vue:117-130`）。这解释了普通页面、工具页、文件页和 AI/Studio 页面边缘对齐不一致。

### 3.2 顶部和侧边导航

- 顶部导航和侧边导航分别由 `topNavItems`、`mainNavItems` 两个 computed 数组维护（`DefaultLayout.vue:257-265`），当前不是同一个菜单配置对象的投影。
- 侧边栏展开项写入 `localStorage` 的 `cygnusx:sidebar-expanded`（`DefaultLayout.vue:63-83`）；折叠态和移动抽屉是壳层本地状态。
- 访问控制通过 `modulesStore.lockedModuleForPath` 与 `disabled_modules` 计算，菜单项和内容区各自判定（`DefaultLayout.vue:102-115`）。
- 路由 active 状态与菜单路径匹配；权限不是由路由文件单独决定，仍依赖模块注册表和后端。
- 顶部和侧边可能出现同一功能的多个入口，且团队协作室/部门路由当前以注释保留，代码与导航存在暂时下线状态。

### 3.3 特殊工作区

`fullscreen: true` 在 `DefaultLayout.vue:117-134` 只让内容区 padding 归零并切换滚动容器；它不绕开 DefaultLayout。寻宝鼠、文件、AI、Studio 均仍处于全局 Header/Sidebar 壳层内，AI/Studio 路由还会自动折叠全局侧栏（`DefaultLayout.vue:162-185`）。Studio 在内容区内部再渲染 `.studio-topbar`（`StudioView.vue:1041-1048`），位于全局 Header 下方。AI 的 `AIChatView` 只包 `AgentWorkspace`；其中有 60px `AgentSidebar`，活跃会话时 `AgentSandbox` 再渲染 agent/session header（`AgentWorkspace.vue`、`AgentSidebar.vue`、`AgentSandbox.vue:567-632`）。这是附加的工作区导航和会话工具栏，不替代全局 Header。寻宝鼠 Vue 页面（`TreasureMouseView.vue`）展示加载/错误状态并 iframe 嵌入 `/treasure-mouse/`；本仓库没有 iframe 子应用源码，不能据此推断它的内部 UI 或主题实现。不同内容区有不同工作区布局；当前证据不足以判断差异属于历史不一致还是有意设计，WorkspaceLayout 只是待评估方案。

### 3.4 主要风险

1. 普通页、工具页和全屏页有三套 padding/scroll 规则，新增页面容易选错。
2. `html, body, #app` 使用 `height: 100vh`、`overflow: hidden !important`（`global.css`），滚动责任下沉到各布局容器；遗漏 `min-height: 0` 或内部 overflow 时容易产生高度溢出。
3. Header/Sidebar 菜单配置分散，新增模块需要多点修改。
4. `App.vue` 在 RouterView 外包有 `AppErrorBoundary`；`main.ts` 未设置 `app.config.errorHandler`，router 文件也没有 `router.onError`。可确认有应用视图树级 render error boundary；动态路由 chunk 失败的用户恢复行为尚未实测，记为待验证风险。

## 4. Design System Audit

### 4.1 颜色和主题

当前已经存在事实上的 token，但有重复来源：

- `tokens.css:1-54` 定义浅色品牌色、背景、文字、圆角和阴影；`tokens.css:56-97` 定义深色 surface 与另一组品牌色。
- `global.css:12-53` 又定义 `--arco-*`、`--kimi-chart-*`、`--neutral-*`、sidebar 和 motion 变量。
- Studio 另有 `--studio-*` 变量；聊天在 `chat-theme.css` 和 `global.css` 中再映射一层。
- 页面/组件仍直接写十六进制和 rgba，且 `var(..., #fallback)` 很多；全局深色补丁用属性选择器和 `!important` 追赶浅色硬编码。

静态计数（当前源码，不含 `dist`）：约 1,918 个颜色字面量匹配、132 个 `!important`、269 个 inline `style` 属性。计数包含同一文件重复和测试/示例，不能等同于独立问题数，但足以证明 token 不是唯一来源。

品牌蓝紫、状态色和子品牌色没有统一语义层。寻宝鼠绿色子品牌是任务背景给出的目标约束；由于本仓库只包含 iframe host，本次无法确认子应用是否已实现。后续应让其覆盖品牌 accent，同时沿用共享 surface、focus、error 和 disabled 语义。

### 4.2 字体与字号

`global.css` 已提供 Inter/system/Noto Sans SC 字体栈和 11/12/13/14/16/18/24/28px type scale。实际页面同时存在 12、13、14、15、16、18、20、22、24、28 等局部值；Studio、聊天、管理页和工具页各自加入字号。等宽字体只在代码/终端上下文出现，没有统一的 numeric/data token。

建议未来冻结：`display 28/36`、`page-title 24/32`、`section 18/28`、`card-title 16/24`、`body 14/22`、`small 13/20`、`caption 12/18`，并增加 `mono 13/20`；不要再新增页面级字号。

### 4.3 间距、尺寸、材质

已有 4px 基础刻度（`--space-xs` 到 `--space-5xl`）、`--page-padding:32px`、`--card-padding:24px`；但 `.page-container` 实际是 24px（`global.css:483-487`），管理页、工具页、Studio 和局部组件各有独立 padding。圆角至少有 2/4/8/10/12/16/999px；阴影既有 `--shadow-card`，也有大量局部 rgba。

壳层尺寸证据：Header 高度由局部 CSS 定义，Sidebar 为 220/80px；未发现一个导出给所有页面的 `--header-height`/`--sidebar-width` token。表格和表单控件大多使用 Naive UI 默认高度，局部组件又覆盖。

### 4.4 组件复用表

| 组件类别 | 当前实现 | 复用评价 | 治理建议 |
|---|---|---|---|
| Button/Input/Select/Tabs/Table/Modal/Drawer | 直接使用 Naive UI，页面 scoped CSS 局部覆盖 | 基础复用高，语义变体分散 | 通过 Naive theme overrides + 少量 wrapper 固化高度/焦点 |
| Page header | `components/PageHeader.vue`，任务/流程/报告/项目/仪表板等使用 | 已有公共实现 | 统一 actions、back、breadcrumb 和 loading slot |
| Empty state | `components/EmptyState.vue`、报告专用 `ReportEmptyState.vue` 等 | 存在重复 | 统一 icon/title/description/action/compact 变体 |
| Task status/table | `components/task/TaskTable.vue`、AI `TaskProgressCard`、工作流 widgets | 语义和显示多套 | 抽取 `WorkflowStatus` 与任务摘要 DTO 适配层 |
| Report | `ReportCard`、`ReportCardMinimal`、预览 modal | 业务组件可复用但视觉变体无契约 | 定义 report card density 和 preview interface |
| AI messages/tool cards | `KimiMessageItem`、20+ tool/approval/plan cards | 领域复用强，文件过大 | 按 message renderer、tool renderer、actions 拆分 |
| Bio tool cards | `ToolCard.vue` + 各工具页面独立 CSS | 入口可复用，详情页差异大 | 固定工具卡 metadata、状态和 CTA |
| Navigation | 仅存在于 `DefaultLayout` 与各工作区 | 配置复用低 | 建立模块 registry → top/side/mobile projections |

## 5. Page-by-Page Findings

| 页面 | 真实路由 / 主组件 | 主要证据和问题 | 风险 | 推荐方案 |
|---|---|---|---|---|
| 首页 | `/` → `HomeView.vue` | 首页 682 行；Hero/快捷入口/动画和全局壳层并存，使用大量页面专用样式 | P2 | 保留品牌 Hero，抽取快捷入口和公告 token；不要套普通 dashboard 卡片 |
| 仪表板 | `/dashboard` → `DashboardView.vue` | 使用 `PageHeader`、`NDataTable`、多个 dashboard panels；738 行且有 1024/768 响应式分支 | P1 | 固定指标卡/趋势图容器，统一 loading/empty/error；图表按卡片边界响应 |
| 科研寻宝鼠 | `/treasure-mouse` → `TreasureMouseView.vue` → same-origin iframe `/treasure-mouse/` | 路由 `fullscreen`；Vue 页显示 loading/error 并嵌入独立服务的子应用；子应用内部视觉未审计 | P2 | 先取得子应用源码/运行证据；用户要求的绿色子品牌属于目标约束，当前仓库证据不足以确认实际表现 |
| 数据管理 | `/files` → `FilesView.vue` | `fullscreen`，1340 行，文件树/抽屉/预览/上传多栏；移动端另有 drawer | P1 | 保留 explorer layout；拆 FileTree/FileDetail/Activity，统一 file ID 和 upload 状态 |
| 参考基因组数据库 | `/database`、`/reference-genomes` → `ReferenceGenomesView.vue` | 两个别名路由指向同一视图；详情还有两个别名；838 行 | P2 | 保留资源目录布局；统一 canonical route，卡片状态和版本 metadata |
| 数据下载 | `/downloads` → `DownloadsView.vue` | 1153 行，表单、配置、任务列表和下载进度混在一个文件；完成后跳 `/tasks/:id` | P1 | 拆 DownloadForm/Preview/History；用任务摘要组件复用任务状态 |
| 任务中心 | `/tasks` → `TasksView.vue` + `TaskTable.vue` | 有 analysis/agent-teams query tab；结果入口按 toolbox 或 report 分流 | P1 | 保留表格密度；统一状态枚举、固定列宽和 task action semantics |
| 流程监控 | `/workflow-monitor` → `WorkflowMonitorView.vue` | `PageHeader` + WebSocket widgets；实时事件/错误/指标组件分域 | P1 | 固定 monitor grid 和可折叠 widget contract；空/断线状态统一 |
| 结果报告中心 | `/reports` → `ReportsView.vue` + `ReportCard` | query `taskId` 深链过滤，报告可跳 task 或创建 Studio session；有重复 flow option `rna_seq`/`rna-seq` | P1 | 规范 flow ID；复用 `ReportPreview` 和 task provenance；明确生成中/过期动作 |
| 项目管理 | `/projects`、`/projects/:projectId` | `ProjectsView` 267 行，详情由 `projectId` 加载 overview；详情仍引用已注释下线的协作路由名 | P1 | 保留 project workspace；清理失效导航契约并统一项目上下文注入 |
| AI 助手 | `/ai/:sessionId?` → `AIChatView.vue` → `AgentWorkspace.vue` | `fullscreen`；内有 AgentSidebar，活跃会话时 AgentSandbox 显示会话 header；消息、工具、审批、附件、流式事件由专用组件承担 | P1 | 保留 chat workspace；比较内外导航职责，统一消息宽度、tool card state 和错误反馈 |
| AI 工作台 | `/studio/:sessionId?` → `StudioView.vue` | `fullscreen`，约 1933 行；三栏工作区、会话、文件、终端、产物、研究模式 | P1 | 保留高密度三栏布局；拆 panel orchestration，建立稳定宽度/拖拽/窄屏契约 |
| 生信工具箱 | `/tools` + `/tools/*` → `ToolsHubView` 和工具 views | 工具列表和详情页路由多；壳层对 `/tools` 取消外层 padding；各工具 CSS 差异大 | P2 | 保留工具详情独立性；抽 ToolPageShell/ToolActionBar/ResultState |
| 关于 | `/about` → `AboutView.vue` | `autoCollapseSidebar`，1082 行，品牌/星空/动画和无障碍降级集中 | P2 | 保留 Immersive Brand Layout；统一 reduced motion/transparency 和可读性验收 |

页面通用交互情况：大部分页面有 loading 和 error 文案，报告/任务/流程已有局部空状态；未发现一套统一的全局错误恢复或跨页“继续任务”状态。浏览器实测未执行，因此 1920/1440/1280/1024/768/390 的实际截图结果待补。

## 6. Cross-Module Workflow Audit

### A. 公共数据发现

可从 `/treasure-mouse` 进入专用探索界面；数据下载提交后明确 `router.push('/tasks/:id')`（`DownloadsView.vue`），因此下载→任务中心可由代码验证。下载结果到文件管理的自动转化未找到同一处端到端调用，属于需要补充运行证据的链路。

### B. 已有数据分析

文件上传/选择通过 `FilesView`、`FilePickerModal` 和 AI 输入附件传递 `file_id`；流程提交在 `FlowSubmitView.vue:435-445` 组装参数后创建任务并跳任务详情；任务成功后 `TaskTable` 按 flow 分流到工具结果或 `/reports?taskId=`。这条主链路的 ID 传递已实现。文件空间按个人/团队切换，分析表单和下载页的项目关联应分别沿 API 契约继续核查；现有证据不足以概括所有入口是否传递项目上下文。

### C. 科研 Agent 工作流

AI 输入、SSE 流、工具调用、审批和任务卡由 `agentHub`、`KimiMessageItem`、`ApprovalCard`、`TaskProgressCard` 等实现；Studio 可从 AI 会话进入，也可从报告创建 session（`ReportsView.vue:114-120`）。参数确认和工具执行有组件证据，但“研究问题→项目/文件自动识别”的完整运行链需要集成/E2E 证据，本次未声称已验证。

### D. 项目与交付

项目详情按 `projectId` 加载，并显示关联会话/任务/报告入口；Agent 会话 DTO 持有 `project_id`，`agentHub` 在 chat stream 请求中传递该 ID；AgentSandbox 的新 Studio 会话提供项目选择，未选择时提示进入默认项目。Studio API 接受 `project_id`，报告优化则使用 `report_id` 建立新会话。可确认项目关联存在且按入口传递；没有 ProjectContext provider 是结构事实，但是否造成重复选择或上下文丢失尚未验证，不作为已确认缺陷。

### 状态和上下文问题

- 任务状态在任务表、AI 卡片、工作流 widgets、报告状态之间存在 `success/completed/generating/failed/cancelled` 多套词汇。
- 参考基因组和数据库存在别名路由；报告 flow filter 存在 `rna_seq` 与 `rna-seq` 重复值。
- AgentTeams 页面当前路由注释下线，但项目详情仍保留按 `agent-teams-room` 推送的代码路径，属于已确认的失效导航风险。

## 7. CSS & Component Technical Debt

| ID | 证据 | 影响 |
|---|---|---|
| CSS-01 | `tokens.css`、`global.css`、`chat-theme.css` 三层变量；`--brand-*`、`--stardust-*`、`--arco-*`、`--neutral-*` 并存 | 主题和品牌改色成本高 |
| CSS-02 | 全局 `.n-card/.arco-card/.cygnusx-card` 选择器及 `!important` 补丁 | 第三方升级和局部 scoped 样式容易互相覆盖 |
| CSS-03 | 约 132 个 `!important`、269 个 inline style、约 1,918 个颜色字面量匹配 | 难以静态推断最终样式 |
| CSS-04 | 275 个 Vue SFC，约 99 个超过 300 行；`StudioView`、`DefaultLayout`、`KimiMessageItem` 特别大 | 视觉、数据、交互改动耦合 |
| CSS-05 | `.page-container` 24px、token `--page-padding` 32px、工具/全屏 0px | 页面边界不统一 |
| CSS-06 | 任务表使用手写 SVG action icon，而其他页面大量使用 vicons | 图标语义、尺寸和 focus 行为不一致 |
| CSS-07 | `global.css` 设置 `overflow:hidden !important`；滚动由多层 layout 分担 | 小视口和嵌套面板容易出现滚动丢失 |
| CSS-08 | 旧路由被注释但业务视图仍调用命名路由 | 运行时导航失败，超出纯视觉问题 |

## 8. Responsive, Accessibility & Performance

### 已由源码确认

- 壳层断点为 `<1024` 折叠、`<768` 移动；多个页面增加 1180/1024/900/768/640/480 等局部断点。
- 全局提供 `prefers-reduced-motion` 和 `prefers-reduced-transparency` 的部分处理。
- 大量图标按钮已有 `aria-label`，Studio 返回、模型选择和聊天操作有 tooltip/label。
- `vue-virtual-scroller` 已安装并全局载入样式；AI/大列表是否全部采用需逐页确认。
- 路由页面普遍动态 import，统计到 72 个路由级动态入口。

### 潜在风险

- 无统一 `forced-colors: active` 规则，无仓库级 skip-to-content 入口证据。
- 自定义按钮、手写 SVG、拖拽分栏、聊天消息 action bar 和文件树需要逐页键盘 focus 顺序验收。
- 图表库、Monaco、CodeMirror、Plotly、ECharts GL 等重依赖虽按页面加载，但 Studio/工具页 chunk 仍可能很大。
- AI 流式消息渲染、Markdown 高亮和大量工具卡在长会话下可能造成重复渲染；现有单元测试不能证明长会话性能。

### 本轮未完成验证

未运行浏览器或 Playwright，不能声称已验证 1920、1440、1280、1024、768、390 视口的真实布局、对比度、横向滚动、模态尺寸或键盘操作。既有 `docs/frontend-design-audit-2026-07-26.md` 也明确未做真实浏览器截图和设备验证。

## 9. Proposed Design System

### 9.1 Foundation

保留当前 CSS variables 方向，但建立单一语义层：

```text
color.surface.base/card/elevated/interactive
color.text.primary/secondary/tertiary/on-primary
color.border.subtle/default/focus
color.brand.primary/hover/active/soft
color.status.success/warning/error/info (+ on + soft)
space.1..8 = 4/8/12/16/20/24/32/40px
type.display/page/section/card/body/small/caption/mono
radius.none/sm/md/lg/pill
shadow.none/sm/card/overlay
motion.fast/standard/emphasis + reduced-motion fallback
layout.header-height/sidebar-width/sidebar-collapsed/page-padding/content-max
z.base/sticky/dropdown/modal/toast
breakpoint.mobile=768/tablet=1024/wide=1440
```

`stardust`、`arco`、`kimi`、`studio` 只能作为品牌/域 alias，不能再直接定义第二套 surface、status 或 typography。

### 9.2 基础组件层

以 Naive UI 为实现基础，增加少量平台 wrapper：`CxButton`、`CxField`、`CxPageHeader`、`CxDataTable`、`CxStatus`、`CxEmptyState`、`CxLoadingState`、`CxErrorState`、`CxModal`、`CxDrawer`。wrapper 只固化 token、语义变体、ARIA 和测试钩子，不复制 Naive UI 行为。

### 9.3 科研业务组件层

优先抽取 `DatasetCard`、`FileCard`、`ProjectCard`、`AnalysisTaskCard`、`WorkflowStatus`、`ReportPreview`、`EvidenceCard`、`AgentExecutionCard`、`ParameterConfirmation`、`ProvenanceView`。这些组件接收统一 DTO，页面负责 API 转换，避免让 UI 组件同时理解多套后端状态名。

### 9.4 Layout 层

- `AppShellLayout`：Header/Sidebar/权限/通知。
- `StandardPageLayout`：PageHeader、24/32px page padding、错误/空/加载槽。
- `DataExplorerLayout`：文件树 + 主面板 + detail drawer。
- `ChatWorkspaceLayout`：会话栏 + 消息区 + composer。
- `StudioWorkspaceLayout`：三栏、拖拽宽度、窄屏 drawer、工作区滚动。
- `ReportViewerLayout`：报告预览、来源、下载、任务回链。
- `ImmersiveBrandLayout`：寻宝鼠/关于页，保留子品牌和星空视觉。

### 9.5 子品牌策略

科研寻宝鼠只覆盖 `color.brand.accent`、插画/背景和语气，继承基础 surface、focus、错误和控件尺寸。BioReport 使用阅读布局和打印 token。Studio 使用同一 foundation，但允许高密度、三栏和终端 surface。

## 10. Prioritized Issue Backlog

| ID | 问题 | 代码证据 | 影响页面 | 优先级 | 修改规模 | 风险 | 阶段 |
|---|---|---|---|---|---|---|---|
| P2-07 | 路由 chunk 失败恢复路径未验证 | `App.vue` 有 `AppErrorBoundary`；`main.ts` 无 errorHandler、router 无 `onError`；实际失败行为未复现 | 全部 | P2（待验证） | 小至中 | 中 | Phase 1 |
| P1-02 | Token 与硬编码样式并存 | `tokens.css`、`global.css`、局部 CSS；约 132 `!important` | 全部，重点 AI/Studio | P1 | 大 | 中 | Phase 1 |
| P2-01 | 工作区布局契约不同，复用边界待评估 | 全局壳层持续存在；AI 有 AgentSidebar/session header，Studio 有 topbar，寻宝鼠内部是未审计 iframe 应用 | 寻宝鼠/文件/AI/Studio | P2 | 中 | 中 | Phase 2 |
| P1-03 | 任务状态和结果入口多套语义 | `TaskTable`、`ReportCard`、AI cards | 任务/报告/工具/监控 | P1 | 中 | 中 | Phase 2 |
| P1-04 | 超大 SFC 阻碍治理 | Studio 1933 行、DefaultLayout 约 1400 行、聊天组件约 1500 行 | 壳层/AI/Studio | P1 | 大 | 高 | Phase 3 |
| P2-02 | 项目关联按入口传递，产品一致性待核实 | Agent session 持有并传递 `project_id`；Studio 新会话允许选择或进入默认项目 | 项目/文件/AI/Studio | P2（未证实为缺陷） | 中 | 中 | Phase 3 |
| P1-05 | 注释下线路由仍被 push | `ProjectDetailView.vue` 推 `agent-teams-room` | 项目详情 | P1 | 小 | 低 | Phase 1 |
| P2-03 | 普通页/工具页/全屏页内容 padding 不同 | `DefaultLayout.vue:117-130` | 全部 | P2 | 中 | 中 | Phase 2 |
| P2-04 | forced colors/skip link 缺少全局实现证据 | 全局样式未检出 forced-colors；源码检索未确认 skip link | 全部 | P2（待人工验证） | 小 | 低 | Phase 1 |
| P2-05 | 数据库、flow ID 和状态命名漂移 | 路由别名、报告重复 flow option | 数据库/分析/报告 | P2 | 小 | 低 | Phase 2 |
| P2-06 | 手写 SVG 与 vicons 混用 | `TaskTable.vue:339-354` | 任务、工具 | P2 | 小 | 低 | Phase 3 |
| P3-01 | 品牌/动效细节缺少统一验收 | Home/About/Studio 局部动画 | 首页/关于/工作区 | P3 | 中 | 中 | Phase 4 |
| P3-02 | 页面级 inline style 和颜色字面量 | 静态计数 269/约 1,918 | 全部 | P3 | 大 | 中 | Phase 3 |

## 11. Refactoring Roadmap

### Phase 1 - 基础整理

- 目标：冻结语义 token，验证路由加载失败恢复路径，补齐无障碍基础并确认 canonical route。
- 文件：`src/styles/tokens.css`、`global.css`、`main.ts`、`router/index.ts`、`AppErrorBoundary.vue`、`ProjectDetailView.vue`。
- 验收：`npm run type-check`、`npm test`、`npm run build`；动态 import 失败可重试；forced colors 和 skip link 有测试或人工证据。
- 风险/回滚：中；按 token/错误边界/路由拆独立提交，可逐个回滚。

### Phase 2 - 壳层和导航

- 目标：建立 registry 驱动的 top/side/mobile 导航，推出 `StandardPageLayout`、`WorkspaceLayout`，统一滚动和 page padding。
- 文件：`DefaultLayout.vue`、新 layout 组件、`PageHeader.vue`、`EmptyState.vue`、模块 registry projection。
- 验收：六个目标视口、明暗主题、锁定模块和移动 drawer；导航配置只需单点登记。
- 风险/回滚：中高；先只迁移首页/仪表板/任务，不触碰 AI/Studio 内部布局。

### Phase 3 - 高频科研链路迁移

- 目标：先处理文件→下载→任务→报告→Studio，以及项目上下文和统一状态。
- 文件：`FilesView.vue`、`DownloadsView.vue`、`TasksView.vue`、`TaskTable.vue`、`ReportsView.vue`、`StudioView.vue`、相关 stores/types。
- 验收：使用真实 ID 深链回跳、任务状态一致、报告 provenance、文件附件和项目上下文不丢失；现有 unit/e2e 通过。
- 风险/回滚：高；每条链路独立 PR，先加适配器再替换视觉组件。

### Phase 4 - 高级体验

- 目标：无障碍逐页验收、流式长会话性能、子品牌视觉、打印/报告阅读和微交互。
- 文件：AI/Studio/寻宝鼠/About 相关组件与性能测试。
- 验收：Playwright 视口矩阵、键盘、reduced motion/transparency、forced colors、长会话和大表格性能。
- 风险/回滚：中；只在基础 token 和布局稳定后执行。

## 12. Open Questions

1. 顶部导航和侧边导航是否应由 `data/MODULE_LOCKED.yaml` 或前端模块 registry 的同一投影生成？
2. `database` 与 `reference-genomes`、`/database/:id` 与 `/reference-genomes/:id` 哪个是 canonical URL？
3. AgentTeams 路由暂时下线是永久产品决策还是短期 feature flag？项目详情的跳转代码应保留到何时？
4. 文件、下载、任务和 AI 会话是否必须绑定 project；未选择项目时产品允许的默认边界是什么？
5. 任务状态的后端权威枚举是什么，`completed` 和 `success` 是否应该统一为一个前端显示层？
6. 深色主题是否为默认正式主题；浅色主题和 Studio 的浅色 surface 是否需要完全等价？
7. 寻宝鼠绿色、BioReport 阅读模式和 Studio 高密度面板需要哪些品牌差异，哪些必须继承基础 token？
8. 浏览器验收是否采用 Playwright；目标设备矩阵和可接受的首屏/chunk 性能预算是什么？

## 13. Recommended First Batch

1. **验证并补足路由 chunk 恢复**：先实测动态 import 失败时 `AppErrorBoundary` 的表现，再决定是否需改 `main.ts`/router；不改变业务 API，适合独立小 PR。
2. **冻结语义 token 命名**：先补 surface/text/status/focus/spacing/layout token，再迁移 2-3 个热点；不先扩大 `!important` 补丁；适合独立小 PR。
3. **修复失效 AgentTeams 导航引用**：项目详情在路由下线时提供安全回退或隐藏入口；影响小，适合独立小 PR。
4. **统一任务状态和结果入口适配器**：`TaskTable`、AI 任务卡、报告卡共享显示层；保留后端字段差异；需要 unit tests，适合独立 PR。
5. **评估工作区共享契约**：先取得寻宝鼠 iframe 子应用源码/运行证据，再比较文件、AI、Studio 的 Header、Sidebar 和滚动职责；确认重复部分后再抽共享布局。
6. **拆分 FilesView**：拆 FileTree、FileDetail、Preview、Upload 状态，保持 `file_id` 和 API 不变；用现有组件测试和窄屏手测验证。
7. **规范报告/任务 provenance**：从 `/reports?taskId=`、任务详情和 Studio 报告 session 建立统一来源入口；验证深链和返回上下文。
8. **增加 forced-colors、skip link 和焦点验收**：覆盖壳层、模态、抽屉、图标按钮；适合独立可访问性 PR。

### 审计边界

本文件是只读审计和规划产物。已核实现状与明确标注为建议的路线图同步回写至活动架构文档 `ARCHITECTURE_DESIGN/CygnusX_frontend.md` §38。未修改前端源码、CSS、依赖、锁文件、路由或业务数据；未创建提交或 PR。构建、类型检查、测试和真实浏览器矩阵应在进入实施阶段后按仓库门禁执行。

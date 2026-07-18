# OmicHub 前端设计系统与实现规范

> **用途**：这是 OmicHub 的前端视觉、交互和实现基线。新增页面、组件及样式改动必须以此文档和现有设计令牌为准。它同时可作为其它科学计算、数据平台或工作台类 Vue 项目的迁移参考。
>
> **使用方式**：先阅读“技术边界”和“页面配方”，再按“实施流程”和“验收清单”完成实现。业务组件只消费语义令牌与共享模式；新增全局规则时，必须同步更新本文件及相应源文件。

## 1. 设计目标与非协商原则

OmicHub 是面向生物信息学任务、数据资产与 AI 工作流的科学工作台。界面应传达**平静、清晰、可靠、可控**，而非追求装饰性。

1. **目的明确**：每个控件只服务一个主要任务；优先展示高频路径，复杂选项下沉。
2. **即时反馈**：按下、悬停、聚焦、加载、完成和失败都有即时且可理解的反馈；不等待操作结束才改变界面。
3. **空间一致**：同类对象使用同一圆角、间距、状态色和进入/退出路径；出现的位置决定它消失的方向。
4. **材质有层级**：页面、卡片、浮层、玻璃导航按层级区分；不通过堆叠重阴影或多层玻璃制造层次。
5. **动效克制且可打断**：普通状态变化使用短过渡；只有直接手势控制的抽屉、拖拽或面板才使用可中断的弹簧动效。
6. **可访问性默认交付**：键盘焦点、减少动态、减少透明度、高对比度、文本状态与窄屏布局不是可选项。
7. **真实状态优先**：系统健康、任务进度、权限和错误不能只靠颜色或乐观文案表达；必须与接口状态和加载状态同步。

## 2. 技术边界与权威来源

### 2.1 当前技术栈

| 范畴 | 当前选择 | 规则 |
| --- | --- | --- |
| 框架 | Vue 3 + TypeScript + Vite | 新组件使用 `<script setup lang="ts">` 与 Composition API。 |
| 组件库 | Naive UI | 新控件优先使用 `NButton`、`NForm`、`NDataTable` 等现有 Naive UI 组件。 |
| 图标 | `@vicons/*` | 使用与现有页面一致的图标集；图标按钮必须提供 Tooltip 或可访问名称。 |
| 样式 | CSS 变量、Tailwind CSS、Sass | 页面优先消费变量和共享工具类；不要复制常量。 |
| 主题 | Pinia 主题状态 + Naive UI `themeOverrides` | 主题由应用层统一提供，业务页面不得覆写全局组件主题。 |

### 2.2 不混用组件库

本仓库**不安装或混用** `@arco-design/web-vue`。`--arco-*` 是历史兼容的设计令牌命名，并不代表页面应使用 `a-*` 组件。

- 在 OmicHub 中：继续使用 Naive UI，并通过 `frontend/src/App.vue` 的 `themeOverrides` 统一主题。
- 在新平台中：可选择 Arco Design Vue，使用 `<a-button>`、`<a-table>`、`<a-form>` 等组件，并将本规范中的语义令牌映射到 Arco 主题；不要在同一应用同时引入 Naive UI 与 Arco Design Vue。
- 迁移到 Arco 时：先完成全局注册、主题、语言和图标策略，再逐页替换。不要只替换单个按钮或表格。

### 2.3 权威实现位置

| 主题 | 权威实现 | 使用规则 |
| --- | --- | --- |
| 品牌令牌、明暗主题基础值 | `frontend/src/styles/tokens.css` | 修改品牌、背景或文本基础值时在这里处理明暗成对变量。 |
| 全局语义变量、交互、辅助类 | `frontend/src/styles/global.css` | 业务样式优先使用其中变量、`card-hover`、`focus-ring` 等共享模式。 |
| Naive UI 主题覆盖 | `frontend/src/App.vue` | Naive UI 的色彩、圆角、菜单和组件基础外观只在此维护。 |
| 主框架、顶部栏、侧栏 | `frontend/src/layouts/DefaultLayout.vue` | 新导航或壳层变更遵循已有折叠、移动端和滚动规则。 |
| 通用页头 | `frontend/src/components/PageHeader.vue` | 统一标题、说明和右侧操作区；不要在页面重复造页头。 |
| 仪表盘实时状态模式 | `frontend/src/views/DashboardView.vue` | 系统健康、局部刷新、任务列表与进度条的推荐实现。 |
| 认证页材质与引言 | `frontend/src/views/LoginView.vue`、`frontend/src/views/RegisterView.vue`、`frontend/src/components/StardustQuote.vue` | 认证场景可使用星空和玻璃材质，普通工作台页面保持克制。 |

### 2.4 Naive UI 应用层约定

- `frontend/src/main.ts` 负责注册 Naive UI；不要为单个页面重复安装组件库或引入第二套全局初始化方式。
- `frontend/src/App.vue` 是唯一的 `NConfigProvider` 与 `themeOverrides` 维护入口。语言、日期语言、明暗主题、通用色彩、圆角及组件级覆盖必须在此集中配置，业务页面不得嵌套新的全局主题提供者。
- `NMessageProvider`、`NDialogProvider` 与 `NNotificationProvider` 已在应用根部提供。`useMessage()`、`useDialog()`、`useNotification()` 只能在这些 Provider 的后代组件或组合式函数调用；需要新增 Provider 时，先说明其覆盖范围和全局影响。
- 本项目当前采用显式导入与全局注册的既有方式。未经构建体积、类型声明和现有代码验证，不要仅为局部页面迁移到自动导入或实验性 Naive UI 功能。
- Tailwind 基础样式、全局 CSS 与 Naive UI 外观发生冲突时，先检查 `global.css` 的选择器和加载顺序；不要用高优先级、深层穿透或 `!important` 批量覆盖 `n-*` 组件。确需控制 Naive UI 样式注入位置或禁用其 preflight 时，应作为应用层变更处理并验证所有页面。

## 3. 设计令牌

### 3.1 令牌使用规则

- 业务组件只使用语义变量，例如 `--neutral-card`、`--neutral-text-2`、`--arco-primary`；不要在 `.vue` 局部样式中硬编码浅色模式色值。
- 新令牌先定义在 `tokens.css` 或 `global.css`，并补全深色模式；再在业务组件中消费。
- 图表沿 `--kimi-chart-1` 至 `--kimi-chart-6` 的顺序取色；进度轨道使用 `--neutral-border`。
- 当组件库 API 需要字符串颜色时，允许传入 `var(--token-name)`，例如 `railColor: 'var(--neutral-border)'`。

### 3.2 色彩

| 语义 | 首选变量 | 浅色基准 | 深色基准/说明 |
| --- | --- | --- | --- |
| 主操作 | `--arco-primary` / `--brand-primary` | `#4C6FFF` | 使用 `#7691FF`；悬停/按下使用对应 `hover`、`active` 变量。 |
| 成功 | `--arco-success` | `#00B42A` | 深色组件使用可读的成功绿；同时提供成功文本或图标。 |
| 警告 | `--arco-warning` | `#FF7D00` | 用于可恢复风险、排队或注意事项。 |
| 错误 | `--arco-danger` | `#F53F3F` | 用于失败、不可用和破坏性操作；不能只用红色表达。 |
| 页面背景 | `--neutral-bg` | `#F5F6FA` | `#0B0F19`。 |
| 卡片/弹窗表面 | `--neutral-card` | `#FFFFFF` | `#151A25`。 |
| 一级文本 | `--neutral-text-1` | `#1D2129` | `#F2F3F8`。 |
| 二级文本 | `--neutral-text-2` | `#4E5969` | `#B8BCC8`。 |
| 辅助文本 | `--neutral-text-3` | `#86909C` | `#7A8194`。 |
| 边框/轨道 | `--neutral-border` | `#E5E6EB` | `#2A3040`。 |
| 悬停底色 | `--neutral-hover` | `#F2F3F8` | 使用深色主题的语义变量或半透明主色。 |

### 3.3 间距、圆角、阴影与排版

| 类别 | 规定 |
| --- | --- |
| 间距阶梯 | 仅使用 `4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48px`，对应 `--space-xs` 至 `--space-5xl`。 |
| 页面内边距 | 默认 `--page-padding: 32px`；密集工具页或窄屏可使用 `16px`。 |
| 卡片 | 默认内边距 `24px`、卡片间距 `20px`；紧凑工具卡片可使用 `12px`。 |
| 圆角 | 常规控件 `8px`、小控件 `4px`、卡片 `12px`、大型面板/认证卡片 `16px`、状态胶囊 `9999px`。 |
| 阴影 | 卡片使用 `--shadow-card` 或 `--shadow-soft`；悬停使用 `--shadow-card-hover`；下拉与弹出层使用 `--shadow-dropdown`。 |
| 字体 | `Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica Neue, Arial, Noto Sans SC, PingFang SC, Microsoft YaHei, sans-serif`。 |

| 文本层级 | 字号 / 行高 | 字重 | 字距 |
| --- | --- | --- | --- |
| Display | `28px / 36px` | 600 | `-0.02em` |
| 页面标题 | `24px / 32px` | 600 | `-0.02em` |
| 区块标题 | `18px / 28px` | 600 | `-0.01em` |
| 卡片标题 | `16px / 24px` | 500 | 默认 |
| 正文 | `14px / 22px` | 400 | 默认 |
| 小正文 | `13px / 20px` | 400 | 默认 |
| 说明文字 | `12px / 18px` | 400 | 默认 |

大标题使用轻微负字距；正文和小字号不压缩字距。层级由字号、字重、行高和色阶共同建立，不只依赖字号。

## 4. 页面结构与材质层级

### 4.1 标准工作台页面配方

按以下顺序组织大多数业务页面：

1. `.page-container` 或页面根元素：提供页面背景、最小高度和 `--page-padding`。
2. `PageHeader`：标题、简短说明和 `#actions` 插槽中的页面级操作。
3. 信息横幅或筛选区：仅在确实影响当前任务时显示。
4. 主内容卡片/网格：采用 `16px` 或 `20px` 间距；页面区块以 `24px` 或 `32px` 分隔。
5. 结果表格、空状态或下一步操作：为首次使用和无数据场景提供明确路径。

页面级刷新、导出、新建等操作放在 `PageHeader` 的 `#actions` 中。卡片内部只放影响该卡片本身的操作，避免同一动作在页面和卡片中重复。

```vue
<PageHeader title="任务中心" subtitle="查看和管理正在运行的分析任务">
  <template #actions>
    <NButton secondary :loading="refreshing" @click="refreshTasks">
      刷新数据
    </NButton>
    <NButton type="primary" @click="createTask">提交任务</NButton>
  </template>
</PageHeader>
```

### 4.2 材质和玻璃表面

1. 页面底层使用 `--neutral-bg`。
2. 常规信息承载在 `--neutral-card` 卡片上，配合 `--neutral-border` 与克制阴影。
3. 顶栏、侧栏和认证场景可使用玻璃材质：半透明背景、`backdrop-filter`、细边界或内高光。
4. 普通内容卡片不叠加玻璃效果；不要在玻璃表面上再放一层浅色玻璃表面。
5. 模态任务使用遮罩与实体表面；并行、非阻塞面板可使用半透明与偏移，不必强制遮罩。

在 `prefers-reduced-transparency: reduce` 下，玻璃表面必须回退到 `--neutral-card` 实色背景并移除模糊。

## 5. 组件实现契约

### 5.1 按钮、链接与图标

| 类型 | 使用方式 |
| --- | --- |
| 主要动作 | `NButton type="primary"`；每个视觉区域通常只有一个主要动作。 |
| 次要动作 | `NButton secondary`、`tertiary` 或 `text`；不要用多个实心主按钮竞争注意力。 |
| 危险动作 | 使用 `type="error"`，并在不可逆或会清理数据时使用 `NPopconfirm` / `NModal`。 |
| 图标按钮 | 使用圆形/弱化按钮；必须有 `NTooltip` 或 `aria-label`。 |
| 页面刷新 | 使用按钮 `:loading` 表示请求中；禁止 `$router.go(0)` 或 `window.location.reload()`。 |

全局按压反馈已经通过共享样式提供轻微缩放。自定义按钮不得将按压缩放扩大为弹跳，不得在过渡期间禁止用户再次操作。

### 5.2 卡片

- 使用 `NCard` 或已有 `.arco-card` / `.omichub-card` 外观模式；新卡片优先复用 `NCard`。
- 卡片标题使用 `16px / 24px / 500`；卡片内信息按 `8px`、`12px`、`16px` 阶梯分组。
- 可点击卡片应有 hover、active、focus-visible 和 selected 状态；悬停位移不超过 `2px`。
- 只要卡片本身可点击，就不要在内部塞满冲突的次级点击区域；必要时使用显式操作菜单。

#### 可选择卡片协议

- 所有会保留选择结果的卡片使用 `.omichub-selectable-card`；已选项同时使用 `.is-selected`，或以 `aria-selected="true"`、`aria-checked="true"`、`data-selected="true"` 表达状态。
- 共享规则位于 `frontend/src/styles/global.css`：选中态使用完整、连续的主色内描边与左缘短状态线；状态线只用于已选项，hover 仅显示低强调预览。不要用状态线替代完整边框。
- 单选卡使用 `role="radiogroup"` / `role="radio"` 和 `aria-checked`；列表型选项使用 `role="listbox"` / `role="option"` 和 `aria-selected`。自定义卡片必须支持 `Enter` 与 `Space` 触发选择。
- 已选状态还必须通过现有标签、单选标记或文字说明表达；色彩与状态线不能是唯一的信息来源。

### 5.3 表单与输入

- 统一使用 `NForm`、`NFormItem`、`:model` 和规则校验；字段使用 `v-model`。
- 标签描述输入目的，辅助文本说明格式或副作用，错误文案放在对应字段附近。
- `required`、`disabled`、`loading`、`error` 和成功反馈都必须有可见状态。
- 两列表单在窄屏降为单列；长表单允许纵向滚动，禁止固定 `100vh` 后裁剪内容。
- 日期时间逻辑保持现有项目依赖；不要为单页额外引入重复日期库。
- 表单提交前调用 `FormInst.validate()`；简单字段通常在 `input` 与 `blur` 触发校验，涉及远端检查的异步校验优先在 `blur` 或显式操作后触发，避免每次输入都产生请求。
- 动态数组和嵌套对象必须使用稳定、可定位的 `path`，例如 `samples[${index}].name` 或 `metadata.projectName`；删除、重排或替换字段后，应同步更新模型、规则和错误状态。
- `v-model` 是受控模式：组件值、可选项和加载状态由页面状态统一维护。需要清空受控字段时使用组件接受的空值（通常是 `null`、空字符串或空数组），不要把受控值设为 `undefined` 以免意外切换为非受控模式。
- 远程 `NSelect` 应区分首次加载、关键词搜索和无结果状态；请求需防止旧响应覆盖新关键词结果，并在 `loading` 时保留已选值。多选、大选项集或可创建标签时，必须限制渲染量并清楚说明新值如何保存。
- `NUpload` 必须在客户端和服务端校验类型、大小与权限。需由用户确认后再提交的表单使用 `:default-upload="false"`；自定义上传请求必须报告进度、在成功/失败时调用对应回调，并为失败文件提供重试或移除入口。

### 5.4 数据表格、空状态与反馈

- 使用 `NDataTable`；列标题为 `12px` 辅助色，单元格为 `13px` 主文本色，行 hover 使用 `--neutral-hover`。
- 长标识符、路径和标题必须启用省略与 Tooltip，避免撑破布局。
- 任务状态使用 `NTag`，进度使用 `NProgress`；颜色必须来自语义令牌，轨道使用 `var(--neutral-border)`。
- 加载采用 `NSpin` 或 `NSkeleton`；无数据采用 `NEmpty`，并给出下一步按钮或解释。
- 成功、警告、错误消息使用 `useMessage()`；长期或富内容反馈使用 Notification / Result，不要把所有信息塞进 toast。
- 远程表格将页码、页大小、排序、筛选和关键词收敛为单一查询状态，由可重复调用的 `load*` 函数请求数据；切页、排序和筛选只更新该状态并局部刷新，不重载路由或丢失用户上下文。
- 表格行必须提供稳定唯一的 `row-key`。选择、展开和筛选若需要跨局部刷新保留，使用受控状态；数据更新后应明确移除已不存在行的选择，不能静默指向错误记录。
- 仅在数据量大且表格容器高度可预测时启用 `virtual-scroll`；虚拟表格避免不稳定行高、自动换行的大段内容和依赖完整 DOM 的交互。无法满足这些条件时，采用后端分页、列精简或独立详情页。
- 异步树和超长选项列表应按需加载并使用稳定键；展开、勾选和已加载节点与远端数据分开维护。不要一次性将完整层级或数万选项渲染到 DOM。
- 表格初次加载优先使用贴近列结构的 `NSkeleton`，局部刷新使用表格区域内的 `NSpin` 或按钮 `loading`；失败时保留可理解的上下文、重试入口和已成功加载的数据，而非用空白替换整个页面。

### 5.5 状态与实时数据卡片

运行状态卡片必须同时表达**文本、颜色、加载或异常语义**：

| 状态 | 文本 | 色彩 | 动效 | 行为 |
| --- | --- | --- | --- | --- |
| 检测中 | `检测中…` | 主色 | 低频脉冲 | 禁止展示旧的成功状态。 |
| 正常 | `系统运行正常` | 成功色 | 允许低频脉冲 | 刷新成功后显示最新结果。 |
| 异常 | `异常` / `后端未连接` | 错误色 | 停止循环脉冲 | 提供可重试入口；不误导为成功。 |

数据刷新应重新请求当前页面所需资源，保持滚动位置、筛选与页面上下文。刷新按钮本身展示 `:loading`，并用消息反馈结果。可按以下模式实现：

```ts
const refreshing = ref(false)

async function refreshDashboard() {
  if (refreshing.value) return
  refreshing.value = true
  await loadDashboard()
  refreshing.value = false
  message[healthOk.value ? 'success' : 'warning'](
    healthOk.value ? '仪表板已更新' : '部分平台状态暂不可用，请稍后重试',
  )
}
```

动态状态文本使用 `aria-live="polite"`；状态点仅作辅助，应使用 `aria-hidden="true"`，避免屏幕阅读器重复朗读装饰。

### 5.6 导航、弹窗与认证页

- 顶部导航和侧栏是持久化空间锚点；同一导航项在所有状态下保持相同位置和高亮逻辑。
- 菜单展开、收起、进入和退出遵循同一路径；移动端抽屉支持关闭、键盘逃逸和焦点管理。
- 普通确认使用 `NPopconfirm`；复杂表单或需要更多上下文时使用 `NModal` 或 `NDrawer`。
- 认证页可以使用星空、玻璃卡片、引言和低对比度装饰，但必须在减少透明度/动态模式下回退，并保证正文对比度。
- `NModal`、`NDrawer` 和受控 `NPopconfirm` 使用 `v-model:show` 管理可见性；打开时应将焦点落在标题、首个可操作项或表单首字段，关闭后将焦点返回触发元素。异步确认期间使用按钮 `loading` 并阻止重复提交。
- 短暂、可逆的操作结果使用 `useMessage()`；需要说明原因、提供链接或持续可见的系统事件使用 `useNotification()`、`NAlert` 或 `NResult`。破坏性操作必须先通过 `NPopconfirm` 或包含后果说明的弹窗确认，不能只依赖红色按钮。

## 6. 动效与交互

### 6.1 时间与属性

```css
--motion-quick: 140ms;
--motion-standard: 220ms;
--motion-spring: cubic-bezier(0.2, 0.8, 0.2, 1);
```

- 颜色、边框、焦点和轻微阴影：`140ms` 至 `180ms ease-out`。
- 卡片、导航宽度、面板材质变化：`220ms var(--motion-spring)`。
- 仅动画 `transform` 与 `opacity`；避免用布局属性造成卡顿。
- 悬停以颜色和阴影为主，位移最多 `2px`；`card-hover-lift` 是遗留兼容类，新页面优先用 `card-hover`。
- 普通按钮/菜单禁止无因的回弹、循环位移、长延迟和庆祝性动效。

### 6.2 手势和空间连续性

- 直接拖拽对象必须使用 Pointer Events、指针捕获、1:1 跟随和释放速度衔接。
- 抽屉、底部面板等可手势控制对象使用可中断弹簧；默认临界阻尼、无过冲，只有快速甩动才允许轻微回弹。
- 可逆转场从当前呈现位置继续，而不是从旧目标值跳变；进入和退出遵循同一路径。
- 不要给普通表单、列表刷新或静态卡片加入弹簧或无限循环动画。

### 6.3 减少动态

`prefers-reduced-motion: reduce` 下：取消循环、漂浮、弹跳和大位移，保留极短的颜色/透明度反馈。状态脉冲应变为静态弱晕染；路由转场应变为短暂淡入淡出。

## 7. 响应式与可访问性

### 7.1 响应式规则

- 页面优先保证可读和可操作，再缩减留白。
- 工具页在 `1200px` 以下将三列布局降为单列或两列；常规双栏在 `1024px` 以下降为单列。
- 页面内边距在 `768px` 以下通常降至 `16px`。
- `640px` 以下的页头操作区换行并占满可用宽度；触控目标保持足够尺寸。
- 允许表格水平滚动或选择简化列，禁止通过压缩文字破坏可读性。

### 7.2 可访问性最低要求

1. 所有键盘可操作元素保留 `2px solid var(--arco-primary)`、`3px` 外偏移的 `:focus-visible` 焦点环。
2. 任何仅靠颜色表达的内容都额外提供文字、图标、位置或 ARIA 语义。
3. 图标按钮提供 Tooltip 或 `aria-label`；加载状态使用组件 `loading` 属性，动态文本使用恰当 `aria-live`。
4. `prefers-reduced-transparency: reduce` 下移除模糊并使用实体背景；`prefers-contrast: more` 下增强焦点环、边界和文本对比。
5. 保持原生语义：页面标题用单个 `h1`，卡片区块按需使用 `section` 和 `h2/h3`，不要仅用 `div` 模拟交互控件。
6. 可选择卡片在状态变化后同步更新 `.is-selected` 与对应 ARIA / `data-selected` 属性；键盘触发路径必须与鼠标点击一致。

## 8. 跨平台迁移策略

将本规范用于新平台时，按以下顺序迁移，而非复制局部 CSS：

1. **建立令牌层**：先创建品牌、明暗主题、文本、边框、间距、圆角、阴影与动效令牌。
2. **选定单一组件库**：OmicHub 使用 Naive UI；新 Vue 平台可选择 Arco Design Vue，但不得混用。
3. **配置应用层主题**：在入口注册组件库、全局语言、主题和图标；将主色、圆角、背景与表面映射到令牌。
4. **建立壳层**：先完成顶部栏、侧边栏、移动端抽屉和统一页头，再开发业务页面。
5. **沉淀页面配方**：实现仪表盘、列表/表格、详情、表单、空状态和错误状态的标准模板。
6. **最后接入业务接口**：加载、重试、部分失败和权限状态必须按本规范呈现。

### 8.1 Naive UI 与 Arco Design Vue 对照

| 场景 | OmicHub（Naive UI） | 新平台如选择 Arco Design Vue |
| --- | --- | --- |
| 主按钮 | `NButton type="primary"` | `<a-button type="primary">` |
| 表单 | `NForm` + `NFormItem` | `<a-form>` + `<a-form-item>` |
| 数据表格 | `NDataTable` | `<a-table>` |
| 提示 | `useMessage()` | `Message` 服务 |
| 弹窗 | `NModal` / `NPopconfirm` | `<a-modal>` / `<a-popconfirm>` |
| 全局主题 | `NConfigProvider` + `themeOverrides` | `app.use(ArcoVue)` + `<a-config-provider>` / Arco 主题变量 |

Arco 项目遵守 Vue 3 `<script setup lang="ts">`、kebab-case 模板属性、`v-model`、`#slot`、`dayjs` 日期处理和 Arco 图标入口的约定。该对照仅用于迁移决策，不是将 Arco 组件引入 OmicHub 的理由。

## 9. 实施流程

每次前端改动按以下流程执行：

1. **确认场景**：识别页面任务、目标用户、主要动作、失败状态和窄屏行为。
2. **复用现有组件**：先查 `PageHeader`、共享卡片、表格、空状态、认证页与全局工具类；避免重复实现。
3. **选择令牌**：只使用语义颜色、间距、圆角、阴影和排版变量；需要新变量时先补全明暗主题。
4. **实现完整状态**：至少覆盖 default、hover、active、focus-visible、disabled、loading、empty、error 和 success（适用时）。
5. **接入数据**：把接口请求收敛到可重复调用的 `load*` 函数；局部刷新调用该函数，而非重载整个路由。
6. **处理可访问性与响应式**：检查键盘、减少动态、减少透明度、高对比度、窄屏和长内容。
7. **验证**：运行 `npm run type-check` 与 `npm run build`；检查 `git diff --check`，并在可用时人工查看明暗主题与关键断点。
8. **同步文档**：若新增全局令牌、共享类、页面配方或交互模式，更新本文件并标注权威实现位置。

## 10. 变更验收清单

- [ ] 页面是否复用 `tokens.css`、`global.css` 与 `App.vue` 的主题体系？
- [ ] 是否只使用一个组件库，且没有将 Arco 与 Naive UI 混入同一应用？
- [ ] 是否复用了 `PageHeader`，并把页面级操作放入 `#actions`？
- [ ] 是否避免硬编码只适用于浅色模式的背景、边框、图表轨道和状态颜色？
- [ ] 按钮、卡片、输入和表格是否具备 hover、active、focus-visible、disabled、loading 和 error 等适用状态？
- [ ] 所有可选择卡片是否使用 `.omichub-selectable-card`，并提供连续选中描边、左缘状态线、文本或图标提示与键盘选择？
- [ ] 系统健康、进度和任务状态是否同时呈现文本、颜色与加载/错误语义？
- [ ] 刷新是否保持页面上下文，而不是使用整页重载？
- [ ] 是否处理了空状态、部分失败、权限不足和长文本溢出？
- [ ] 动效是否短促、必要、可中断，并在减少动态下安全回退？
- [ ] 是否验证了浅色、深色、窄屏、高对比度和键盘焦点？
- [ ] 是否通过 `npm run type-check`、`npm run build` 和 `git diff --check`？

## 11. 可复用 Skill 入口

本规范对应本机 Codex 技能 `$omichub-frontend-design`。技能入口保持简洁，完整参考保存在本文件；当令牌、共享组件或工作流变化时，先更新本文件，再同步技能引用副本。

建议的调用方式：

```text
使用 $omichub-frontend-design 优化此 Vue 工作台页面；沿用项目已有组件库和主题，先检查设计令牌、页面状态、响应式与可访问性，再实施并验证构建。
```

技能用于提供一致的实施流程，不替代具体仓库中的 `AGENTS.md`、前端架构说明或组件库文档；发生冲突时，以当前仓库的直接指令和实现为准。

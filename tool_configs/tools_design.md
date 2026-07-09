# OmicHub 生信工具箱 · 前端工具设计规范

> 本文档规定「生信工具箱」(`/tools`)下所有工具页面的架构、布局、样式、交互约定。
> 新增工具**必须遵循本规范**,以保证视觉一致、交互统一、维护成本低。
> 现有参考实现:火山图(`VolcanoPlotView.vue`)为最完整的样板,优先参照;BLAST / FASTQ 质控 / 绘图工坊 / KEGG 为次参照;JBrowse 为**全屏工具特例**,不作为紧凑布局参照。
>
> 最后更新:2026-07-06

---

## 一、设计目标

| 目标 | 含义 |
|------|------|
| **统一** | 所有工具页面的根容器、工具栏、参数面板、卡片、配色、组件选型一致 |
| **紧凑** | 核心工作区(图表/表格/结果)屏幕占比最大化,四周与卡片间留白最小化 |
| **主题适配** | 亮 / 暗模式开箱即用,颜色一律走 CSS 变量,禁止硬编码 |
| **可复用** | 纯前端工具与有后端的工具共用同一套页面壳,差异只在数据来源 |
| **可演进** | 改全局布局规范只需改本文档 + `DefaultLayout.vue`,不动各工具页 |

---

## 二、技术栈(强制)

- **框架**:Vue 3 `<script setup lang="ts">` + Vite + TypeScript(严格模式,`vue-tsc` 必须通过)
- **UI 库**:Naive UI(`naive-ui`)—— 组件一律从 `naive-ui` 具名导入,禁止用其他 UI 库
- **图标**:`@vicons/ionicons5`(仅此一个图标库)
- **科学图表**:Plotly.js(`plotly.js-dist-min`,适合散点/火山/热图等大数据量)
- **通用图表**:ECharts(`vue-echarts`,适合柱/折/箱线等)
- **路由**:Vue Router 4
- **状态**:Pinia(`useThemeStore` 取主题,`useAuthStore` 取鉴权)
- **HTTP**:`@/api/client`(已封装鉴权与错误处理的 axios 实例)

---

## 三、文件与目录组织

```
frontend/src/
├── views/BioTools/
│   ├── ToolsHubView.vue          # 工具箱列表页(唯一,不新增)
│   └── <Tool>View.vue            # 各工具页面(每工具一个 SFC, PascalCase)
├── utils/
│   └── <tool>Processor.ts        # 工具数据处理与图表配置(纯函数,无 Vue 依赖)
├── components/bio-tools/
│   └── ToolCard.vue              # 工具卡片(共用,不新增)
├── api/tools.ts                  # GET /tools 拉取工具列表(共用)
├── types/tools.ts                # ToolItem 类型(共用)
└── router/index.ts               # 注册 tools/<key> 子路由

tool_configs/                            # 仓库根,后端配置目录
├── tools_setting.yaml            # 工具箱前端注册表(卡片元数据)
└── <tool>/                       # 有后端配置的工具专用目录(如 jbrowse/、enrichments/)
```

### 命名约定

| 对象 | 规则 | 示例 |
|------|------|------|
| 视图文件 | `<Tool>View.vue`,PascalCase | `VolcanoPlotView.vue` |
| 处理器文件 | `<tool>Processor.ts`,camelCase | `volcanoProcessor.ts` |
| 路由 key | 小写连字符(kebab-case) | `fastq-qc`、`kegg-enrichment` |
| 根 class | `<key>-page` | `volcano-page`、`blast-page` |
| 布局 class | `<key>-layout` | `volcano-layout` |
| 路由 name | `tools-<key>` | `tools-volcano` |
| 路由 path | `tools/<key>` | `tools/volcano` |

> **key 一致性**:`tools_setting.yaml` 的 `key`、路由 `path` 的最后一段、根 class 前缀、路由 `name` 后缀,四处必须用同一个 kebab-case key。

---

## 四、新工具接入流程(强制 checklist)

新增一个工具,按顺序完成以下 5 步:

1. **后端注册**:在 `tool_configs/tools_setting.yaml` 的 `tools` 列表追加一项(字段见 §五)。
2. **前端路由**:在 `frontend/src/router/index.ts` 的 `DefaultLayout` children 内,仿照已有工具追加子路由(见 §五)。
3. **图标登记**(仅当用了新图标):在 `ToolsHubView.vue` 的 `ICON_MAP` 登记组件。YAML 的 `icon` 字段是字符串,Vue 组件不能由字符串动态 import,必须在此映射。
4. **后端功能配置**(仅有后端的工具):新建 `tool_configs/<tool>/` 目录放 YAML,并在 YAML 的 `config_dir` 指明。纯前端工具(如 plot/volcano/blast)留空。
5. **创建页面**:新建 `frontend/src/views/BioTools/<Tool>View.vue`,按 §六骨架实现;复杂数据逻辑抽到 `frontend/src/utils/<tool>Processor.ts`。

---

## 五、路由与注册规范

### 5.1 `tools_setting.yaml` 字段

```yaml
- key: "volcano"                         # 唯一标识,同时是路由 token,kebab-case
  title: "火山图绘制"                    # 卡片标题
  description: "差异表达结果可视化..."   # 卡片描述(一句话)
  icon: "BonfireOutline"                 # 图标字符串 key,须在 ICON_MAP 登记
  gradient: "linear-gradient(135deg, #F53F3F 0%, #FF7D00 100%)"  # 卡片图标渐变
  route: "/tools/volcano"                # 点击跳转路由,与 router path 一致
  enabled: true                          # false 则软下线,不出现在工具箱
  order: 45                              # 卡片排序,升序(10 的步长留间隔)
  config_dir: ""                         # 有后端配置填 "tool_configs/<tool>",纯前端留空
```

### 5.2 路由注册(`router/index.ts`)

```ts
{
  path: 'tools/<key>',
  name: 'tools-<key>',
  component: () => import('@/views/BioTools/<Tool>View.vue'),
  meta: { title: '<中文标题>', requiresAuth: true },
}
```

- 所有工具路由是 `DefaultLayout` 的 children,path 不带前导 `/`(相对父级 `/`)。
- `requiresAuth: true` 必填。
- **全屏工具**(如 JBrowse,需要占满视口、自带滚动)额外加 `meta: { fullscreen: true }`。全屏工具走 `DefaultLayout` 的 fullscreen 分支(`padding: 0`),**不适用本文档的紧凑布局规范**,其页面内部布局自理。详见 §十一。

### 5.3 图标登记(`ToolsHubView.vue`)

```ts
import { BonfireOutline, /* ... */ } from '@vicons/ionicons5'

const ICON_MAP: Record<string, Component> = {
  ScanOutline, SearchOutline, ColorPaletteOutline, LayersOutline,
  BarChartOutline, AppsOutline, BonfireOutline, // ← 新图标在此登记
}
```

未登记的 `icon` key 回退到 `AppsOutline`。

---

## 六、页面布局规范

### 6.1 标准页面骨架(紧凑布局)

```vue
<template>
  <div class="xxx-page">
    <!-- 1. 工具栏:返回 + 标题 + 操作 -->
    <div class="page-toolbar">
      <NButton text @click="router.push('/tools')">
        <template #icon><NIcon :size="18"><ArrowBackOutline /></NIcon></template>
        返回工具箱
      </NButton>
      <h1 class="page-title">工具标题</h1>
      <NButton size="small" quaternary @click="loadSample">
        <template #icon><NIcon><SparklesOutline /></NIcon></template>
        示例数据
      </NButton>
    </div>

    <!-- 2. 主体:左参数 + 中工作区 + 右辅助(可选) -->
    <div class="xxx-layout">
      <aside class="param-panel"><!-- NCollapse 参数 --></aside>
      <main class="work-area"><!-- 图表/结果 --></main>
      <aside class="side-panel"><!-- 统计/列表,可选 --></aside>
    </div>
  </div>
</template>
```

### 6.2 根容器与留白(强制值)

工具页面**不设外层 padding**——`DefaultLayout.vue` 的 `contentStyle` 已对 `/tools` 与 `/tools/*`(非全屏)设 `padding: 0`,由页面根自控单层 padding,避免双层留白。

```css
.xxx-page {
  padding: 16px;          /* 统一四周留白,禁止 > 20px */
  min-height: 100%;
}
.page-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;     /* 工具栏到主体间距,紧凑 */
}
.page-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--neutral-text-1, #1d2129);
  margin: 0;
  flex: 1;                /* 标题占满中间,把右侧操作按钮推到最右 */
}
.xxx-layout {
  display: grid;
  grid-template-columns: 300px 1fr 280px;  /* 左参数 / 中工作区 / 右辅助 */
  gap: 16px;              /* 卡片间距统一 16px */
  align-items: start;
}
```

- **两栏工具**(无右侧辅助):`grid-template-columns: 320px 1fr;`
- **单栏工具**(纯结果):`grid-template-columns: 1fr;`
- 左参数面板宽度建议 280–360px,右侧辅助 260–300px。

### 6.3 卡片样式(强制)

所有白色面板(参数面板、结果卡片、辅助面板)统一:

```css
.param-panel,
.work-card,
.side-panel {
  background: var(--neutral-card, #fff);
  border: 1px solid var(--neutral-border, #e5e6eb);
  border-radius: 12px;
  padding: 12px;          /* 卡片内边距 12px(参数面板);结果卡片 8–12px */
  max-height: calc(100vh - 120px);  /* 超出滚动,避免整页滚动 */
  overflow-y: auto;
}
```

### 6.4 响应式(强制)

```css
@media (max-width: 1200px) {
  .xxx-layout { grid-template-columns: 1fr; }  /* 三栏/两栏退化为单栏堆叠 */
  .param-panel, .side-panel { max-height: none; }
}
@media (max-width: 768px) {
  .xxx-page { padding: 12px; }
}
```

### 6.5 Plotly 图表容器

```css
.plot-card {
  position: relative;
  background: var(--neutral-card, #fff);
  border: 1px solid var(--neutral-border, #e5e6eb);
  border-radius: 12px;
  padding: 8px;
  min-height: 540px;       /* 图表可视高度 ≥ 540px */
}
.plot-container {
  width: 100%;
  height: 560px;           /* 固定高度,Plotly 需要明确尺寸 */
}
.plot-area.fullscreen .plot-container { height: calc(100vh - 120px); }
```

Plotly layout 的 `margin` 用紧凑值:`{ t: 40, r: 30, b: 60, l: 60 }`。

---

## 七、组件使用规范(Naive UI)

### 7.1 选型约定

| 场景 | 组件 | 关键 props |
|------|------|-----------|
| 参数折叠分组 | `NCollapse` + `NCollapseItem` | `arrow-placement="left"`, `:default-expanded-names="[...]"` |
| 数值输入 | `NInputNumber` | `:show-button="false"`, `size="small"`, `:step` 按字段语义 |
| 文本输入 | `NInput` | `size="small"` |
| 下拉选择 | `NSelect` | `size="small"`, options 形如 `{label, value}` |
| 开关 | `NSwitch` | `size="small"` |
| 单选互斥(模式) | `NRadioGroup` + `NRadioButton` | `size="small"` |
| 颜色 | `NColorPicker` | `:show-alpha="false"`, `size="small"` |
| 文件上传 | `NUpload` | `:default-upload="false"`, `:max="1"`, `accept` |
| 数据表格 | `NDataTable` | `:pagination="{pageSize:20}"`, `size="small"`, `:scroll-x` |
| 空状态 | `NEmpty` | 图表区无数据时占位 |
| 加载 | `NSpin` | 渲染中遮罩 |
| 统计数字 | `NStatistic` | 右侧统计面板 |
| 消息反馈 | `useMessage` | `message.success/error/warning/info` |

### 7.2 按钮层级(强制)

| 层级 | 用法 | 样式 |
|------|------|------|
| 主操作 | 「生成图表」「运行分析」等触发核心计算 | `type="primary"`, `size="small"`, 带 `:loading` |
| 次操作 | 导出 PNG/SVG、重置视图 | `size="tiny"`, `secondary` |
| 文字操作 | 返回工具箱、示例数据 | `text` 或 `quaternary` |

```vue
<NButton size="small" type="primary" :loading="plotting" @click="generate">
  <template #icon><NIcon><BarChartOutline /></NIcon></template>生成图表
</NButton>
<NButton size="tiny" secondary @click="exportImage('png')">PNG</NButton>
<NButton text @click="router.push('/tools')">返回工具箱</NButton>
```

### 7.3 图标导入

```ts
import { NIcon } from 'naive-ui'
import { ArrowBackOutline, BarChartOutline, DownloadOutline, SparklesOutline } from '@vicons/ionicons5'
```

---

## 八、样式与主题规范

### 8.1 CSS 变量(强制,禁止硬编码颜色)

| 变量 | 用途 | 亮色回退 |
|------|------|---------|
| `var(--neutral-bg)` | 页面灰底 | — |
| `var(--neutral-card)` | 卡片白底 | `#fff` |
| `var(--neutral-border)` | 边框 | `#e5e6eb` |
| `var(--neutral-text-1)` | 主文字 | `#1d2129` |
| `var(--neutral-text-2)` | 次文字 | `#4e5969` |
| `var(--neutral-text-3)` | 辅助文字 | `#86909c` |
| `var(--arco-primary)` | 主色 | `#165DFF` |
| `var(--arco-primary-light)` | 主色浅(选中态) | — |

所有颜色必须用变量并带亮色回退:`color: var(--neutral-text-1, #1d2129);`。

### 8.2 暗黑模式

- **CSS 层**:变量已在全局定义,卡片/文字自动适配;图表内固定色用 `themeStore.isDark` 切换调色板。
- **Plotly/ECharts 层**:监听 `isDark` 重新渲染,切换 `plot_bgcolor`/`paper_bgcolor`/字体颜色:

```ts
const themeStore = useThemeStore()
const isDark = computed(() => themeStore.isDark)
watch(isDark, () => renderPlot())
// buildPlotlyFigure(..., isDark.value, ...) 内部按 isDark 选调色板
```

### 8.3 scoped 样式

- 每个工具视图用 `<style scoped>`,避免污染全局。
- 穿透 Naive UI 内部类用 `:deep()`,如 `.param-panel :deep(.n-collapse-item__header) { font-size: 13px; }`。

---

## 九、交互与数据流规范

### 9.1 数据加载

- **onMounted 自动载入示例数据**,让用户进入页面即见图,不要求先上传:

```ts
onMounted(() => { loadSample() })
```

- 文件上传 / 粘贴 / 示例数据三种入口,统一走 `loadTable(headers, rows, fileName)` → `updatePipeline()`。
- 解析失败用 `message.error` 提示,不抛异常打断。

### 9.2 自动更新(debounce)

- 参数变化用 `watch` + 300ms debounce 触发重算,避免拖动滑块时频繁渲染:

```ts
let debounceTimer: ReturnType<typeof setTimeout> | null = null
function schedulePipeline() {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(updatePipeline, 300)
}
watch(() => [form.pvalCutoff, form.lfcCutoff, /* ...所有参数 */], schedulePipeline, { deep: false })
```

### 9.3 显式生成按钮(强制)

- 工具栏**必须有一个 `type="primary"` 的主操作按钮**(「生成图表」/「运行分析」),点击立即强制重算(跳过 debounce)。
- 作用:给用户明确控制感;自动渲染失败时的兜底入口。

### 9.4 组件卸载清理

```ts
onUnmounted(() => {
  if (debounceTimer) clearTimeout(debounceTimer)
  const el = document.getElementById(PLOT_DIV_ID)
  if (el) Plotly.purge(el)   // Plotly 必须显式释放,否则内存泄漏
})
```

---

## 十、数据处理模块规范(`<tool>Processor.ts`)

复杂工具的数据处理与图表配置**必须抽到独立的处理器文件**,视图只管交互。处理器是**纯函数模块,不持有状态、不依赖 Vue**。

### 10.1 结构约定

```ts
// volcanoProcessor.ts
import * as Plotly from 'plotly.js-dist-min'

// 1. 类型定义
export interface VolcanoConfig { /* 所有可调参数 */ }
export interface VolcanoRow { /* 单行数据 */ }
export interface ProcessedResult { rows: VolcanoRow[]; stats: ...; axisRange: ... }

// 2. 默认值(供视图初始化)
export const DEFAULT_CONFIG: VolcanoConfig = { ... }
export const DEFAULT_COLORS: VolcanoColors = { ... }

// 3. 解析函数(纯)
export function parseDelimited(text: string): ParsedTable { ... }
export function autoDetectColumns(cols: string[]): ColMap { ... }

// 4. 核心处理 pipeline(纯)
export function processVolcanoData(raw, colMap, config): ProcessedResult { ... }

// 5. 图表配置生成(纯,接收 isDark)
export function buildPlotlyFigure(rows, config, axisRange, isDark, focusGene?): PlotlyFigure { ... }

// 6. 辅助
export function formatP(n: number): string { ... }
export function genSampleData(): ParsedTable { ... }
```

### 10.2 视图与处理器的边界

| 职责 | 归属 |
|------|------|
| 响应式状态(form / colMap / processed) | 视图(`<Tool>View.vue`) |
| 数据清洗、统计、坐标轴计算 | 处理器(`processXxx`) |
| Plotly/ECharts 配置对象生成 | 处理器(`buildXxxFigure`) |
| 主题调色板选择 | 处理器(接收 `isDark` 参数) |
| DOM 操作、事件、消息提示 | 视图 |
| 调用 `Plotly.react` / `Plotly.purge` | 视图 |

---

## 十一、作用域隔离与全屏工具排外规则(重要)

### 11.1 紧凑布局的作用域

`DefaultLayout.vue` 的 `contentStyle` 用路由判断控制主内容区 padding,**只对工具箱区域生效**:

```ts
const contentStyle = computed(() => {
  if (route.meta.fullscreen) return 'padding: 0; ...'              // 全屏工具
  const isToolsArea = route.path === '/tools'
    || (route.path.startsWith('/tools/') && route.path !== '/tools/jbrowse')
  if (isToolsArea) return 'padding: 0; ...'                        // 工具箱紧凑
  return 'padding: 24px; ...'                                      // 其他页面不变
})
```

- 非工具页(首页、仪表板、任务、报告等)**保持 24px**,不受影响。
- 工具页(非全屏)外层 `padding: 0`,由页面根 16px 自控。

### 11.2 全屏工具(JBrowse 模式)排外

**「Web 基因组浏览器」(JBrowse)及任何 `fullscreen: true` 的工具,不适用本文档的紧凑布局规范**,其四周空隙与现有样式必须完全保持现状。

技术保证(双重保险):
1. `fullscreen` 分支在 `contentStyle` 中**最先判断**,直接返回 `padding: 0`,不进入工具箱分支。
2. 工具箱分支的 `isToolsArea` 判断中**显式排除 `/tools/jbrowse``,即便 fullscreen meta 被误删也不会被紧凑化。

**新增全屏工具时**:在路由 meta 加 `fullscreen: true` 即可自动走排外分支;若希望它也被排除在工具箱紧凑分支外,在 `isToolsArea` 判断里追加 `&& route.path !== '/tools/<key>'`。

### 11.3 禁止事项

- 禁止在工具页面根容器设 `max-width`(必须流式 `width: 100%`,大屏铺满)。
- 禁止在工具页面外层再套一层带 padding 的 wrapper(会造成双层留白)。
- 禁止硬编码颜色(必须走 §8.1 CSS 变量)。
- 禁止在视图中写超过 ~50 行的数据处理逻辑(抽到 processor)。

---

## 十二、可视化与导出规范

### 12.1 图表渲染

- 用 `Plotly.react(container, figure.data, figure.layout, figure.config)` 增量更新,不用 `newPlot`。
- 大数据量(>5000 点)用 `scattergl` 类型:`const useGL = rows.length > 5000`。
- 容器用固定 `id`,通过 `document.getElementById` 获取(不依赖 ref 时序)。

### 12.2 导出

- **PNG 高 DPI**:用 `Plotly.downloadImage` 的 `scale = dpi / 96`,DPI 选择器默认 1000(可选 300/600/1000)。
- **SVG 矢量**:不设 scale,直接导出。
- **文件名**:`<base>_<YYYYMMDD_HHMMSS>_<dpi>dpi.png`,含时间戳与 DPI。

```ts
const dpi = exportDpi.value
const scale = dpi / 96
Plotly.downloadImage(container, {
  format: 'png',
  filename: `${baseName}_${formatTimestamp()}_${dpi}dpi`,
  width: Math.round(rect.width),
  height: Math.round(rect.height),
  scale,
} as any)  // @types/plotly.js-dist-min 的 DownloadImgopts 缺 scale 字段,用 as any 逃逸
```

> `@types/plotly.js-dist-min` 类型不完整(`DownloadImgopts` 不含 `scale`、要求 `width/height` 必填),实际 Plotly 支持,用 `as any` 逃逸并在注释说明。

---

## 十三、上线检查清单

新增工具提交前,逐项确认:

- [ ] `tools_setting.yaml` 已注册,`key`/`route`/`icon`/`enabled`/`order` 字段完整
- [ ] `router/index.ts` 已加 `tools/<key>` 子路由,`name` 为 `tools-<key>`,`requiresAuth: true`
- [ ] 用了新图标已在 `ToolsHubView.vue` 的 `ICON_MAP` 登记
- [ ] 视图文件命名 `<Tool>View.vue`,根 class `<key>-page`,布局 class `<key>-layout`
- [ ] 根容器 `padding: 16px`,无外层 wrapper、无 `max-width`
- [ ] 工具栏:返回按钮 + 标题(flex:1) + 操作按钮,`margin-bottom: 8px`
- [ ] 主体 `gap: 16px`,卡片 `var(--neutral-card)` + 12px 圆角 + 12px padding
- [ ] 响应式:`@media (max-width: 1200px)` 退化为单栏
- [ ] 所有颜色走 CSS 变量,无硬编码
- [ ] 暗黑模式:图表监听 `isDark` 重渲染
- [ ] `onMounted` 载入示例数据,进入即见内容
- [ ] 参数变化 300ms debounce 自动更新
- [ ] 有 `type="primary"` 主操作按钮(生成/运行)
- [ ] `onUnmounted` 清理定时器与 Plotly 实例
- [ ] 复杂逻辑已抽到 `<tool>Processor.ts`(纯函数)
- [ ] `npm run build` 通过(`vue-tsc` 严格类型检查)
- [ ] 构建后 `docker restart omichub-nginx`(bind mount 换 inode 必须重启,否则跑旧产物)
- [ ] 若是全屏工具,路由 meta 加 `fullscreen: true`,并在 `isToolsArea` 排除

---

## 十四、参考实现索引

| 工具 | 视图 | 参考价值 |
|------|------|---------|
| 火山图 | `VolcanoPlotView.vue` + `volcanoProcessor.ts` | **首选样板**:三栏布局、参数折叠、坐标轴配置、高 DPI 导出、Plotly 暗黑模式 |
| BLAST | `BlastSearchView.vue` | 两栏(输入 + 结果)、表格结果展示 |
| FASTQ 质控 | `FastqQCView.vue` | 两栏、文件上传、统计卡片 |
| 绘图工坊 | `PlotWorkshopView.vue` | ECharts 集成、多图表类型切换 |
| KEGG 富集 | `KeggEnrichmentView.vue` | 两栏、后端配置驱动(`config_dir`) |
| JBrowse | `JBrowseViewer.vue` | **全屏工具特例**,仅参考全屏模式,不参考紧凑布局 |
| 工具箱列表 | `ToolsHubView.vue` | 卡片网格、ICON_MAP、API 拉取 |

---

*本规范由现有工具实现提炼,改动规范请同步更新本文档。*

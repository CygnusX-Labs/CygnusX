# OmicHub 生信工具箱 · 前端工具设计规范

> 本文档规定「生信工具箱」(`/tools`)下所有工具页面的架构、布局、样式、交互约定。
> 新增工具**必须遵循本规范**,以保证视觉一致、交互统一、维护成本低。
> 现有参考实现:火山图(`VolcanoPlotView.vue`)为最完整的样板,优先参照;BLAST / FASTQ 质控 / 绘图工坊 / KEGG 为次参照;JBrowse 为**全屏工具特例**,不作为紧凑布局参照。
>
> 最后更新:2026-07-17

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
└── <tool-key>/                   # 工具专属 YAML 配置目录(如 jbrowse/、enrichments/)
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

1. **后端注册**:在 `tool_configs/tools_setting.yaml` 的 `tools` 列表追加一项，必须指定 `group`（字段与可选值见 §五）。
2. **前端路由**:在 `frontend/src/router/index.ts` 的 `DefaultLayout` children 内,仿照已有工具追加子路由(见 §五)。
3. **图标登记**(仅当用了新图标):在 `ToolsHubView.vue` 的 `ICON_MAP` 登记组件。YAML 的 `icon` 字段是字符串,Vue 组件不能由字符串动态 import,必须在此映射。
4. **后端功能配置**(仅有后端的工具):按 §5.1.1 新建 `tool_configs/<tool-key>/` 目录放 YAML,并在 YAML 的 `config_dir` 指明。纯前端工具(如 plot/volcano/blast)留空。
5. **创建页面**:新建 `frontend/src/views/BioTools/<Tool>View.vue`,按 §六骨架实现;复杂数据逻辑抽到 `frontend/src/utils/<tool>Processor.ts`。

> **图形绘制工具补充要求**：散点图、火山图、热图、箱线图、柱状图等以数据导入和交互式绘图为核心的工具，还必须遵守 §5.6 的参数、功能、导出与验证规范。

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
  group: "visualization"                 # 分组 key,决定工具箱中的展示分区
  enabled: true                          # false 则软下线,不出现在工具箱
  order: 45                              # 卡片排序,升序(10 的步长留间隔)
  config_dir: ""                         # 有后端配置填 "tool_configs/<tool-key>",纯前端留空
```

#### 5.1.1 工具运行配置外置（推荐）

只要工具存在可运营、需按环境/物种/资源调整，或可能由管理员维护的参数，就应将其外置为
`tool_configs/<tool-key>/` 下的 YAML 文件，而不是散落在 Python、Vue 或 TypeScript 常量中。
典型配置包括参考基因组、物种列表、数据库资源、分析默认阈值、容器镜像、可选算法、结果保留策略和功能开关。

```text
tool_configs/
├── tools_setting.yaml                         # 工具箱注册表；只放卡片展示与入口元数据
└── <tool-key>/
    ├── <tool-key>_config.yaml                  # 工具主运行配置（推荐命名）
    ├── resources.yaml                          # 可选：参考资源/数据库/物种等大列表
    └── presets.yaml                            # 可选：用户可选的参数预设
```

| 配置类别 | 放置位置 | 示例 |
|---|---|---|
| 工具卡片元数据 | `tool_configs/tools_setting.yaml` | 标题、图标、路由、分组、排序、`config_dir`。 |
| 工具运行配置 | `tool_configs/<tool-key>/*.yaml` | 默认参数、资源目录、算法开关、可用物种。 |
| 前端纯展示预设 | 优先 `tool_configs/<tool-key>/presets.yaml`；无后端读取需求时可随前端模块维护 | 绘图主题、示例数据说明、表单默认预设。 |
| 密钥与环境差异 | 环境变量 + `src/omichub/core/config.py` | API Key、密码、数据库 DSN、主机地址。 |

实现要求：

1. 后端为每份 YAML 建立对应的 Pydantic 配置模型与加载器，建议放在 `src/omichub/tools/<tool_key>/config.py`；不要把 `dict[str, Any]` 直接传入业务逻辑。
2. 加载器必须明确默认值、必填字段和 YAML 解析失败策略。可热更新的配置应按文件 mtime 缓存/重载；不支持热更新时在文档中说明重启要求。
3. API 只返回前端实际需要且允许公开的配置子集；不得将本地路径、访问令牌、密码或内部基础设施细节直接下发到浏览器。
4. 配置字段改动时，同步更新 Pydantic 模型、调用服务、前端类型/API（如有）、示例 YAML 和模块设计文档。
5. YAML 使用 UTF-8、2 空格缩进与 `snake_case` 字段名；需引用路径时使用相对仓库根的稳定路径，避免写入开发机绝对路径。
6. 每个工具配置至少有解析与模型校验的定向测试/验证样例，确认空配置、非法枚举、资源缺失和默认值行为。

纯前端且没有可运营参数的工具可以保持 `config_dir: ""`；一旦需要让默认阈值、色板、资源列表或预设可独立维护，就应创建对应 YAML 配置，而不是继续扩大组件内硬编码常量。

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

### 5.4 工具箱分组展示(`ToolsHubView.vue`)

工具箱列表页按 `group` 分区渲染，而不是将全部工具卡片平铺。分组常量定义在
`frontend/src/views/BioTools/ToolsHubView.vue` 的 `GROUP_MAP`；新增分组时必须同步更新
前端映射、分组图标登记与本文档。

| group key | 展示名称 | 分组图标 | 分组顺序 | 当前工具 |
|---|---|---|---:|---|
| `sequence` | 序列分析 | `CodeSlashOutline` | 1 | FASTQ 极速质控、序列检索 BLAST、序列魔术师、PrimerForge 引物锻造工坊 |
| `visualization` | 数据可视化 | `ColorPaletteOutline` | 2 | 组学绘图工坊、火山图绘制 |
| `genome` | 基因组与进化 | `LayersOutline` | 3 | Web 基因组浏览器、系统发育树构建、格式轻量转换器 |
| `function` | 功能注释 | `BarChartOutline` | 4 | KEGG 通路富集分析 |
| `environment` | 计算环境 | `TerminalOutline` | 5 | 云端沙盒终端 |

分组与卡片排序规则：

1. `enabled: false` 的工具在后端已过滤，前端仍以 `tool.enabled !== false` 作兼容性过滤；禁用工具不参与分组计数。
2. 分组按上表的 `order` 升序展示；组内工具继续严格按各自 `order` 升序展示，不改变既有排序语义。
3. `group` 缺失或不在 `GROUP_MAP` 内时，前端归入最后的「其他工具」（`AppsOutline`），避免新配置导致卡片丢失。
4. 无可用工具的分组不渲染；首次加载时展示五个标准分组标题，并在每个分组下显示两行骨架卡片。

每个分组标题必须包含分组图标、名称、工具数量和折叠按钮。分组默认展开，用户操作后的
折叠状态以 `localStorage` 键 `omicHub_tools_group_collapsed` 持久化；刷新或再次进入工具箱时恢复。
分组内继续直接复用 `components/bio-tools/ToolCard.vue`，不得修改其卡片渐变、圆角、hover 动效或路由跳转方式。

推荐样式约定：

```css
.tool-group { margin-bottom: 24px; }
.group-header { /* 图标 + 16px/500 标题 + 数量 + 右侧折叠按钮 */ }
.tools-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  margin: 12px 0;
}
@media (max-width: 768px) {
  .tools-grid { grid-template-columns: 1fr; }
}
```

### 5.5 注册表与 API 字段透传

`group` 是工具注册表元数据的一部分，必须沿以下链路保持同名透传：

```text
tool_configs/tools_setting.yaml
  → src/omichub/tools/registry/config.py::ToolItem
  → src/omichub/tools/registry/schema.py::ToolItemDTO
  → GET /api/v1/tools
  → frontend/src/types/tools.ts::ToolItem
  → ToolsHubView.vue
```

新增或修改 `group` 时，需要同时确认配置模型、API DTO、前端 `ToolItem` 类型与 `GROUP_MAP` 一致；
不要仅修改 YAML，否则接口会因 Pydantic 模型忽略未知字段而无法向前端返回分组信息。

### 5.6 图形绘制工具通用规范（以火山图为基准）

本节适用于火山图、散点图、热图、箱线图、柱状图、富集气泡图等“用户导入表格后在浏览器中配置并生成图形”的工具。
新增图形绘制工具应复用火山图的完整交互闭环，而不是只输出一张不可配置的静态图：

```text
数据导入 → 表头识别与字段映射 → 数据校验与转换 → 参数化绘图
→ 图上交互与结果查询 → 数据表核对 → 图片/矢量导出
```

#### 5.6.1 目录与职责

```text
frontend/src/
├── views/BioTools/<Chart>View.vue       # 页面、表单状态、渲染生命周期、导出按钮
└── utils/<chart>Processor.ts             # 纯函数：解析、列识别、校验、计算、Plotly/ECharts 配置
```

- 页面组件只管理表单、上传文件、响应式状态、图表挂载和用户反馈；不在 Vue 组件内堆积数据算法。
- `Processor` 必须导出明确的输入行、列映射、配置、处理结果和图表构建函数类型；同一输入与配置应得到可预测结果。
- 图表库遵循 §十二：需要缩放、悬浮提示、点选、矢量导出或大规模散点时优先 Plotly；常规统计图可使用 ECharts。
- 绘图工具如是纯前端计算，数据不得上传后端；如果确有服务端计算需求，必须说明文件保留、任务状态、权限与结果清理策略。

#### 5.6.2 必备数据导入与字段映射参数

| 能力 | 最低要求 | 火山图参考实现 |
|---|---|---|
| 文件上传 | 支持 CSV、TSV/TXT；明确大小限制和解析失败提示。 | `NUpload` + `FileReader`。 |
| 直接粘贴 | 支持将表格文本粘贴为数据源，适合少量快速作图。 | 火山图页面已提供粘贴入口。 |
| 示例数据 | 每个工具提供可一键载入的最小有效示例，帮助用户理解字段要求。 | `genSampleData()`。 |
| 分隔符识别 | 自动识别 Tab、逗号和空白分隔；不确定时给出提示或允许人工选择。 | `parseDelimited()`。 |
| 表头与行数反馈 | 上传/粘贴后显示文件名、有效行数、可选列。 | 文件名 + 行数提示。 |
| 自动列识别 | 根据常见别名推测所需列，减少手动操作。 | `autoDetectColumns()` 识别 `padj`、`log2FC`、基因名。 |
| 手动列映射 | 所有核心字段必须可由用户重新选择；不要只依赖列名猜测。 | `NSelect` 映射 padj、log2FC、gene。 |
| 数据校验 | 校验必填列、数值范围、空值、重复/非法值；明确跳过行或中断的规则。 | NA 过滤、`p <= 0` 安全处理。 |

不同图种在模块设计文档中必须列出**输入契约**：必需列、可选列、可接受别名、数值单位、最小行数和示例数据格式。例如：

| 图种 | 常见必需列 | 常见可选列 |
|---|---|---|
| 火山图 | 特征 ID、效应值（如 `log2FC`）、显著性（`padj`/`pvalue`） | 分组、注释、原始 p 值 |
| 散点图 | X、Y | 标签、颜色分组、点大小、形状分组 |
| 箱线图 | 分组、数值 | 子分组、样本 ID、显著性结果 |
| 热图 | 行 ID、列名与数值矩阵 | 行/列注释、聚类结果、分组颜色 |
| 柱/折线图 | 分类/时间轴、数值 | 系列、误差值、标签、置信区间 |

#### 5.6.3 参数面板的最低功能集

参数面板使用 `NCollapse` 分区，默认展开数据、核心阈值/映射和轴设置；复杂参数允许折叠，但不能隐藏核心操作。

| 参数分组 | 必备参数/功能 | 说明 |
|---|---|---|
| 数据与映射 | 数据源、列映射、解析提示、重置/示例数据 | 显示当前数据状态；数据更新后自动重算。 |
| 核心计算 | 图种特有阈值、分组规则、变换方式、统计口径 | 例如火山图的 p-value 与 `|log2FC|` 阈值。 |
| 颜色与图例 | 分组颜色、强调色、图例开关/位置（适用时） | 使用 `NColorPicker`；默认色需符合亮/暗主题。 |
| 坐标轴与标题 | 自动/手动范围、最小/最大值、X/Y 轴标题、主标题、标题换行 | 手动范围须校验 `min < max`；自动模式使用数据驱动的安全边界。 |
| 标签与重点对象 | Top N 标注、自定义 ID/基因列表、高亮开关、标注上限 | 防止大数据量一次标注全部对象；无效 ID 必须提示。 |
| 图表样式 | 点/线/柱尺寸、透明度、网格/阈值线、布局密度 | 参数变化即时重绘，不能破坏数据与筛选状态。 |
| 导出 | PNG、SVG、尺寸跟随容器或自定义宽高、PNG DPI/导出倍率 | PNG 至少提供 300/600/1000 DPI 或等效 `scale` 选项；自定义尺寸要校验合理范围，例如 100–8000 px。 |

图种特有参数必须按语义追加，不能强行套用火山图字段。例如热图需要色阶、聚类和标准化；箱线图需要离群值、抖动点与统计比较；散点图需要回归线、相关系数和点大小映射。

#### 5.6.3.1 分组与配色规范（强制）

**只要最终图形存在分类分组、系列、处理组、样本组、显著性类别或注释类别，就必须用颜色区分。**
不得仅依赖点形状、线型、位置或文字来区分不同组；颜色、图例和 hover 中的分组名称必须同时存在。

1. 分类变量使用**离散色板**，一个类别对应一个稳定颜色；同一类别在筛选、重绘、导出和同工具的不同图中必须保持同色。
2. 连续数值（如表达量、富集比例、时间、相关性）使用**连续渐变色板**，必须显示颜色条及数值范围；禁止把连续渐变逐项分配给离散类别。
3. 默认颜色是数据编码的例外，可使用本节列出的固定十六进制色值；页面背景、文字、边框等 UI 颜色仍须遵守 §八的 CSS 变量要求。
4. `NColorPicker` 仅用于允许用户覆盖默认颜色；重置后必须恢复标准色板。自定义颜色改变后，图例、hover、标注和导出图必须同步更新。
5. 类别数超过当前色板容量时，不得静默循环复用颜色；应提示用户、要求合并/筛选类别，或使用经过设计并在模块文档中登记的扩展色板。

以下色板是 OmicHub 图形绘制工具的标准默认选项。实现时可直接以同名常量放入 `<chart>Processor.ts` 或共用配色工具文件：

```ts
export const PLOT_COLOR_PALETTES = {
  // 优先默认：色觉友好，适合 2–6 个离散组
  color_discrete_friendly: ['#0072B2', '#56B4E9', '#009E73', '#F5C710', '#E69F00', '#D55E00'],
  // 海岸风格，适合不超过 5 个离散组
  colors_discrete_seaside: ['#8ecae6', '#219ebc', '#023047', '#ffb703', '#fb8500'],
  // 色觉友好扩展，适合不超过 7 个离散组
  colors_discrete_friendly_long: ['#CC79A7', '#0072B2', '#56B4E9', '#009E73', '#F5C710', '#E69F00', '#D55E00'],
  // 长离散色板，适合不超过 12 个离散组
  colors_discrete_friendly_long_2: ['#fe65b3', '#CC79A7', '#ffd2d8', '#0072B2', '#007aff', '#56B4E9', '#009E73', '#4cd964', '#F5C710', '#E69F00', '#D55E00', '#ff3b30'],
  // 可选主题色板：按工具设计选用，不能与同图中的默认色板混用
  colors_discrete_apple: ['#ff3b30', '#ff9500', '#ffcc00', '#4cd964', '#5ac8fa', '#007aff', '#5856d6'],
  colors_discrete_ibm: ['#5B8DFE', '#725DEE', '#DD227D', '#FE5F00', '#FFB109'],
  colors_discrete_candy: ['#9b5de5', '#f15bb5', '#fee440', '#00bbf9', '#00f5d4'],
  color_1: ['#ECA669', '#E06681', '#8087E2', '#E2D269'],
  // 仅用于有序连续数值；必须配合 colorbar，不可作为分类色板
  colors_continuous_bluepinkyellow: ['#00034D', '#000F9F', '#001CEF', '#241EF5', '#5823F6', '#A033E0', '#E85AB1', '#F1907C', '#F4AF63', '#FCE552', '#FFFB6D'],
} as const
```

默认选择规则：

| 场景 | 默认色板 | 使用规则 |
|---|---|---|
| 2–6 个分类组 | `color_discrete_friendly` | 首选，保证主要生信分组的可读性与色觉友好性。 |
| 7 个分类组 | `colors_discrete_friendly_long` | 按稳定类别顺序取色。 |
| 8–12 个分类组 | `colors_discrete_friendly_long_2` | 必须保留清晰图例；建议同时提供筛选。 |
| 工具明确要求特定视觉主题 | `colors_discrete_seaside` / `colors_discrete_apple` / `colors_discrete_ibm` / `colors_discrete_candy` / `color_1` | 只能选一套作为该图的离散默认色；在模块文档记录选择原因。 |
| 连续数值映射 | `colors_continuous_bluepinkyellow` | 按数值从低到高映射，并展示 colorbar；若数值具有“零/基线”语义，需在模块文档说明中点颜色和范围。 |

建议按原始数据或用户明确的类别顺序建立颜色字典，而不是按当前筛选结果临时排序：

```ts
function buildGroupColorMap(groups: string[], palette: readonly string[]) {
  const uniqueGroups = [...new Set(groups)]
  if (uniqueGroups.length > palette.length) {
    throw new Error('当前分组数超过所选离散色板容量')
  }

  return Object.fromEntries(
    uniqueGroups.map((group, index) => [group, palette[index]]),
  )
}
```

图例中应按该颜色字典输出所有当前可见组；分组标签需使用用户可理解的中文/原始名称，禁止只展示内部编码。

#### 5.6.4 数据处理与绘图质量要求

1. **纯函数处理管线**：将原始行转换为渲染行时，依次完成列读取、数值转换、缺失值策略、派生指标、分类/分系列、排序、标签选择和坐标范围计算。
2. **异常值策略明确**：零值、负值、NA、NaN、Infinity、重复 ID、极端值和对数变换的非法输入必须有确定行为；例如火山图把 `p <= 0` 夹到最小正数，避免产生 `Infinity`。
3. **自动范围可读**：自动坐标范围必须留边距，并抑制单个极端值挤压主体数据；用户始终可切换为手动范围。
4. **主题适配**：图表背景、网格、坐标轴、文本、标注框、hover 文本和图例均要随 `useThemeStore()` 的亮/暗主题切换。
5. **可解释 hover**：每个图元的 hover 至少展示主键/标签、关键数值和分组；格式化小数、p 值和科学计数法，禁止直接显示未处理的浮点数。
6. **受控重绘**：参数、数据或主题变化后更新图表；避免重复创建图表实例。页面卸载时调用图表库的销毁方法（如 `Plotly.purge`）。
7. **性能边界**：大数据量默认关闭过多文本标签，限制搜索结果/结果表首屏行数；必要时采用 WebGL trace、抽样或前端分页，并在设计文档说明阈值。

#### 5.6.5 结果区、交互与可追溯性

每个图形绘制工具至少提供以下能力：

- **图表状态**：未导入数据时展示明确空状态和输入要求；绘制时显示 loading；失败时显示可操作的错误提示。
- **统计摘要**：展示总行数、有效行数及图种关键分组/统计结果。火山图对应总计、上调、下调和非显著数量。
- **搜索与焦点**：可按主键/标签搜索对象；选中对象在图上突出显示或添加引线标注。
- **结果数据表**：可展开查看用于绘图的处理后数据，至少包含主键、关键数值、分组/系列与派生指标；支持合理的排序或筛选。
- **重置与全屏**：提供恢复默认参数/重新绘制操作；复杂图表提供全屏查看，并确保退出后图表尺寸重新计算。
- **可复现信息**：导出或结果区域应能让用户获知数据来源、列映射和关键参数；需要审计的工具可额外导出参数 JSON 或生成分析摘要。

#### 5.6.6 导出规范

```ts
// Plotly 工具的最小导出能力；PNG 的 scale 可按目标 DPI / 96 计算
await Plotly.downloadImage(plotElement, {
  format: 'png', // 同时提供 'svg'
  filename: '<tool_key>_plot',
  width,
  height,
  scale: targetDpi / 96,
})
```

- PNG 用于演示和报告插图，至少可选择 300、600、1000 DPI 或等效倍率；SVG 用于论文排版和后续矢量编辑。两种格式都必须可用。
- 默认导出尺寸跟随当前图表容器；开启自定义尺寸时使用用户输入的宽高，且 SVG 不额外套用 DPI 概念。
- 导出文件名使用稳定的 `<tool_key>_plot` 前缀，可附加日期或用户填写的实验名；不得使用随机临时文件名。
- 导出前验证图表实例和数据有效，避免生成空白图片；导出失败时通过 `useMessage()` 告知用户。

#### 5.6.7 图形绘制工具验收清单

- [ ] 支持上传、粘贴和示例数据，且能显示解析后的表头与有效行数。
- [ ] 具备自动列识别和手动列映射；无效或缺失字段会给出明确提示。
- [ ] 核心计算、颜色、坐标轴、标题、标签、样式和导出参数均可配置。
- [ ] 含分类分组/系列的图表使用离散颜色、图例和 hover 同步展示；相同分组在重绘与导出中保持同色。
- [ ] 连续变量使用连续色板和 colorbar；类别数超过默认色板容量时不会静默重复颜色。
- [ ] 自动与手动坐标范围均正确，手动范围能阻止 `min >= max` 的无效提交。
- [ ] 图表支持 hover、主题切换、搜索/重点对象标注、统计摘要和处理后数据表。
- [ ] 支持 PNG 与 SVG 导出，能选择容器尺寸或自定义尺寸。
- [ ] 大数据量下不会默认渲染无限标签，切换页面后图表实例已正确销毁。
- [ ] 处理器中的解析、列识别、数值转换、核心计算和图表配置具备定向测试或可重复的验证样例。

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


---

## 十五、AI 助手联动架构

OmicHub 的「AI 助手」页面（Agent 调度中枢）不仅支持通用对话，还能直接调用平台生信工具箱中的工具完成计算、绘图、富集等任务。本章说明工具箱如何与 AI 助手打通，以及新增工具时需要遵守的约定。

### 15.1 总体数据流

```
用户消息/附件
    │
    ▼
Agent 调度中枢 (chat_service.py::stream_agent_chat)
    │ 1. 查 Agent → 组装模型/系统词/MCP server/工具列表
    │ 2. 送 LLM（流式）
    ▼
LLM 决定调用工具（OpenAI function call）
    │
    ▼
MCPClient.call_tool(server, tool_name, arguments)
    │  _builtin transport_ → omichub-tools preset
    ▼
ToolBridgeService.execute(user_id, tool_name, arguments)
    │ 1. 参数校验 + upload:// 解析
    │ 2. 按 invocation_mode 分发执行
    ▼
具体工具实现（service / shim / async / open_page）
    │
    ▼
双通道结果
    ├─ llm_payload：精简摘要，回灌 LLM 用于下一轮对话
    └─ ui_payload：完整图/表/任务信息，透传给前端渲染
```

### 15.2 工具注册：从 tools_schema.yaml 到 LLM function

`tool_configs/tools_schema.yaml` 是 AI 助手工具的唯一注册表。每个工具条目包含：

| 字段 | 作用 |
|------|------|
| `name` | LLM 看到的 function 名，必须以 `omichub_` 开头 |
| `description` | LLM 判断是否调用该工具的依据 |
| `input_schema` | OpenAI functions 参数 schema |
| `invocation_mode` | 执行方式：`backend_sync` / `backend_shim` / `backend_async` / `open_page` |
| `service` + `method` | `backend_sync` 时进程内调用的 service 方法 |
| `shim_module` | `backend_shim` 时调用的轻量 Python 模块 |
| `llm_result_fields` | 回灌 LLM 的字段白名单（建议 ≤3KB） |
| `ui_result_fields` | 透传给前端的字段白名单 |

启动时 `AgentService.assemble_context()` 自动把 `tools_schema.yaml` 中的工具注入为 Agent 可调用的 OpenAI functions，并在系统提示词里追加工具清单（`schema_loader.build_system_hint()`）。

### 15.3 双通道输出规范

工具实现返回的原始 dict 经过 `ToolBridgeService._package()` 后统一为：

```python
{
    "success": True,
    "is_error": False,
    "llm_payload": {...},   # 给 LLM 看
    "ui_payload": {...},    # 给前端看
}
```

#### 15.3.1 llm_payload（回灌 LLM）

- 必须精简，默认不超过 3KB。
- 只放文字摘要、统计、Top 列表、错误说明等 LLM 能读懂的内容。
- 禁止放完整 Plotly JSON、二进制、大表格。

#### 15.3.2 ui_payload（前端渲染）

前端 `KimiMessageItem.vue` 目前识别以下 ui_payload 字段：

| 字段 | 前端行为 |
|------|---------|
| `plotly_figure` | 用 Plotly.js 渲染交互式图表 |
| `table_data` / `tableData` | 用 `NDataTable` 展示表格 |
| `confirm_card` | 显示二次确认卡片 |
| `route` | 显示「前往工具页」引导卡片 |
| `task_id` + `progress_url` / `result_url` | 显示异步任务进度卡片 |

新增可视化工具时，ui_payload 里必须包含 `plotly_figure: {data: [...], layout: {...}}`，前端即可自动出图。

### 15.4 文件上传协议：`upload://file_id`

AI 助手上传的文件保存在 `{data_root}/users/{uid}/workspace/chat-uploads/`。当工具参数需要大段文本（如 `data_text`、`gene_text`）时，LLM 可以传 `upload://file_id` 引用已上传文件，而不是把整个 CSV 塞进参数。

约定：

- 参数 description 里必须写明「也支持 upload://file_id」。
- 系统提示词规则里明确要求 LLM：大文件用 `upload://file_id`，禁止留空。
- `ToolBridgeService._resolve_upload_refs()` 负责把引用解析为文件内容。

示例参数描述：

```yaml
data_text:
  type: string
  description: CSV/TSV 格式的差异表达表文本，含 log2FC 与 p-value 列；也支持 upload://file_id 引用已上传文件
```

### 15.5 前端 SSE 事件消费

Agent 调度中枢通过 `/api/v1/chat/stream` 返回 SSE 事件，前端 `useAgentChatStream.ts` 解析：

| 事件类型 | 含义 | 前端处理 |
|---------|------|---------|
| `text` | LLM 生成的文字 token | 追加到当前 assistant 消息 |
| `tool_call` | LLM 发起工具调用 | 在 assistant 消息的 `toolCalls` 里新增 running 状态卡片 |
| `tool_result` | 工具执行完成 | 匹配 `tool_call_id`，回填 `result` / `uiPayload`，更新状态为 success/error |
| `error` | 服务端/模型错误 | 显示错误态 |
| `done` | 整轮结束 | 结束流式状态 |

`KimiMessageItem.vue` 中：

```ts
const plotlyCharts = computed(() => {
  // 优先从 tool.uiPayload.plotly_figure 取图
  // 兼容 result.ui_payload.plotly_figure / result.plotly_figure
})
```

工具卡片会同时显示：工具名、参数、运行状态、LLM 摘要结果、图表/表格/确认卡/任务进度卡。

### 15.6 新增一个 AI 助手可用工具的步骤

1. **实现工具逻辑**：在 `src/omichub/tools/` 下新增 service 或 shim，返回原始 dict（含 `success` + 可选 `plotly_figure` / `table_data` 等）。
2. **注册 schema**：在 `tool_configs/tools_schema.yaml` 新增条目，写好 description、input_schema、llm_result_fields、ui_result_fields。
3. **选择 invocation_mode**：
   - 轻量快速出图 → `backend_shim`
   - 复用现有 service → `backend_sync`
   - 长时间计算 → `backend_async`（返回 `task_id`）
   - 需要复杂交互 → `open_page`（返回 `route`）
4. **确认 ui_payload 字段**：出图必须含 `plotly_figure`；表格必须含 `table_data`。
5. **测试链路**：
   - `pytest tests/unit/tools/test_tool_bridge.py` 验证 ToolBridge 分发。
   - 在 AI 助手页面发送自然语言请求，确认工具被调用、图表/表格正确渲染。

### 15.7 常见问题排查

| 现象 | 可能原因 | 排查方向 |
|------|---------|---------|
| LLM 不调用工具 | 工具描述不清 / 系统提示词未注入 | 检查 `tools_schema.yaml` description 和 `build_system_hint()` |
| 提示缺少必填参数 | LLM 没传文件内容 | 确认参数 description 写了 `upload://file_id` |
| 工具执行成功但前端没图 | `ui_payload` 里没有 `plotly_figure` / 字段名不对 | 检查 `ui_result_fields` 和工具返回值 |
| 工具结果没关联到工具卡片 | `tool_call_id` 为空或前后端不匹配 | 检查 LLM provider 是否返回 tool_call id |
| 图表渲染报错 | Plotly figure 结构非法 | 用 `python -m omichub.tools.shims.xxx` 单独测试返回值 |

---

## 十六、Apple Design 交互与动效规范(工具箱)

> 自 2026-07-17 起,工具箱列表页(`ToolsHubView.vue`)与工具卡片(`ToolCard.vue`)按 Apple
> 「流体界面」(Fluid Interfaces, WWDC 2018)原则设计。新增/修改工具箱 UI 时必须遵守本节约定,
> 保持全站动效语言一致。

### 16.1 核心原则

| 原则 | 要求 |
|------|------|
| **响应即时** | 按下(pointer-down)立刻给出反馈,不等松手;按压态过渡时长固定 `100ms` |
| **弹簧缓动** | 所有交互过渡统一用 `cubic-bezier(0.16, 1, 0.3, 1)`(模拟临界阻尼弹簧,无过冲);禁止 `transition: all` 和默认 `ease` |
| **动量才弹** | 无手势动量的 UI(卡片、面板、模态)一律临界阻尼不回弹;回弹只允许出现在拖拽/甩动之后 |
| **方向暗示** | 中间帧要预示结果:可导航卡片的箭头在悬停时向「前进」方向位移(`translateX(3px)`) |
| **空间一致** | 展开/收起等可逆动作使用同一元素的连续运动(如箭头旋转 90°),禁止两个图标瞬时替换 |
| **材质纵深** | 彩色图标块加顶部内高光 `inset 0 1px 0 rgba(255,255,255,0.28)`;浮起阴影用「大面积柔光 + 近身接触影」双层结构 |
| **反馈有度** | 不可交互的表面不做悬停位移;反馈只出现在可操作的元素上 |

### 16.2 标准参数(直接复用)

```css
/* 交互过渡(悬停/聚焦等柔和反馈) */
transition: <prop> 320ms cubic-bezier(0.16, 1, 0.3, 1);

/* 按压反馈(即时) */
:active {
  transform: scale(0.98);
  transition-duration: 100ms;
}

/* 卡片/列表项入场(交错 40ms,仅上浮 + 淡入,无缩放弹跳) */
@keyframes cardIn {
  from { opacity: 0; transform: translate3d(0, 10px, 0); }
  to   { opacity: 1; transform: translate3d(0, 0, 0); }
}
animation: cardIn 420ms cubic-bezier(0.16, 1, 0.3, 1) both;

/* 键盘焦点(必须可见) */
:focus-visible {
  outline: 2px solid var(--arco-primary, #165DFF);
  outline-offset: 2px;
}

/* 减少动态效果:去掉位移/缩放/旋转,保留不透明度变化 */
@media (prefers-reduced-motion: reduce) { /* transition: none; transform: none */ }
```

### 16.3 无障碍基线

- 可点击的非按钮元素(如卡片)必须 `role` + `tabindex="0"` + `@keydown.enter` / `@keydown.space.prevent`,并提供 `:focus-visible` 描边。
- 三个无障碍媒体查询按需响应:`prefers-reduced-motion`(去位移,保留淡入淡出)、`prefers-reduced-transparency`(去毛玻璃改实色)、`prefers-contrast`(边框加实)。
- 排他控件(展开/收起)加 `aria-label`,说明动作而非状态。

### 16.4 字距规则

- 大标题/大数字:负字距(`-0.01em` ~ `-0.02em`),可启用 `font-optical-sizing: auto`。
- 正文(13–16px):字距保持 `0` 或 `-0.01em`,用字重而不是字距建立层级。

### 16.5 本次落地记录(2026-07-17)

| 文件 | 修改内容 |
|------|---------|
| `components/bio-tools/ToolCard.vue` | 缓动改弹簧曲线并限定属性;新增 `:active` 100ms 按压收缩;悬停阴影改双层;箭头悬停右移 3px;图标块加内高光与投影;补 `role="link"`、键盘触发、`:focus-visible`、`prefers-reduced-motion` |
| `views/BioTools/ToolsHubView.vue` | 展开/收起改为单箭头旋转 90°(加 `aria-label`);卡片网格交错入场(40ms 步进);分组标题字重 500→600、字距 -0.01em;补 `prefers-reduced-motion` |

---

*本章节与 `tools_update.md` 互为补充：后者记录落地计划与排期，本文档记录架构规范与实现约定。*

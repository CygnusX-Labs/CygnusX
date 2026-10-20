# 生信工具接入指南

本页说明如何把生信工具接入 CygnusX 工具箱，并让它可被 AI 安全调用。工具同时受前端注册表与
LLM schema 两条链路约束；两者都登记后，才形成完整的用户入口与 Agent 入口。工具运行模式与
现有实现细节见[生信工具箱](../features/toolbox)。

## 双注册表

| 注册表 | 作用 | 消费方 |
| --- | --- | --- |
| `tool_configs/tools_setting.yaml` | 前端工具卡片、分组、路由、启用状态 | `GET /api/v1/tools` → 工具箱页面 |
| `tool_configs/tools_schema.yaml` | LLM 工具 schema、调用模式、结果字段 | 工具清单编译 → Chat / MCP |

只登记前端卡片时，工具只能人工使用；只登记 schema 时，AI 可能调用但用户看不到入口。两者
应保持 key 一致。

## 前端卡片注册

```yaml
tools:
  - key: volcano
    name: 火山图
    route: /tools/volcano
    icon: FlameOutline          # @vicons/ionicons5 图标名
    gradient: "linear-gradient(135deg, #ff7e5f, #feb47b)"
    group: visualization        # sequence / visualization / genome / function / environment
    enabled: true
    order: 10
    config_dir: volcano         # tool_configs/volcano/ 配置目录
```

`group` 必须为 `sequence`、`visualization`、`genome`、`function`、`environment` 之一，并完整
透传到前端 DTO。展示规则：

- 按分组顺序和组内 `order` 升序展示；
- 禁用工具不计数；
- 未知分组归入“其他工具”；
- 分组折叠状态使用 `localStorage` 键 `cygnusX_tools_group_collapsed`；
- 卡片复用 `components/bio-tools/ToolCard.vue`。

## ToolBridge 执行模式

工具在 schema 中声明调用模式，由 `ToolBridgeService` 分发：

| 模式 | 行为 | 适用 |
| --- | --- | --- |
| `backend_sync` | 同步调用后端服务并返回结果 | 轻量计算、查询 |
| `backend_shim` | 兼容旧工具的同步包装 | 历史工具迁移 |
| `backend_async` | 提交独立异步作业（ARQ/任务队列） | 系统发育树等独立工具作业 |
| `open_page` | 返回前端跳转指令，由用户继续操作 | 需要人工交互的工具 |
| `analysis_flow` | 走 Flow prepare → 人类确认 → `TaskService.submit()` | 标准分析流程 |

分析中心流程**不**走 `backend_async`，而是与表单共用 `TaskService.submit()`，保证任务记录、
用户隔离、工作目录、监控、结果页和计费一致。

## 工具专属配置目录

在 `tool_configs/<tool>/` 放置：

- 参考数据、物种配置、参数模板；
- Dockerfile（如需要自定义容器）；
- 测试数据；
- README.md，说明使用方法和数据来源。

## 图形绘制工具强制闭环

火山图、散点图、热图、箱线图、柱/折线图等必须形成：

```text
导入/粘贴/示例数据 → 自动与手动列映射 → 校验与计算 → 交互式绘图
  → 结果表 → PNG/SVG 导出
```

### 参数覆盖

- 数据映射（x/y/group/color/size 等）
- 核心计算（p 值阈值、fold change 阈值、聚类等）
- 颜色、坐标轴、标题、标签
- 样式与导出尺寸/DPI

### 分组配色

- 2–6 组：默认 `color_discrete_friendly`
- 7 组：`colors_discrete_friendly_long`
- 8–12 组：`colors_discrete_friendly_long_2`
- 超过色板容量必须提示或筛选，**禁止静默重复颜色**
- 连续数值使用连续色板并显示 colorbar，不能当作分类色板

### 图表质量

- 处理逻辑放入 `utils/<tool>Processor.ts` 的纯函数；
- 处理 `NA` / `NaN` / `Infinity` / 极端值；
- 支持亮暗主题；
- 可解释 hover；
- 受控重绘和页面卸载销毁；
- PNG 导出至少支持 300/600/1000 DPI 或等效倍率；
- SVG 用于矢量导出。

## 接入 checklist

- [ ] 在 `tools_setting.yaml` 注册前端卡片，指定正确的 `group` 和 `config_dir`
- [ ] 在 `tools_schema.yaml` 注册 function schema、调用模式与结果字段
- [ ] key 在两个注册表中一致，`enabled` 状态符合预期
- [ ] 后端 Pydantic 模型包含 `group` 并透传到 DTO
- [ ] 前端 `ToolItem` 类型包含 `group`
- [ ] 工具箱按分组和顺序正确展示
- [ ] 需要异步执行时明确是独立作业还是标准 Flow，不能混用
- [ ] 图形工具完成数据闭环与 PNG/SVG 导出
- [ ] 亮/暗主题、空数据、错误状态均已处理
- [ ] 新增依赖已写入 `frontend/package.json` 或 `pyproject.toml`
- [ ] 工具 README.md 已补充

## 安全与边界

- 工具参数由 schema 约束，模型只能填写声明过的字段；需要确认的工具必须走人工确认。
- 文件访问限定在当前用户工作区，禁止路径逃逸。
- 工具执行结果属于过程证据，不代表科学结论；涉及真实数据和正式交付时仍须人工审核。
- 新增工具不得绕过模块注册、权限校验和审计。

## 相关页面

- [生信工具箱](../features/toolbox)
- [MCP 体系](../architecture/mcp)
- [沙箱与工作台](../architecture/sandbox)
- [开发规范](index)

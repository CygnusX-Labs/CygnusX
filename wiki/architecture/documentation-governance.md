# 文档治理与证据等级

CygnusX 的文档不是“写得越像现状越可信”，而是按**文档类型**和**证据等级**分层。开发、评审和发布时，必须知道一条结论来自代码、as-built、规范、提案还是历史快照。

> 本页解释 `ARCHITECTURE_DESIGN/` 的治理规则，以及 Wiki 与知识库的边界。新增/重命名架构文档时先读本页和 [`ARCHITECTURE_DESIGN/README.md`](../../ARCHITECTURE_DESIGN/README.md)。

## 文档类型

| 类型 | 定义 | 可信度 | 使用方式 |
| --- | --- | --- | --- |
| **as-built** | 记录仓库当前已落地架构 | 最高（仍需与代码核对） | 修改前必读，作为模块边界与门禁依据 |
| **规范** | 约束“应该怎么改” | 高 | 修改时必须遵守 |
| **提案/规划** | 目标态设计，未完全实施 | 不得当作现状 | 只用于理解方向与取舍 |
| **历史快照** | 某时点的施工/评审/交接记录 | 部分引用已失效 | 只作背景，不覆盖活动基线 |
| **deprecated** | 不再演进的历史文档 | 低 | 只作历史参考 |

`docs/` 下的方案、评审和交接记录属于历史档案；提案与 vision 文档不能作为现状依据。

## 事实来源优先级

```text
当前代码 / 配置 / Alembic 迁移 / 部署文件
  > ARCHITECTURE_DESIGN as-built
  > 规范文档
  > 提案 / 规划
  > 历史快照
  > deprecated / docs 历史档案
```

出现冲突时：

1. 以代码、配置和迁移为准；
2. 更新 as-built 文档；
3. 在变更说明中记录差异和影响；
4. 不要用旧文档“证明”新代码的行为。

## 命名与目录规则

现行规则（2026-10-03 起）：

1. 文件名统一 `CygnusX_<领域>_<xxx>.md`；
2. 领域段紧随前缀：`agent`、`chat`、`database`、`frontend`、`knowledge`、`log`、`mcp`、`memory`、`network`、`platform`、`sandbox`、`skill`、`storage` 等；
3. 主体使用 snake_case，不用连字符或中文文件名；
4. **文件名不带日期**；基线日期/快照日期写在文档头部和索引描述中；
5. 不再演进的方向移入 `deprecated/`，同样按规则命名，并登记到索引“废弃归档”；
6. 新增文档必须同步登记到 `ARCHITECTURE_DESIGN/README.md`。

时点性文档（快照）只增不改；活动基线（as-built/规范）随代码更新。

## 文档索引的分工

| 入口 | 作用 |
| --- | --- |
| 根 `README.md` | 平台定位、能力边界、路线图与生态 |
| `ARCHITECTURE_DESIGN/README.md` | 架构文档索引、文档类型、合并/更名记录 |
| `AGENTS.md` | 工程协议、命令门禁、保护模块与雷区 |
| `wiki/README.md` | 面向用户/开发/运维的操作文档总览 |
| `docs/knowledge/` | 实验室 SOP、方法与平台使用知识 |
| `docs/` 其他目录 | 历史档案，不作为现状依据 |

外部独立文档：

- [`mcp-server/ARCHITECTURE.md`](../../mcp-server/ARCHITECTURE.md)：MCP 外部通道终态与确认契约；
- [`tool_configs/tools_design.md`](../../tool_configs/tools_design.md)：工具页面专项规范。

## Wiki 的写作边界

Wiki 与架构文档分工：

| 内容 | 放在哪里 |
| --- | --- |
| 稳定用法、操作步骤、排障 | Wiki |
| 模块边界、数据流、修改门禁 | `ARCHITECTURE_DESIGN/` |
| 实验方法、SOP、领域知识 | `docs/knowledge/` |
| 实施记录、评审、交接 | `docs/` 历史档案 |

Wiki 不写：

- 密钥、真实服务器地址、用户数据路径；
- 内部系统提示词或完整 Agent 人设；
- 未审核的设计方案；
- 会把历史证据冒充当前能力的结论。

## 知识库同步

`docs/knowledge/meta.yaml` 将 `wiki/**/*.md` 定义为自动集合，同步时索引每篇正文并排除 `_Sidebar.md`。

```bash
make sync-knowledge      # 同步 Wiki 与知识库源
make knowledge-reindex   # 仅重建既有文档分块与向量
```

改 Wiki 后先核对链接、命令和配置名，再同步；同步依赖可用的 Web/数据库环境。

## 变更文档的流程

1. 先改代码/配置/迁移；
2. 更新对应 as-built 文档（当前事实、图、验证状态）；
3. 更新 Wiki 操作页（如果用户可见行为变了）；
4. 同一逻辑变更放在同一提交；
5. 只有确实不再演进的方向才移入 `deprecated/`，不要用删除掩盖历史。

## 关联文档

- [Wiki 维护与知识库同步](../documentation-maintenance) · [架构与数据索引](index)
- [`ARCHITECTURE_DESIGN/README.md`](../../ARCHITECTURE_DESIGN/README.md) · [`AGENTS.md`](../../AGENTS.md)

# Skill 体系

Skill 是 Agent 的**按需知识与操作规程层**：它把领域方法、检查清单、脚本和参考资料封装成可版本化、可绑定、可审计的技能包。平台 Skill 与编码助手 Skill 是两套独立体系，不能混为一谈。

> **当前状态**：平台 Skill 的磁盘安装、数据库索引、三层渐进披露、会话 pin 与调用审计已实现；Studio capability catalog 是另一条沙箱能力路径，不属于平台 Skill。

## 两套 Skill 系统

| 体系 | 位置 | 使用者 | 加载方式 |
| --- | --- | --- | --- |
| **平台 Skill** | `data/ai/skills/<skill_id>/` | 平台业务 Agent | DB 索引 + `skill_ids` 绑定 + `use_skill` |
| 编码助手 Skill | `.agents/skills/`（约 561 个 `bio-*`） | Kimi CLI 等编码助手 | 目录扫描加载，与平台运行时无关 |

平台内置市场位于 `data/ai/skill_marketplace/`（约 600 个可安装技能，含全部 `bio-*`），安装后复制到 `data/ai/skills/`。**磁盘目录是内容真相源**，数据库保存索引、版本快照和调用审计。

## 存储与数据模型

```text
data/ai/skill_marketplace/<skill_id>/     内置市场（随仓库发布）
data/ai/skills/<skill_id>/                已安装技能（真相源）
    ├─ SKILL.md                           元数据 + 正文
    ├─ scripts/                           脚本（永不进入模型上下文）
    ├─ references/                        参考资料（L3 按需读取）
    └─ assets/                            资源（L3 按需读取）

DB:
  skills             L1 元数据索引 + L2 正文缓存（prompt 列，兜底）
  skill_versions     全量内容快照（revision 递增，审计/回滚/会话 pin）
  skill_invocations  每次 use_skill 的调用审计
```

安装、更新、回滚和删除由管理端服务完成：`write_skill_folder` / `rewrite_skill_md` / `read_skill_body` / `read_skill_resource` / `remove_skill_folder`。`skill_id` 优先取 frontmatter，否则由 name 派生；市场安装以文件夹名为规范键，保证 DB/磁盘/市场三处一致。

## 绑定与注入

- Agent 声明：`data/ai/*.yaml` 的 `skill_ids`，同步到 `AgentTemplateModel.skill_ids`（JSONB）；用户级能力在 `UserCapabilityModel.skill_ids`。
- 注入上限：`MAX_ACTIVE_SKILLS = 10`；未绑定有效技能时，`use_skill` / `skill_resource` **根本不注入**。
- 会话创建时只注入每个技能的 name 与 description（L1），控制首轮 token。
- 会话首轮固定 `skill_pins`；运行中升级或回滚不改变当前会话上下文，新会话才读取新快照。

## 三层渐进披露

| 层级 | 内容 | 进入上下文的方式 |
| --- | --- | --- |
| L1 | 技能名称、描述 | 系统提示词，常驻但很短 |
| L2 | `SKILL.md` 正文 | 模型调用 `use_skill` 后加载 |
| L3 | `references/`、`assets/` | 模型调用 `skill_resource` 按需读取 |

正文加载优先级：**会话 pin 的 revision 快照 → 磁盘实时正文 → 数据库 prompt 兜底**。`skill_resource` 只允许 `references/` 与 `assets/`，脚本永不进入模型上下文，单次读取上限 200 KB。

## 运行时与审计

```text
模型选择 use_skill(skill_id)
  → runtime 校验 skill_id 是否在本会话挂载集合
  → 未挂载直接拒绝
  → 读取正文 / 资源
  → SSE ChatChunk(type="skill", phase=invoked/completed/failed)
  → skill_invocations 落库（版本、来源、耗时、用户、会话、消息）
```

AgentTeams 房间会把技能事件投影为 `skill.finished` / `skill.failed` / `skill.manual_review` 发言，便于协作审计。

`skill_route` 是平台内置的**只读工具**，用于按查询检索可用 Skill 并返回匹配、置信度和适配检查；它不是独立注册的 `skill_router` Agent，也不绕过 `skill_ids` 绑定。

## 与沙箱 capability 的区别

| 概念 | 作用 | 授权源 |
| --- | --- | --- |
| 平台 Skill | 注入领域知识与操作规程 | Agent YAML `skill_ids` / DB 绑定 |
| Studio capability | 决定沙箱能执行代码、浏览器或文档能力 | Agent YAML `features.studio.sandbox_capabilities` |

不要把 Skill 当成沙箱权限，也不要用 Skill 绕过工具白名单。

## 维护要点

1. 新增平台技能：放入市场目录 → 管理端安装 → 绑定 Agent → 验证 L1/L2/L3 与审计记录。
2. 修改技能正文：走管理端更新生成新 revision；不要直接改数据库中的 `prompt` 缓存。
3. 技能目录包含脚本时，确认脚本不会被模型读取；脚本执行应走受控沙箱或工具，而不是 Skill 资源通道。
4. 区分 `.agents/skills/` 与 `data/ai/skills/`；前者不参与平台 Agent 装配。

## 代码锚点

| 组件 | 位置 |
| --- | --- |
| Skill 服务 | `src/cygnusx/application/services/skill_service.py` |
| 领域工具构建 | `src/cygnusx/domain/skill/services.py`（`build_skill_tools`） |
| 磁盘读写 | `src/cygnusx/infrastructure/skills/skill_store.py` |
| 运行时执行 | `chat/runtime_support.py`、`chat/skill_execution.py` |
| 数据模型 | `skills` / `skill_versions` / `skill_invocations` |

## 关联文档

- 权威基线：[`CygnusX_skill_architecture.md`](../../ARCHITECTURE_DESIGN/CygnusX_skill_architecture.md)
- [Agent 运行时](agent-runtime) · [沙箱与执行隔离](sandbox) · [MCP 体系](mcp)
- [AI 助手与工作台](../features/ai-chat)

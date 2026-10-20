# 开发规范

本章节面向 CygnusX 开发者，说明如何新增模块、设计 API、编写前端页面、管理数据库迁移、扩展
Flow/工具以及执行验证。修改前先读 [Wiki 总览](../README)、`AGENTS.md` 和
`ARCHITECTURE_DESIGN/README.md` 中对应的 as-built 文档；`ARCHITECTURE_DESIGN/` 是唯一架构权威库，
`docs/` 仅为历史档案。

## 内容导航

- [模块设计与接入](module-design) — 新增模块的设计原则、文档模板与评审问题
- [前端规范与工具箱](frontend-conventions) — Vue 3 目录组织、UI/主题/响应式约定
- [API 设计约定](api-design) — REST/WebSocket 接口、DTO、错误码与分页规范
- [项目结构](project-structure) — 顶层目录、后端分层、前端组织与保护资产
- [数据库迁移](database-migrations) — Alembic 迁移、单一 head、schema 漂移对账
- [分析流程扩展](flow-extension) — 六段 Flow schema、固定 MCP 工具与接入清单
- [生信工具接入](bio-tool-guide) — 双注册表、ToolBridge 模式与交付闭环

## 开发前必读

1. 先读 `ARCHITECTURE_DESIGN/CygnusX_platform_design.md` 的设计原则与模块类型划分，再核对对应
   域的 as-built 文档；提案、vision 和 `deprecated/` 内容不得当作现状依据。
2. 新增模块前，按[模块设计与接入](module-design)完成可审查设计文档，并同步到
   `ARCHITECTURE_DESIGN/README.md` 索引。
3. 前后端接口先定契约（Pydantic DTO ↔ TypeScript types），再写页面。
4. 所有资源操作必须校验认证、角色与所属关系；Agent 不得获得 shell、流程 YAML 或数据库写权限。
5. 改配置、镜像、子模块或保护资产前，先确认[变更验证矩阵](#变更验证矩阵)与同步清单。

## 最低验证命令

```bash
# 后端
uv sync --frozen
uv run ruff check src/ tests/
uv run mypy src/cygnusx/
uv run python scripts/check_migrations.py
uv run pytest tests/unit tests/e2e -q -m "not quarantine"

# 子工程
(cd integrations/agentteams/bridge && uv run pytest -q)

# 前端
cd frontend
npm ci
npx vitest run
npx vue-tsc --noEmit
npm run build

# 配置/镜像
make validate-image-mapping
uv run python scripts/test_studio_agent_runtime.py
```

## 变更验证矩阵

| 改动类型 | 最小验证 | 必须追加的条件 |
| --- | --- | --- |
| 核心逻辑（domain/application/chat 链路） | lint + type-check + 单测 | 改 Chat 执行/事件流 → E2E + LangGraph 沙箱用例 |
| 接口契约（API schema/DB 模型/MCP 工具） | 单测 + `make check-migrations` | 改响应结构 → `tests/integration`；改 MCP 确认契约 → 双表面等价测试 |
| 前端（组件/store/api） | `npm run type-check` + `npm test` | 动路由/布局/构建 → `npm run build`；SSE、上传、终端需手工 E2E |
| 配置（Agent YAML/prompts/image-mapping/CygnusX.yaml/MODULE_LOCKED） | `make validate-image-mapping` + 单测 | 实际加载验证；改模块注册需全栈启动验证门禁 |
| 子模块（pipelines/FlowFrame） | 子仓自身测试 | 父仓只提交指针；流程契约变更须 FlowFrame v2.0 评审 |
| 纯文档 | 无需测试 | 遵守文档治理：活文档不带日期，快照带 `_YYYY-MM` |

## 常见盲区

- **CI 不跑 mypy，也不跑 `tests/integration`**（需真实 DB/Redis），本地必须补跑。
- 前端 `npm test` 通过 ≠ `npm run build` 通过；build 内含 `vue-tsc -b`。
- `-m "not quarantine"` 会静默隔离存量失败；改动相关域时先查 quarantine 是否已有同类用例。
- 多分支并行迁移会产生多个 Alembic head，提交前必须 `make check-migrations` 与
  `make check-alembic-heads`。
- 修改镜像或 Agent 运行时画像必须跑 `make validate-image-mapping` 与
  `scripts/test_studio_agent_runtime.py`。
- 父仓 `git status` 中的子模块 “modified content” 无法从父仓提交，必须进入子仓提交。

## 相关页面

- [架构总览](../architecture/index)
- [文档治理](../architecture/documentation-governance)
- [部署与运行](../deployment/index)
- [运维手册](../operations/index)

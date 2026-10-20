# Wiki 维护与知识库同步

Wiki 是 CygnusX 面向用户、管理员和开发者的稳定说明层。它不复制全部仓库 Markdown，而是从当前
实现和权威文档中提炼可操作、可检索的内容；日期归档、实施草稿、内部提示词和自动生成报告不作为
Wiki 正文来源。仓库级文档类型、事实优先级和命名规则见
[文档治理](architecture/documentation-governance)。

## 更新原则

1. 先核对当前代码、`.env.example`、`Makefile`、根目录 `README.md` 和对应模块的 as-built 文档。
2. 变更功能时同时更新对应 Wiki 页面、导航页和面向用户的知识库说明。
3. 有时间敏感或环境相关的内容，写清适用条件，并链接到命令帮助或配置模板，而不是复制易过期值。
4. 不把密钥、真实服务器地址、用户数据路径、内部系统提示词或未审核设计方案写入 Wiki。
5. 区分“已实现 / 已隔离测试 / 已运行验证 / 已端到端验证 / 已生产批准”，不把代码存在写成
   运行验收通过。

## 事实优先级

```text
代码 / 配置 / 迁移  >  ARCHITECTURE_DESIGN as-built  >  规范
  >  提案 / vision  >  历史快照  >  deprecated
```

- `ARCHITECTURE_DESIGN/` 是唯一架构权威库；`docs/` 仅为历史档案。
- 提案和 vision 文档可以解释意图，但不能作为当前能力证据。
- 发现文档与代码冲突时，以代码为准并修正文档；无法从代码确认的事实标记 `[待人工确认]`。

## 当前主题与核对来源

| Wiki 主题 | 优先核对来源 |
| --- | --- |
| 快速开始、部署、运维、安全 | `README.md`、`.env.example`、`Makefile`、`deploy/` |
| AI、Agent、工作台和协作室 | `data/ai/`、`src/cygnusx/application/services/`、`ARCHITECTURE_DESIGN/`、测试 |
| 科研数据、Dataset、交付与证据 | `ARCHITECTURE_DESIGN/CygnusX_*research*`、`dataset`、`download`、`treasure_mouse` |
| 知识库 | `docs/knowledge/`、知识库服务和同步脚本 |
| Flow、工具和生信分析 | `flows/`、`tool_configs/`、`pipelines/`、`Protocol/FlowFrame/` |
| 数据库与存储 | `alembic/`、ORM 模型、`scripts/check_schema_drift.py`、`ARCHITECTURE_DESIGN/CygnusX_storage_architecture.md` |
| 前端与 API | `frontend/`、`src/cygnusx/api/`、DTO 和相关测试 |

## 新增或修改页面

1. 按现有章节放置页面：`architecture/`、`research/`、`features/`、`development/`、
   `deployment/`、`operations/`、`security/`。
2. 页面内链接使用 GitHub Wiki 风格的无扩展名相对路径（如 `../architecture/database`）。
3. 同步更新 `wiki/README.md` 的页面索引与 `wiki/_Sidebar.md` 导航。
4. 涉及用户可见功能时，同时检查 `docs/knowledge/platform/` 是否需要更新。
5. 不新建时间快照式页面；需要快照时在 `ARCHITECTURE_DESIGN/` 按治理规则命名。

## 知识库索引

`docs/knowledge/meta.yaml` 已将 `wiki/**/*.md` 定义为自动集合；同步时会索引每篇正文，并排除
`wiki/_Sidebar.md`。编辑 Wiki 后运行：

```bash
make sync-knowledge
```

若仅需要重建既有文档的检索分块和向量，可运行 `make knowledge-reindex`。

## 自动校验

```bash
make check-doc-counts
# 等价于：uv run python scripts/check_doc_counts.py
```

`scripts/check_doc_counts.py` 直接解析结构化事实源，再核对文档中已登记的当前事实断言：

| 事实 | 解析来源 |
| --- | --- |
| ORM 表数量、模型模块数量 | `src/cygnusx/infrastructure/database/models/`（AST 扫描） |
| Alembic 迁移数量 | `alembic/versions/*.py` |
| 镜像清单数量 | `deploy/image-mapping.yaml` |
| 静态工具 / 前端工具 / Studio 工具 | `tools_schema.yaml`、`tools_setting.yaml`、`STUDIO_TOOL_NAMES` |
| 安全清单条目 | `wiki/security/index.md` 复选框 |

- 只校验注册在脚本 `ASSERTIONS` 表中的现状断言，不做全库数字正则替换；新增易漂移事实时
  同步登记断言。
- 带“历史快照 / 历史记录 / 施工记录”等标记或日期的段落按历史值跳过，不会被回写。
- 未登记但仍被发现的可疑计数输出为人工审核项（`--strict-scan` 可将其升级为失败）。
- 该脚本已接入后端 CI job，与迁移校验同批执行。

## 发布前检查

- [ ] 新增页面已加入 README 索引和 Sidebar
- [ ] 内部链接无悬空，标题锚点一致
- [ ] 事实与代码/配置一致，证据状态标注清楚
- [ ] 动态计数已通过 `make check-doc-counts`
- [ ] 未包含密钥、真实地址、用户数据路径或内部提示词
- [ ] 已运行知识库同步，检索可命中新页面

## 相关页面

- [文档治理](architecture/documentation-governance)
- [Wiki 总览](README)
- [开发规范](development/index)

# 数据库迁移

Alembic 是 CygnusX schema 的唯一事实来源。ORM 模型只描述代码期望，实际表结构以迁移链为准；
生产容器在 `RUN_MIGRATIONS=1` 时执行迁移并做 schema 漂移对账，失败即拒绝启动。

## 常用命令

```bash
make migrate                    # 升级到最新
make migrate-new m="add xxx table"
make migrate-rollback           # 回滚一个版本
make migrate-merge              # 合并多分支
make check-migrations           # 迁移链静态校验
make check-alembic-heads        # 检测多 head（>1 告警）
```

## 迁移链规则

- 每个迁移必须能解析 `revision`、`down_revision`、`depends_on`，父迁移真实存在。
- 迁移链只能有一个 root，且拓扑连通；`alembic heads` 必须唯一。
- 多人并行改模型后，rebase 或合并前必须检查 head；出现多 head 用 `make migrate-merge` 收敛。
- 迁移文件一旦进入共享分支不得改写历史 revision；修复应新增迁移。

`make check-migrations` 覆盖前三条，`make check-alembic-heads` 单独告警多 head，二者都应在
提交前通过。

## 新增迁移流程

1. 修改 `src/cygnusx/infrastructure/database/models/` 下的 ORM 模型。
2. 确认新模型已在 `models/__init__.py` 注册；未注册的模型不会被 Alembic autogenerate 发现。
3. `make migrate-new m="..."` 生成迁移，人工审查 `upgrade()` / `downgrade()`。
4. 在空库和现有库上分别验证升级；涉及回滚的变更验证降级路径。
5. 运行 `make check-migrations && make check-alembic-heads`。
6. 涉及向量列时使用项目自定义 `Vector` 类型，并确认 pgvector 扩展已启用。

## Schema 漂移对账

`scripts/check_schema_drift.py` 对比 ORM 与实际数据库：

- 容器 entrypoint 在 `RUN_MIGRATIONS=1` 时执行，发现漂移直接 fail-fast。
- 本地可单独运行，用于定位“模型已改、迁移漏写”或“库里有历史遗留表”的问题。
- `mem0_memories` 是受保护的迁移残留，列入 `_NON_ORM_TABLES` 豁免；不得为对齐而删除。
- 参考基因组模块使用独立 SQLite/FTS5，不纳入 Alembic 对账。

## 常见错误

### `down_revision` 指向错误

迁移应指向创建其依赖表的父迁移，否则空库升级会报：

```text
sqlalchemy.exc.ProgrammingError: relation "xxx" does not exist
```

### Multiple Heads

多人并行创建迁移且未合并时出现。修复：

```bash
make migrate-merge
```

### 模型改了但 autogenerate 为空

通常是模型未在 `models/__init__.py` 导入，或列类型不在 Alembic 的 compare 范围。先确认注册，
再检查自定义类型。

### 线上启动即失败

entrypoint 的迁移或漂移对账失败会阻止启动。先看容器日志中的具体差异，不要通过关闭对账绕过；
确属历史遗留时，按受保护表清单评估豁免，而不是删除数据。

## 相关页面

- [数据库架构](../architecture/database)
- [存储与目录](../architecture/storage)
- [开发规范](index)

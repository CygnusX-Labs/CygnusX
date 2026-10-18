# RI095 RC01 Runtime Foundation Closure

Run ID: `rc01-rc02-20261017-attempt1`  
Commit: `d9c92cf6ee1c1e8de902c2b897b93f60b4f00f33`  
时间：2026-10-17 Asia/Shanghai

结论：**PARTIAL**。本轮完成了迁移 DAG、Compose 保护和前端锁文件的静态修复审计；真实 Docker、数据库升级和完整前端安装/构建没有在当前环境完成。历史真实运行证据保留在 `ri095-20261017-attempt1`，不自动继承为本轮结果。

## 迁移审计

当前静态 DAG 为 111 个 revision、唯一 head `projectreport01`、唯一 base `08ab25316cc1`。`c1d2e3f4b5a6`（ALTER `mcp_versions`）现在显式依赖 `h6i7j8k9l1m3`（CREATE `mcp_versions`），离线规划确认 CREATE 排在 ALTER 之前且没有重复步骤。证据：[migration-dag.json](../../evidence/runtime-acceptance/rc01-rc02-20261017-attempt1/migration-dag.json)、[migration-check.log](../../evidence/runtime-acceptance/rc01-rc02-20261017-attempt1/migration-check.log)。

历史调查曾在空库真实复现 `mcp_versions does not exist`，修复后在 disposable 镜像中迁移到 head；该历史证据的文件 SHA 已由本轮索引复核，无篡改。由于没有可信的旧数据库 schema、`alembic_version`、数据备份和报告基线，本轮不能证明已有数据库升级兼容性，旧模型升级 Gate 仍 **BLOCKED**。禁止用 `stamp`、reset、downgrade 或重复 CREATE/ALTER 代替升级验证。

## Compose 与卷

三个 `/tmp` tmpfs 定义均为单一引号标量 `"/tmp:uid=10001,gid=10001,mode=1777"`。控制器现在拒绝 split tmpfs、错误 UID/GID、外部网络、宿主端口、Docker socket、外部数据库、分析写权限和未批准变量，共八项负例；[compose-static.log](../../evidence/runtime-acceptance/rc01-rc02-20261017-attempt1/compose-static.log) 为本轮 PASS_STATIC。

`permissions` 入口会在真实容器内检查 UID/GID 10001，并对 `/tmp` 和 `/acceptance-storage` 做写入、fsync、回读。Docker socket 当前再次返回 `operation not permitted`，因此真实容器启动、UID/GID 和卷写入仍 **BLOCKED**。

## 前端确定性构建

本轮复现了原始 `npm ci` 错误：锁树缺少两个 optional Sass 平台包的嵌套占位条目。`frontend/package-lock.json` 仅增加：

```text
node_modules/sass-embedded-all-unknown/node_modules/sass
node_modules/sass-embedded-unknown-all/node_modules/sass
```

`npm ci --dry-run --offline` 在全新临时目录通过锁树校验（646 packages）。真实 `npm ci` 仍受当前网络/缓存限制，未取得完整安装结果；因此没有生成当前源码的真实 dist，也没有报告前端构建 PASS。原始错误、候选锁文件和本轮摘要见 [npm-ci-final.log](../../evidence/runtime-acceptance/rc01-rc02-20261017-attempt1/npm-ci-final.log)、[frontend-source-lock-sha256.txt](../../evidence/runtime-acceptance/rc01-rc02-20261017-attempt1/frontend-source-lock-sha256.txt)。

`frontend/Dockerfile` 不存在；实际前端镜像入口是 `deploy/docker/Dockerfile.frontend`。该 Dockerfile 的 `npm ci` 依赖当前锁文件，下一次有网络的干净构建必须执行 `npm ci`、`npm run build` 并记录 Node、npm、commit 和 dist SHA-256。不得继续使用不明来源旧 dist 作为 RC01 通过证据。

## 本轮修改

- `alembic/versions/c1d2e3f4b5a6_add_contract_digest_to_mcp_versions.py`：已有工作树修复，依赖 `h6i7j8k9l1m3`。
- `deploy/acceptance/compose.yml`：已有工作树修复，tmpfs 标量引号。
- `deploy/acceptance/control.py`、`runtime.py`、`checks.py`：新增 UID/GID、tmpfs 和私有卷写回读保护。
- `frontend/package-lock.json`：新增两个 optional Sass 嵌套锁条目。
- `deploy/acceptance/audit_migrations.py`：新增离线 DAG 规划审计。

这些修改均未提交；工作树存在大量与本轮无关的既有修改，不能直接整体提交。生产配置、生产数据库和旧制品未触碰。

## RC01 状态

| 项目 | 状态 |
|---|---|
| Alembic 拓扑/唯一 head | PASS_STATIC |
| 空库升级缺陷修复审计 | PASS_STATIC；历史 runtime 证据存在 |
| 已有数据库升级 | BLOCKED：缺可信旧库基线 |
| Compose 隔离/八项保护 | PASS_STATIC |
| 实际容器 UID/GID/卷回读 | BLOCKED：Docker 权限 |
| npm 锁树校验 | PASS_STATIC |
| npm 完整安装与当前源码 build | BLOCKED：网络/缓存，无真实 dist |

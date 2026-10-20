# 运维操作

本章节面向运维人员，汇总日常排障、日志查询、Makefile 命令与数据库迁移管理的速查信息。
排障前先区分“部署就绪”“服务可用”“业务运行验证”三种状态，不要把健康检查通过当作业务验收。

## 内容导航

- [常用命令](common-commands) — Makefile 命令速查表
- [问题排查](troubleshooting) — 常见故障现象与排查路径
- [日志架构](../architecture/logging) — 日志目录、轮转与结构化字段
- [可观测性](../architecture/observability) — Trace / Metrics / 审计与会话排查
- [数据库迁移](../development/database-migrations) — 迁移、单一 head 与漂移对账

## 关键目录

```text
${CYGNUSX_DATA_ROOT:-/data/cygnusx}/
├── cygnusx_data/       # 集中数据区（DB、Redis、MinIO/JBrowse、知识库等）
├── users/<user_id>/    # 用户私有数据
├── uploads/            # 分片上传中转
├── bin/                # 外置二进制（EBIDownload、ossutil 等）
├── logs/               # 统一日志根目录（app / celery / nginx / snakemake / audit）
├── skills/             # 平台技能
├── .sandbox-pool/      # 沙箱池运行时
└── .tmp/               # 临时文件
```

数据根由 `CYGNUSX_DATA_ROOT`（兼容 `STORAGE_PATH`）解析；所有容器必须挂载同一路径。

## 日志入口

```bash
# 应用日志
tail -f ${CYGNUSX_DATA_ROOT}/logs/app/cygnusx.log
tail -f ${CYGNUSX_DATA_ROOT}/logs/app/error.log

# 按任务查 Celery 日志
tail -f ${CYGNUSX_DATA_ROOT}/logs/celery/tasks/{task_id}.log

# Nginx 5xx
jq 'select(.status >= 500)' ${CYGNUSX_DATA_ROOT}/logs/nginx/access.log
```

## 排障顺序

1. **入口**：Nginx / Web 健康检查、认证与模块门禁是否放行。
2. **应用**：`app/error.log` 与结构化日志中的 `trace_id` / `request_id` / `session_id`。
3. **异步**：Celery 任务状态、任务日志、队列积压与 reconcile 记录。
4. **存储**：数据根挂载、目录权限、磁盘容量、MinIO/S3 可达性。
5. **依赖**：PostgreSQL 连接池、Redis、模型 Provider、外部 MCP/下载服务。
6. **证据**：核对任务事件、审计记录和产物路径，确认是“未执行”还是“执行失败”。

## 证据边界

- 日志和指标证明系统行为，不证明科研结果正确。
- 长任务 >600s 走 Celery reconcile-only，Web 进程内不得直接运行。
- 下载、Dataset 分析、报告重跑等受源码门禁约束；排障时先确认开关与验收状态，
  见[科研证据边界](../research/evidence-boundaries)。

## 相关页面

- [部署与运维](../deployment/index)
- [日志架构](../architecture/logging)
- [可观测性](../architecture/observability)
- [安全模型](../architecture/security-model)

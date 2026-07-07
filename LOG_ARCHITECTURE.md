# OmicHub 日志架构说明

> 本文档描述 OmicHub 平台统一日志架构。新增或修改日志相关功能时，请对照本架构保持目录、格式与挂载方式一致。
>
> 关联文档：
> - `docs/26.7.7/omichub_log_unification_plan.md`（改造计划）
> - `README.md`「日志排查」章节（日常运维速查）

---

## 1. 设计目标

- **统一落盘**：所有日志（应用 / Nginx / Celery / Snakemake / 审计）统一落到宿主机 `/data/omichub/logs/`。
- **分级聚合**：可读文本 + 结构化 JSON + ERROR 独立日志，兼顾人读与机器抓取。
- **持久化**：通过 Docker bind mount 写入宿主机，容器重建不丢失。
- **保留实时流**：Celery 任务日志仍通过 Redis Pub/Sub → WebSocket 实时推送，并回写 DB；文本日志作为备份。
- **Loki 就绪**：JSON 日志与 Nginx JSON 访问日志可直接被 Promtail 抓取，后续平滑接入 Grafana Loki。

---

## 2. 目录结构

```
/data/omichub/logs/                  # 宿主机统一日志根目录
├── app/                             # 应用服务日志（web / beat / worker）
│   ├── omichub.log                  # 可读文本主日志（loguru 轮转）
│   ├── omichub.json.log             # 结构化 JSON 日志，供 Loki 抓取
│   └── error.log                    # ERROR 级别以上单独抽离
├── nginx/                           # Nginx 访问/错误日志
│   ├── access.log                   # JSON 结构化访问日志
│   └── error.log
├── celery/                          # Celery 任务执行日志（文本备份）
│   └── tasks/
│       └── {task_id}.log
├── snakemake/                       # 生物信息流程日志
│   └── {project_name}/
│       └── {timestamp}/
│           ├── stdout.log
│           └── stderr.log
└── audit/                           # 审计日志文本备份（当前写入 app/omichub.json.log）
    └── audit.log                    # 预留：后续可拆分到独立审计文件
```

---

## 3. 各服务写入方式

### 3.1 应用日志（web / beat / worker）

- **模块**：`src/omichub/core/logging.py`
- **入口**：`setup_logging()` 在 `src/omichub/main.py` lifespan 及各进程启动时调用。
- **环境变量**：
  - `SERVICE_NAME=web|beat|worker`：决定日志中的 `extra.service` 字段。
  - `OMICHUB_LOG_LEVEL`：日志级别，默认 `INFO`。
  - `OMICHUB_LOG_DIR`：日志根目录，默认 `/app/logs`；本地开发无法写入时自动回退到 `./logs`。
- **Sink**：
  1. `sys.stdout`：带颜色可读格式，便于开发。
  2. `/app/logs/omichub.log`：文本主日志，50 MB 轮转，30 天保留，zip 压缩。
  3. `/app/logs/omichub.json.log`：JSON 结构化，`serialize=True`。
  4. `/app/logs/error.log`：仅 ERROR 及以上。
- **使用方式**：代码中直接 `from loguru import logger` 即可，已全局绑定 `service`。

### 3.2 Nginx 日志

- **配置**：`deploy/docker/nginx/nginx.conf`（开发）、`deploy/docker/nginx/nginx.prod.conf`（生产）。
- **格式**：自定义 `omichub_json` log_format，字段包括：
  - `timestamp`, `service`, `remote_addr`, `request_id`, `method`, `uri`, `status`, `bytes`, `request_time`, `upstream_time`, `referer`, `user_agent`。
- **落盘**：`access_log /var/log/nginx/access.log omichub_json;`
- **挂载**：`docker-compose*.yml` 中将宿主机 `/data/omichub/logs/nginx` 挂载到容器 `/var/log/nginx`。

### 3.3 Celery 任务日志

- **模块**：`src/omichub/infrastructure/celery_app/logging.py`
- **机制**：`LoggedTask` 作为 Celery 全局 `task_cls`，每个任务自动创建独立文件 `/app/logs/celery/tasks/{task_id}.log`。
- **双写**：任务执行期间的 `logger.info/...` 同时进入任务专属文件和全局应用日志；现有 `publish_task_log` + DB 回写链路不变。
- **清理**：建议通过 crontab 定期清理超过 7 天的任务日志：
  ```bash
  find /data/omichub/logs/celery/tasks -type f -mtime +7 -delete
  ```

### 3.4 Snakemake 流程日志

- **模块**：`src/omichub/infrastructure/execution/local.py`
- **机制**：`LocalSnakemakeExecutor._execute` 在 subprocess 执行后，将 stdout/stderr 写入：
  ```
  /logs/snakemake/{project_name}/{timestamp}/
      stdout.log
      stderr.log
  ```
  其中 `project_name` 取自 `work_dir` 的末段目录名（通常是 task_id），`timestamp` 为 `YYYYMMDD_HHMMSS`。
- **挂载**：`docker-compose.worker.yml` 将宿主机 `/data/omichub/logs/snakemake` 挂载到容器 `/logs`。

### 3.5 审计日志

- **数据库表**：`audit_logs`（模型 `src/omichub/infrastructure/database/models/audit_log.py`）。
- **中间件**：`src/omichub/middleware/audit.py` 自动记录所有写操作（POST/PUT/PATCH/DELETE）。
- **文本备份**：DB 写入成功后，使用 `logger.bind(service="audit").info({...})` 写入 JSON 日志，字段包括：
  - `timestamp`, `user_id`, `method`, `path`, `resource_type`, `resource_id`, `status_code`, `ip`, `user_agent`, `result`。
- **查询示例**：
  ```bash
  jq 'select(.extra.service == "audit")' /data/omichub/logs/app/omichub.json.log
  ```

---

## 4. Docker 挂载矩阵

| 服务 | 容器内路径 | 宿主机路径 | 用途 |
|------|-----------|-----------|------|
| web | `/app/logs` | `/data/omichub/logs/app` | 应用日志 |
| beat | `/app/logs` | `/data/omichub/logs/app` | 应用日志 |
| worker | `/app/logs` | `/data/omichub/logs/app` | 应用日志 + Celery 任务日志 |
| worker | `/logs` | `/data/omichub/logs/snakemake` | Snakemake 流程日志 |
| nginx | `/var/log/nginx` | `/data/omichub/logs/nginx` | 访问/错误日志 |

> 注意：Celery 任务日志实际写入 `/app/logs/celery/tasks/`，因此共享 `/data/omichub/logs/app` 挂载即可。

---

## 5. 后续扩展（Loki 接入）

当前架构已为 Loki/Promtail 预留接入点：

- `app/omichub.json.log`、`nginx/access.log`、`audit` 均为 JSON，可直接被 Promtail 解析。
- 建议后续新增 `deploy/docker/docker-compose.monitoring.yml`：
  - `loki` 服务：存储与查询。
  - `promtail` 服务：挂载 `/data/omichub/logs` 只读，按 `service` label 推送。
- Grafana 查询示例：
  ```logql
  {service="app"} |= "ERROR"
  {service="audit"} | json | user_id="user_123"
  {service="nginx"} | json | status>=500
  ```

---

## 6. 清理策略

| 日志类型 | 清理方式 | 说明 |
|----------|---------|------|
| 应用主日志 / JSON / error | loguru 内置 `rotation="50 MB"`, `retention="30 days"`, `compression="zip"` | 自动轮转压缩 |
| Nginx access/error | 无内置清理 | 建议配置宿主机 `logrotate` 或定时任务 |
| Celery 任务日志 | 建议 crontab | `find ... -mtime +7 -delete` |
| Snakemake 流程日志 | 建议 crontab | `find ... -mtime +30 -delete` |

---

## 7. 排障速查表

| 现象 | 排查路径 |
|------|---------|
| 服务启动后 `/data/omichub/logs/app` 无文件 | 检查目录权限与挂载；容器内运行用户是否为 `PUID/PGID`；`OMICHUB_LOG_DIR` 是否可写 |
| Nginx 日志仍为旧格式 | 确认使用的是 `nginx.conf` 或 `nginx.prod.conf`，且 `access_log` 使用 `omichub_json` |
| Celery 任务无文件日志 | 检查 `task_cls=LoggedTask` 是否生效；任务目录 `/data/omichub/logs/app/celery/tasks` 是否可写 |
| Snakemake 日志目录为空 | 检查 worker 是否挂载 `/data/omichub/logs/snakemake:/logs`；`work_dir` 是否非空 |
| 审计日志未进 JSON | 检查 `AuditMiddleware` 注册顺序是否在 `AuthMiddleware` 之后；`logger.bind(service="audit")` 是否生效 |

---

## 8. 更新约定

新增日志相关功能时，请遵循：

1. **统一目录**：所有持久化日志必须落到 `/data/omichub/logs/` 下对应子目录。
2. **环境变量控制**：服务标识、日志级别、日志根目录通过 `SERVICE_NAME`、`OMICHUB_LOG_LEVEL`、`OMICHUB_LOG_DIR` 控制。
3. **JSON 优先**：供机器抓取的日志优先输出 JSON（loguru `serialize=True` 或 Nginx `escape=json`）。
4. **不影响主流程**：日志写入失败必须降级，不能导致请求/任务失败。
5. **同步更新本文档**：新增目录、环境变量或 sink 时，同步更新 `LOG_ARCHITECTURE.md` 与 `README.md`「日志排查」章节。

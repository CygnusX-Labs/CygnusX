# 部署与运维

本章节介绍 CygnusX 的 Docker 部署方式、生产环境检查清单以及日常更新回滚操作。部署拓扑和
安全基线分别以 `deploy/` 和[安全模型](../architecture/security-model)为准；页面中的命令是
入口，不代表当前环境已完成运行验收。

## 内容导航

- [Docker 部署](docker-deployment) — 主栈 + Worker 栈、跨机与生产部署入口
- [代码更新与回滚](update-rollback) — 日常刷新、镜像重建与回退策略
- [生产环境检查清单](production-checklist) — 安全、网络、密钥、SSL 等生产必填项
- [开启 Multi-Agent 与 AgentTeams](agentteams-enablement) — 意图路由、会诊、Bridge 令牌与预检

## 部署目录拓扑（`deploy/`）

```text
deploy/
├── docker/            主栈与 Worker 栈：compose 文件、Dockerfile、nginx、rocketmq 配置
├── agentteams/        AgentTeams 栈：Bridge/Gateway/Worker compose、env 模板、验证脚本
├── runtime-images/    Studio 分析运行时三件套（core/plot/scrna Dockerfile + build.sh）
├── studio/            OmicStudio 沙箱镜像、出站白名单代理、sandbox_agent
├── sandbox/           AI Copilot 代码执行沙盒镜像
├── mas/               MAS Apptainer Worker（systemd unit + env 模板）
├── logrotate/         宿主机日志轮转配置
└── image-mapping.yaml 镜像清单唯一权威源（当前 17 个，以清单与校验命令为准）
```

## 部署模式

CygnusX 采用**双栈分离**部署：

- **主栈**（`deploy/docker/docker-compose.yml`）：Web、数据库、缓存、入口与调度服务。
- **Worker 栈**（`deploy/docker/docker-compose.worker.yml`）：分析 Worker 与运行时镜像，可水平扩展。
- 两栈通过外部网络共享 Redis，并挂载同一数据根目录。默认根为 `/data/cygnusx`，可用
  `CYGNUSX_DATA_ROOT` / `STORAGE_PATH` 覆盖；所有容器必须使用同一路径，否则任务目录不可见。

## 镜像与运行时

- 镜像清单以 `deploy/image-mapping.yaml` 为唯一权威源，**禁用 `latest`**，tag 必须带 git SHA 短号。
- 变更 tag 需同步 6 处：清单 → config_files → build.sh/Makefile/.env.example/config.py →
  重建子镜像 → `make validate-image-mapping`。
- Agent 运行时画像变更必须同时通过 `make validate-image-mapping` 与
  `scripts/test_studio_agent_runtime.py`。
- 沙箱镜像以非 root（uid 10001）、`cap_drop=ALL`、只读根文件系统运行；`/workspace/input` 只读。

## 常用运维入口

| 操作 | 命令 |
|---|---|
| 启动主栈 | `make docker-up` |
| 启动 Worker 栈 | `make docker-up-worker` |
| 一键启动全部 | `make docker-up-all` |
| 日常代码改动刷新 | `make docker-dev-refresh` |
| 前端改动后完整重载 | `make docker-reload` |
| 彻底重建环境 | `make docker-start` |
| 启动 AgentTeams 栈 | `make docker-up-agentteams` |
| 修复权限事故 | `make docker-fix-permissions` |

## 部署后确认

1. `GET /health` 与登录链路可用；容器日志无迁移或 schema 漂移失败。
2. 模块注册生效：前端导航与后端 ModuleGate 一致，未出现模块 403/消失。
3. 数据根目录挂载一致：Web、Worker、Celery、Redis/MinIO 运行时目录均可读写预期路径。
4. 日志与指标可见：应用日志、Celery 任务日志、`/metrics`、审计事件。
5. 需要 AI 时确认 Provider Key、模型配置与 Agent 启用清单；需要协作室时确认 Bridge/Gateway 与令牌。

## 证据边界

- 容器健康、迁移成功和页面可访问只证明**部署就绪**，不等于科研链路验收通过。
- 下载、Dataset 分析提交、报告重跑等能力仍受源码门禁与默认关闭开关约束，
  见[科研证据边界](../research/evidence-boundaries)。
- 生产变更前先在预发布环境验证，并保留操作记录与回滚路径。

## 相关页面

- [数据库架构](../architecture/database)
- [存储与目录](../architecture/storage)
- [安全模型](../architecture/security-model)
- [可观测性](../architecture/observability)
- [运维操作](../operations/index)

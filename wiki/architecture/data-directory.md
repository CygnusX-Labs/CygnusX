# 数据目录结构

平台运行时数据遵循**单存储根**原则：默认根为 `${CYGNUSX_DATA_ROOT:-/data/cygnusx}`，业务代码中的路径由 `${STORAGE_PATH}` 经 `StoragePathFactory` 派生。部署时可以通过环境变量换根，但**不要在代码里写死 `/data/`**。

> 目录布局是存储协议的一部分；新增目录前先读[存储层](storage)与 [`Protocol/file_protocol.md`](../../Protocol/file_protocol.md)。

## 顶层布局

```text
${CYGNUSX_DATA_ROOT:-/data/cygnusx}/
├── users/{user_id}/          用户私有区（项目、上传、输入与产物）
├── platform/                 平台共享资产（参考数据、公共资源）
├── tasks/                    历史任务目录（legacy 只读）
├── inbox/                    收件箱（逻辑归属与物理目录分离）
├── archives/                 工作区归档包
├── logs/                     五域日志（app/celery/nginx/snakemake/audit）
├── skills/                   平台 Skill 可写共享卷
├── .sandbox-pool/            Chat 沙箱 warm pool（必须与 Docker daemon 共享）
├── cygnusx_data/             部署运行时数据
│   ├── _pgdata/              PostgreSQL 数据（属主 postgres，rsync 用 -a）
│   ├── _redis/               Redis 持久化、Celery 队列、限流缓存
│   └── _minio/               MinIO 对象数据（如启用）
└── onlyoffice-data/          OnlyOffice 文档服务数据（如启用）
```

> 上述 `users/`、`platform/`、`tasks/`、`inbox/`、`archives/` 由路径工厂和目录登记链创建；不同部署的实际子目录以当前配置和 sync 结果为准。

## 用户区与平台区

| 区域 | 路径 | 规则 |
| --- | --- | --- |
| 用户私有 | `users/{user_id}/projects/...` | owner 隔离；目录名不出现 UUID；以 realpath 校验 |
| 平台共享 | `platform/` | 参考数据、共享资产；只由平台流程写入 |
| 收件箱 | `inbox/` | 逻辑归属与物理目录分离，避免移动大文件 |
| 任务运行 | 项目 Run 目录 | 新任务使用 `StoragePathFactory.create_project_run_dir()` |
| 历史任务 | `tasks/` | legacy 只读，不再新建 |

日志目录的详细规则见[日志架构](logging)，不要自行在数据根下新增日志子目录。

## 运行时数据与业务数据

| 目录 | 作用 | 备注 |
| --- | --- | --- |
| `_pgdata/` | PostgreSQL 全部关系型数据 | bind mount，属主 postgres uid 70 |
| `_redis/` | Redis 持久化、队列、限流 | 缓存类，丢失可重建 |
| `_minio/` | 对象存储数据 | 若使用外部 S3 则不启用 |
| `cygnusx_data/` | 部署运行时数据的父目录 | 与业务数据根分离，便于备份 |

业务数据的权威记录仍在 PostgreSQL 和 FileRecord；磁盘目录只是一侧事实，必须通过 sync 对账。

## 迁移与备份

```bash
make docker-down-all
sudo rsync -aP --info=progress2 /data/cygnusx/ <目标机>:/data/cygnusx/
```

迁移前同时备份：

- 数据库（或 `_pgdata` 一致性快照）；
- `.env`；
- `data/worker_config.yaml`；
- 外部对象存储配置；
- 平台 Skill 目录与工作区归档。

恢复后：

1. 运行迁移与 `check_schema_drift.py`；
2. 执行 sync 对账并清理幽灵目录；
3. 验证用户目录、任务产物、知识库附件、参考数据可读；
4. 不要只复制 `docs/knowledge/` 就认为在线知识库已恢复。

## 常见错误

| 错误 | 后果 | 正确做法 |
| --- | --- | --- |
| 代码写死 `/data/cygnusx` | 换根后路径错位 | 使用 `STORAGE_PATH` 与路径工厂 |
| 新建目录不登记 | sync 视为幽灵目录 | 调用 `ensure_directory_chain()` |
| 在用户区创建平台目录 | 权限与展示混乱 | 平台资产放 `platform/` |
| 复制 `_pgdata` 时不保属主 | PostgreSQL 启动失败 | 使用 `rsync -a` 或一致性备份 |
| 把 `.sandbox-pool` 放私有 `/tmp` | 容器与 daemon 不可见 | 使用共享数据根下的默认路径 |

## 关联文档

- [存储层](storage) · [日志架构](logging) · [Docker 部署](../deployment/docker-deployment)
- 权威基线：[`CygnusX_storage_architecture.md`](../../ARCHITECTURE_DESIGN/CygnusX_storage_architecture.md)
- 协议：[`Protocol/file_protocol.md`](../../Protocol/file_protocol.md)

# 存储层

CygnusX 的运行时数据遵循**单存储根原则**：所有用户区、平台区、任务工作目录、日志和归档都由 `STORAGE_PATH` 派生，不允许在代码中硬编码 `/data/` 路径。存储布局是可部署、可迁移、可对账的协议，而不是若干约定俗成的目录。

> **当前状态**：路径工厂、用户/平台目录、sync 双向对账、幽灵目录清理、目录树展示元数据和 CI 守卫已落地；会诊工作目录前缀统一等遗留决策仍待裁决。

## 存储根解析

```text
get_storage_config()
  → 显式配置（STORAGE_PATH）
  → 兼容回退（旧配置）
  → 默认值 storage_path
        │
        ▼
StoragePathFactory（唯一路径构造入口）
  ├─ create_project_run_dir()
  ├─ create_user_dir() / create_task_dir()
  └─ ensure_directory_chain()（登记目录链）
```

- 用户可见目录**禁止出现 UUID**；项目/任务目录使用安全名称。
- 新建目录必须经 `ensure_directory_chain()` 登记，供 sync 与目录树消费。
- 新增路径前先查路径工厂是否已有方法；不要自己拼接字符串。

## 目录体系

```text
${STORAGE_PATH}/
├── users/{user_id}/                 用户私有区
│   ├── projects/                    项目目录
│   └── ...                          上传、分析输入与产物
├── platform/                        平台区（参考数据、共享资产）
├── tasks/                           任务运行目录（legacy 只读）
├── inbox/                           收件箱（逻辑视图与物理目录分离）
├── logs/                            五域日志
└── archives/                        工作区归档
```

| 规则 | 说明 |
| --- | --- |
| 用户隔离 | 每个用户只能访问自己的根目录；路径以 realpath 校验 |
| inbox 分离 | 逻辑归属与物理目录分离，避免移动大文件 |
| `tasks/` legacy | 历史任务目录只读保留，新任务走项目 Run 目录 |
| 系统目录 | 平台目录清单由代码定义；不要在用户区创建“平台专用”目录 |

## sync 与对账

```text
正向 sync：数据库记录 → 扫描磁盘 → 登记缺失/新增目录与文件
反向对账：磁盘目录 → 对照数据库 → 标记幽灵目录
         → _reconcile_ghost_directories 清理
```

- skip 名单覆盖系统目录、缓存、沙盒 shell 残留等模式，避免误登记。
- 幽灵目录治理的根因是“目录创建后未登记/删除后未清理”；修复靠路径工厂 + 登记链，而不是扩大 skip 名单。
- 目录树展示由后端驱动：`visible_in_tree` 控制是否展示，`aggregated` 控制是否聚合展示；前端不自行推断目录层级。

## 会诊工作目录

AgentTeams/会诊的工作目录统一挂载到容器 `/workspace/workdir`。历史上存在三种前缀并存和挂载断裂问题；当前已按路径工厂派生并修复挂载链路。

**遗留决策**：会诊目录前缀的最终统一方案仍待裁决（Gap 3）；在裁决前新增会诊路径必须使用路径工厂，不得引入第四种前缀。

## 防复发门禁

| 门禁 | 作用 |
| --- | --- |
| `/data/` 字面量 CI 守卫 | 禁止源码中出现硬编码数据根 |
| Worker 配置 fail-fast | `worker_config.yaml` 与 `.env` 数据根不一致时拒绝启动 |
| 路径工厂唯一构造入口 | 新增目录只能经 `StoragePathFactory` 和 `ensure_directory_chain()` |
| schema 漂移检查 | 目录元数据表与 ORM 对账 |

## 迁移与备份

```bash
make docker-down-all
sudo rsync -aP --info=progress2 /data/cygnusx/ <目标机>:/data/cygnusx/
```

迁移前同时备份数据库、`.env`、`data/worker_config.yaml` 和外部对象存储配置。恢复后：

1. 运行迁移与漂移检查；
2. 执行一次 sync 对账；
3. 验证目录树展示、任务产物和知识库附件可读；
4. 不要只复制 `docs/knowledge/` 就认为在线知识库已恢复。

## 对象存储与共享盘

- 小文件与工作区使用共享存储；大对象可接 MinIO/S3。
- 对象键与文件登记（FileRecord）必须成对维护；删除文件前先确认引用。
- 工作区归档（休眠打包）与对象存储是两套机制，归档包路径由路径工厂生成。

## 修改门禁

1. 改存储根或目录协议 → 读存储架构文档 + 文件协议，跑路径守卫与 sync 测试。
2. 新增自动建目录 → 必须登记目录链，并更新目录树元数据。
3. 改 Worker 挂载 → 同时验证 `worker_config.yaml`、Compose 与容器内路径。
4. 清理目录前先查引用/归档；禁止用 `rm -rf` 绕过对账。

## 代码锚点

| 组件 | 位置 |
| --- | --- |
| 存储配置/路径工厂 | `src/cygnusx/infrastructure/storage/` |
| sync/幽灵目录对账 | 存储同步服务与 `_reconcile_ghost_directories` |
| Worker 配置 | `data/worker_config.yaml`、`scripts/worker-compose.sh` |
| CI 守卫 | `/data/` 字面量检查 |

## 关联文档

- 权威基线：[`CygnusX_storage_architecture.md`](../../ARCHITECTURE_DESIGN/CygnusX_storage_architecture.md)、[`CygnusX_storage_workspace_gap_audit.md`](../../ARCHITECTURE_DESIGN/CygnusX_storage_workspace_gap_audit.md)
- 协议：[`Protocol/file_protocol.md`](../../Protocol/file_protocol.md)
- [数据目录结构](data-directory) · [数据库基础设施](database) · [日志架构](logging)

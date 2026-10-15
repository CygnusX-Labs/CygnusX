# CygnusX 存储层架构（as-built，2026-10-04）

> **状态**：活动基线（as-built）。存储根解析、目录协议、sync 对账、防复发门禁的唯一架构权威。
> **施工来源**：`docs/info/26.10.3/存储层优化实施方案.md`（Phase 0–3 已落地；Phase 4 注册表可延后）；调查依据 `CygnusX_storage_workspace_gap_audit.md`（审计快照，Gap 编号沿用）。
> **修改本域任何代码前必读**：§3 路径构造纪律、§6 防复发门禁。文件协议（用户可见目录、目录链登记）仍以 `Protocol/file_protocol.md` 为最高规范，本文不重复其内容。

---

## 1. 存储根与配置解析链

**单根原则**：全平台宿主数据根唯一锚点 = `Settings.storage_path`（`.env` 的 `STORAGE_PATH`，默认 `/data/cygnusx`；live 部署 `/data/omichub`）。任何代码不得写死宿主侧 `/data/...` 字面量（CI 守卫见 §6）。

**解析链**（`infrastructure/config/storage_config.py`）：

```
get_storage_config().data_root
  1) data/CygnusX.yaml storage.data_root     ← 优先
  2) settings.storage_path                     ← .env STORAGE_PATH
  3) 内置兜底 /data/cygnusx                     ← 仅缺省安装
```

**派生默认值**（`core/config.py`，2026-10-04 起）：历史上 19 处配置默认值各自写死 `/data/cygnusx`，换根部署后一部分被 env 覆盖、一部分仍指旧根，产生"同进程两套数据根"的静默故障（Gap 1）。现约定：

- 宿主侧路径默认值一律空值 + `model_validator` 从 `storage_path` 派生（`ebi_download_binary`、`blast_db_root`、`snakemake_conda_prefix`、`aliyun_skills_cache_dir`、`welcome_yaml`、`sandbox_data_dir`、`enrichment_data_mount`、`deg_data_mount`、`mas_workspace_root`、`sandbox_pool_host_dir` 等）；
- 显式 env / YAML 配置优先生效，派生只在空值时兜底；
- **容器内路径不受此约束**：R 工具容器挂载目标 `:/data/cygnusx`、Studio 平台只读挂载点 `/data/platform`、nginx 挂载约定是容器内规范路径，与宿主根无关。

**工具配置同样派生化**：`tools/{terminal,fastq_qc,jbrowse,download}/config.py` 的 Pydantic 配置类默认值空值派生 `storage_path`（YAML 显式配置优先）。换根部署只改 `.env` 的 `STORAGE_PATH` 一处。

**worker 栈一致性门禁**（Gap 2）：`scripts/render_worker_config.py` 渲染时校验 `data/worker_config.yaml` 的 `paths.shared_data_dir` 必须与仓库根 `.env` 的 `STORAGE_PATH` 一致，不一致 exit 1。`.env` 缺失（CI 环境）时跳过。

## 2. 目录体系（现状）

### 2.1 用户区（`{data_root}/users/{uid}/`）

| 目录 | 性质 | 逻辑展示 | 物理写入方 |
| --- | --- | --- | --- |
| `inbox/` | 系统目录 | **树中隐藏**（D2，后端元数据） | 上传（`_inbox_subdir`，子目录自动建） |
| `projects/` | 系统目录 | 可见 | 所有现代工具/流程 → `projects/{project}/runs/{analysis}-{ts}/` |
| `raw_data/` | 系统目录 | 可见 | 数据下载（默认已改 `downloads/`，历史任务兼容） |
| `workspace/` | 系统目录 | 可见 | chat 沙盒产物 `chat-output/{session}/output/`、上传附件 `chat-uploads/` |
| `downloads/` | 系统目录 | 可见 | 数据下载默认落点 |
| `temp/` | 系统目录 | 可见 | 临时文件（`file_temp_retention_days=30` 清理） |
| `tasks/` | **legacy 只读** | **树中隐藏**（D3，物理+DB 保留） | 不再新建；blast `_legacy_task_result_dir` 读取兼容 |

- 逻辑目录与物理目录**分离**：逻辑 `foo/bar`（file_records.directory / user_directories.path）的物理实体在 `inbox/foo/bar`（`_derive_directory` 剥 inbox 前缀）。
- 历史幽灵目录（enrichment/results/raw/raw-data，26.7–26.8 三套旧路径方案遗留）已于 2026-10-04 清理完毕，产生机制已根治（§4）。

### 2.2 平台区

| 目录 | 用途 | 管理方 |
| --- | --- | --- |
| `{data_root}/studio/{session_id}/` | Studio 会话工作区 | `studio_sandbox_manager` |
| `{data_root}/.sandbox-pool/` | chat 沙盒 warm pool 交付目录 bind mount 基目录（Web 与 Docker daemon 共见） | `sandbox/pool.py` |
| `{data_root}/output/agentteams/{case_id}/` | 协作室会诊 workdir + artifact_fetch 兜底 | `agent_consultation_service` / `agentteams_data_tool_service` |
| `{data_root}/subagents/{run_id}/{index}/` | 普通 fan-out 子代理 workdir | `parallel_subagent_service` |
| `{data_root}/cygnusx_data/` | welcome/参考基因组等平台内部数据 | 各自服务 |
| `{data_root}/bin/` | EBIDownload 等二进制 | 部署脚本 |
| `system/.tmp` | 上传分片暂存 | `FileService` |

### 2.3 Nginx `/tracks/` 直链（JBrowse）

`deploy/docker/nginx/nginx.conf`（及 prod 变体）的 `location ^~ /tracks/ { alias /data/omichub/; }`——alias 目标是**容器内**路径，与 compose 数据挂载目标（`${STORAGE_PATH}`）一致；换根时改 `.env` + alias 两处。安全边界：仅 RFC1918 内网可达（公网需改鉴权代理，见 conf 内注释）。URL 策略不变：`origin/tracks/{file.path}`。

## 3. 路径构造纪律

**唯一构造入口**：`StoragePathFactory`（`infrastructure/storage/path_factory.py`，含全部调用点清单 docstring）。业务代码构造数据路径必须走 `get_path_factory()`，禁止手工拼接。

**新增目录的正确姿势**：走 `create_project_run_dir(uid, project, analysis)`（projects/runs 布局，含 input/output/work/logs 四子目录 + `ensure_directory_chain` 登记）——工具/流程/Studio 产物登记均此路径。禁止在用户根直接 mkdir 新顶层目录（26.7.9 富集模块 `enrichment/{task_id}` 的教训）。

**DB 登记**：物理目录建立后须调 `ensure_directory_chain`（`file_service.py`）写 `user_directories`，否则目录树不显示。会诊/协作室路径用 `ensure_directory_chain`（agentteams_service、studio_context_service 等调用点见 path_factory docstring）。

**GC / 兜底路径**：`agentteams_evidence_gc_service` 从 `get_storage_config()` 解析数据根 + 启动自检（数据根不存在即抛错，不静默）；`agentteams_data_tool_service` 的 workdir fallback 同样走配置链，不再落旧根。

## 4. sync 对账（`POST /files/sync`，进页静默触发）

`FileService.sync_user_files` 双向对账，2026-10-04 起**双向**：

1. **正向（磁盘 → DB）**：非 skip 目录逐级 `ensure_directory_chain` 登记；文件幂等入库；active 记录物理消失则删除。skip 名单：顶层 `tasks/projects/temp/results/raw` + `workspace/{chat-uploads,sandbox}` + 隐藏目录 + **workspace 根沙盒 shell 残留模式**（`zsh.*.omp.cache`、`init.*.zsh`、`omp.cache`——chat 沙盒容器 HOME 落 workspace 根产生的缓存，不登记）。
2. **反向（DB → 磁盘，幽灵目录根治）**：`_reconcile_ghost_directories` 遍历 `user_directories`，候选物理路径（`user_root/{path}` 与 `inbox/{path}`）均不存在 → 删除记录。护栏：`is_system=1` 不删；有 active file_records 子级（含父级链）不删；叶子先行、父级由后续 sync 迭代收敛。返回 `removed_directories` 计数。

> 历史教训：sync 曾对 `user_directories` 只增不减——物理目录删了、file_records 清了，目录记录永留，目录树出现"点开为空"的幽灵节点（enrichment 21 条 / results 4 条 / raw 2 条……详见 `docs/info/26.10.3/个人空间目录治理-补充调查报告.md`）。反向 pass 不做的话幽灵目录还会再长。

## 5. 目录树展示（后端元数据驱动）

`DirectoryService.list_directories` 输出展示元数据，前端（`DirectoryTree.vue`）按元数据过滤，**不在前端写死名单**：

- `visible_in_tree=false`：不渲染（inbox 上传暂存层 D2、tasks 历史任务产物 D3——物理与 DB 保留，blast 读取兼容不受影响）；
- `aggregated=true`：子树折叠为单个只读聚合节点（D1——`workspace/chat-output` 升格为「AI 会话产物」，29 个会话 UUID 子目录不再逐个展开；会话产物仍经消息卡片 / 文件列表下载）；
- `DirectoryDTO` 新增 `visible_in_tree` / `aggregated` 字段。

## 6. 防复发门禁（三项，CI 强制）

| 门禁 | 位置 | 规则 |
| --- | --- | --- |
| `/data/` 字面量守卫 | `scripts/check_storage_paths.py`（CI backend job） | `src/cygnusx/**/*.py` 禁止 `/data/...` 字面量；白名单：`core/config.py` 与 `storage_config.py`（存储根锚点/兜底）、行级容器端点（`:/data/cygnusx`、`/data/platform`）与"容器内/兜底"注释 |
| worker 配置 fail-fast | `scripts/render_worker_config.py`（CI backend job） | `shared_data_dir` ↔ `STORAGE_PATH` 不一致拒绝渲染 |
| 路径工厂登记 | `path_factory.py` docstring | 业务目录唯一构造入口 + 调用点清单，新增调用方同步维护 |

本地验证：`uv run python scripts/check_storage_paths.py && uv run python scripts/render_worker_config.py --check`。

## 7. 会诊 workdir 挂载（Gap 3 挂载断裂修复）

**修复前**：会诊（workspace_execution）经 `parallel_subagent_service` fan-out，子代理调 `sandbox_execute` 进入 Studio 会话沙盒（`{workspace_root}/{child_session_id}`），而分配的 workdir 是宿主路径（`output/agentteams/{case}/{work_item}`）——`extra.subagent_workdir` 无任何消费方，提示词承诺的工作目录在容器内**不可见**（产物落盘从未真正兑现）。

**修复后链路**（2026-10-04）：

```
_execute_child_tool（parallel_subagent_service）
  └─ workspace 工具执行前：studio_sandbox_manager.register_workdir_mount(
         parent_session_id, workdir)     ← 防逃逸校验（须在存储根内）+ mkdir
     └─ ensure_running 容器创建：
         volumes[workdir] = {"bind": "/workspace/workdir", "mode": "rw"}
     └─ 复用校验 _container_mounts_match：workdir 挂载缺失/源不匹配 → 重建容器
```

- 容器内挂载点固定 `/workspace/workdir`；提示词 `data/ai/prompts/shared/agentteams_workspace_execution.md` 已同步：宿主侧 `output/agentteams/<case_id>/<work_item_id>/` 与容器内 `/workspace/workdir/` 两端同一批文件。
- 注册必须在首次 `ensure_running` 之前（Docker mount 创建后不可变；旧容器缺挂载由复用校验触发重建）。

**遗留（Gap 3 前缀统一，待架构裁决，不在本轮）**：会诊工作目录存在三种前缀表达（宿主 `output/agentteams/`、产物登记 `workspace/agentteams/`、file_protocol §9 的 `projects/.../runs/agentteams-case-*`）。裁决前一律不动 `output/agentteams/`、`workspace/agentteams/` 前缀。

## 8. 验证矩阵

| 改动类型 | 最小验证 |
| --- | --- |
| 存储根 / 派生默认值 | `uv run python -c "from cygnusx.core.config import get_settings; ..."` 断言派生值 + `tests/unit` 配置相关用例 |
| sync / 目录树 | `uv run pytest tests/unit/test_file_service.py -q`（29 用例：反向对账 3 + 展示元数据 1 + skip 模式 1） |
| 新增目录构造 | `scripts/check_storage_paths.py` + 确认走 `create_project_run_dir` |
| worker 配置 | `render_worker_config.py --check` 正例/负例 |
| 会诊挂载 | 触发一次会诊子代理执行，容器内 `ls /workspace/workdir` 可见宿主 workdir 内容 |
| nginx /tracks/ | 改 alias 后 `curl -o /dev/null -w "%{http_code}" .../tracks/{已知文件}` 应 200 |

## 9. 已知遗留与决策点

| 项 | 状态 | 说明 |
| --- | --- | --- |
| Gap 3 前缀统一（方案 A/B/C） | 待架构裁决 | 会诊产物是否进用户文件树、`output/agentteams` vs `workspace/agentteams` vs protocol path 三前缀收敛 |
| Phase 4 `DIRECTORY_SCHEME` 注册表 | 延后 | 目标架构：路径模板/归属/`visible_in_user_tree`/sync 范围/GC 策略的代码单一事实源；sync skip 与可见性过滤改查注册表；file_protocol v1.4 增补 L2 chat-output 章 |
| `inbox/raw-data/` 实体文件 | 人工决策保留 | `integration_harmony.qs`（212MB）留在原处，DB 记录未迁移（原计划归位 raw_data/ 被人工叫停） |
| workspace 根 4 个沙盒残留文件 | 物理保留 | DB file_records 已清 + skip 模式挡住再登记；物理删除被人工叫停，建议后续在沙盒容器把 `/workspace` HOME 残留改 tmpfs 或清理脚本 |
| 旧根 `/data/cygnux` 归档 | 运维事项 | 9-20 后零运行时写入，可归档；不在本方案动 |
| `mas_workspace_root` 派生 | 已生效但 deprecated | 历史 MAS 编排域（mas_enabled=False），7 实例化点全部显式传 root |

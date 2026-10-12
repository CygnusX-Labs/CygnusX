# CygnusX 存储系统与四级入口工作目录 Gap 审计

> **状态**：审计快照（2026-10-03 实勘）；Gap 1/2/挂载断裂已于 2026-10-04 修复，终态以 `CygnusX_storage_architecture.md` 为准；Gap 3 前缀统一待架构裁决
> **类型**：调查报告（时点性文档，只增不改）；整改实施见 `docs/info/26.10.3/存储层优化实施方案.md` 及 Phase 0–3 提交（7788dc34 / 2e0e2b87 / 后续）
> **审计范围**：平台底层存储系统设置、L1/L2/L3/L4 四级入口工作目录的理论规范覆盖、沙箱挂载与 Agent 告知信息的一致性
> **调查方法**：文档精读（`Protocol/file_protocol.md` v1.3、`CygnusX_sandbox_architecture.md` v1.2 等）+ 代码实勘（`src/cygnusx/`、`deploy/`、`integrations/agentteams/`）+ live 容器实机核对（`cygnusx-web`、`cygnusx-worker`、`cygnusx-agentteams-bridge`、`agentteams-worker-*` 的环境变量与 Mounts）

---

## 1. 底层存储系统实际形态

**双根并存的本地文件系统**（对象存储仅用于协作室证据归档）：

| 配置源 | 值 | 出处 |
| --- | --- | --- |
| `data/CygnusX.yaml` `storage.data_root`（优先级最高） | `/data/omichub` | `data/CygnusX.yaml:30` |
| `.env` `STORAGE_PATH` / `CYGNUSX_DATA_ROOT` | `/data/omichub` | `.env:54`、`.env:67` |
| `core/config.py` 默认值 | `/data/cygnusx` | `src/cygnusx/core/config.py:131` |
| `data/worker_config.yaml` `shared_data_dir` | `/data/cygnusx`（与 .env 不一致，见 Gap 2） | `data/worker_config.yaml:7` |
| 硬编码（绕过 Settings，见 Gap 1） | `/data/cygnusx` | 多处 |

配置解析链：`get_storage_config()` 以 `data/CygnusX.yaml` 的 `storage` 段优先，缺失时回退 `settings.storage_path`，再回退内置默认 `/data/cygnusx`（`src/cygnusx/infrastructure/config/storage_config.py`）。

MinIO 仅承担协作室证据 / turns 归档（`MINIO_AGENTTEAMS_BUCKET=agentteams-evidence`），用户文件全走本地卷。

**live 实机核对（2026-10-03）**：

- `cygnusx-web`、`cygnusx-worker` 容器内 `STORAGE_PATH=/data/omichub`；
- 宿主 `/data/omichub` 为活跃数据根（`users/`、`studio/`、`.sandbox-pool/` 均在此）；
- 宿主 `/data/cygnusx` 为旧根残留（仅有 `bin/`、`cygnusx_data/`、`logs/`、旧 `users/user-1` 等）。

## 2. 四级入口目录规范覆盖现状

| 入口 | 规范来源 | 代码落地 | 评价 |
| --- | --- | --- | --- |
| L1 工具箱 / Flow | `Protocol/file_protocol.md` §2–§5 | `TaskService._make_work_dir` → `create_project_run_dir(user, project, flow_id)`（`task_service.py:325`）；DEG / BLAST / 富集 / GSEA / 系统发育树均已接入 | 规范与实现齐全 |
| L2 星尘 AI 助手 | file_protocol §2 仅将 `workspace/` 定义为「内部目录，不作为分析结果入口」，未定义 chat 产物协议 | 附件落 `users/{uid}/workspace/chat-uploads/`；产物落 `users/{uid}/workspace/chat-output/{session}/output`（`chat_sandbox_tools.py:231`），注册 file_records 但不走 `create_project_run_dir`、不登记目录树 | 规范缺口：文件协议 v1.3 完全没提 chat-output，实际是代码既成事实 |
| L3 AI 工作台 OmicStudio | file_protocol §5 仅一行「Studio 报告交付已接入」（指报告交付那一步） | 工作区落 `{storage_path}/studio/{session_id}`（`data/ai/studio.yaml` `mounts.workspace` + `studio_loader.py:271`）；会话内部目录协议在提示词（`shared/sandbox_protocol.md`「沙盒目录使用规范」）而非文件协议 | 规范分散：Studio 会话工作区的 input / ref / output / scripts / mcp-builds 布局只存在于提示词与 `manager.py:176` 注释，file_protocol 无此契约 |
| L4 协作室 | file_protocol §9–§12（v1.3 融合）最完备：Case→Project Run 绑定、四层目录、protocol path、交付投影 | `agentteams_service.py:545` 建目录、`:549` 登记目录链、`:1100` 交付投影，与协议一致 | 但另有一条平行的旧路径体系，见 Gap 3 |

**第一问结论**：理论规范不是「没有」，而是「不完整」。L1 / L4 有强协议；L2 / L3 的会话级工作目录属于「提示词约定 + 代码既成事实」，未纳入 `Protocol/file_protocol.md` 统一管治。

## 3. 发现的 Gap（按严重度排序）

### Gap 1（高）：`/data/cygnusx` 硬编码绕过 Settings，换根后即错位

| 位置 | 问题 |
| --- | --- |
| `src/cygnusx/application/services/agentteams_evidence_gc_service.py:47` | `Path("/data/cygnusx/output/agentteams")`——GC 服务在 `/data/omichub` 环境下扫不到任何 Case 目录，清理静默失效 |
| `src/cygnusx/application/services/agentteams_data_tool_service.py:259` | fallback `f"/data/cygnusx/output/agentteams/{case_id}/downloads"`——workdir 缺失时产物下载到错误根 |
| `src/cygnusx/domain/mas/workspace.py:31` | `WorkspaceLayout(root="/data/cygnusx")` 默认参数（MAS runs 目录） |
| `src/cygnusx/core/config.py:474` | `sandbox_pool_host_dir` 默认 `/data/cygnusx/.sandbox-pool`（.env 已覆盖，但默认值与 YAML 根不一致） |
| `src/cygnusx/core/config.py:162` | `mas_workspace_root` 默认 `/data/cygnusx` |

实机证据：活跃根是 `/data/omichub`，以上五处在换根部署下全部指向旧根。

### Gap 2（高）：`worker_config.yaml` 与 `.env` 数据根不一致

`data/worker_config.yaml:7` 写 `/data/cygnusx`，而 `.env:72` `WORKER_SHARED_DATA_DIR=/data/omichub`。`scripts/worker-compose.sh` 经 `render_worker_config.py` 把 YAML 渲染进 env 文件；`.env` 直接 `docker compose` 时二者冲突。当前 live 栈 worker 挂载正确（`/data/omichub`），说明是 `.env` 兜住了 YAML 的错值；单独经 `worker-compose.sh` 路径启动会把 worker 挂到旧根。

### Gap 3（高）：L4 存在两套互相矛盾的「工作目录」约定

- **提示词告知**（`data/ai/prompts/shared/agentteams_workspace_execution.md:12`）：「工作目录固定为 `output/agentteams/<case_id>/<work_item_id>/`」——未说明相对什么根，且与 file_protocol §9 的 `projects/<slug>/runs/agentteams-case-...` 是两个体系。
- **代码实现**：
  - `agent_consultation_service.py:374-378` 建的 workdir 是 `{storage_path}/output/agentteams/{case_id}/{work_item_id}`（平台全局，无用户段）；
  - DB 登记时 `directory=f"workspace/agentteams/{case_id}/{work_item_id}"`（`:886`，又一个前缀）；
  - bridge `_workspace_artifact_refs` 只认 `workspace/agentteams/{case_id}/{work_item_id}` 形状的路径（`integrations/agentteams/bridge/cygnusx_agentteams_bridge/service.py:1573`）。
- 三种前缀（`output/agentteams/`、`workspace/agentteams/`、DB directory 字段）指向同一批文件的不同表达；file_protocol §9 的 protocol path（`projects/.../runs/...`）只在 Case 交付投影时使用。
- **挂载断裂**：会诊 workspace_execution 走 `parallel_subagent_service`，子代理调 `sandbox_execute` 时进入的是 Studio 会话沙盒（session_id 维度），而 `workdir_root` 是宿主路径；`_run_child` 只把 workdir 放进 `extra.subagent_workdir`，无任何消费方将它挂载进容器——提示词承诺的工作目录与沙盒实际可见的文件面没有绑定。
- **实机证据**：`/data/omichub/output/agentteams/` 下只有 `downloads/`（artifact_fetch 兜底路径产物），没有 `<work_item_id>/` 目录——提示词承诺的「工作目录固定为 output/agentteams/...」在 live 上大概率从未真正兑现。

### Gap 4（中）：L2 chat 产物目录游离于文件协议之外

`workspace/chat-output/{session}/output` 不在 file_protocol §2 的目录图内（§2 只把 workspace 标为「内部目录不作为分析结果入口」），不走 `ensure_directory_chain`（只注册 file_records），用户在「我的文件」目录树看不到它，只能从消息卡片下载。协议自身声称「所有会产生用户可下载产物的新模块」必须走项目运行目录——chat 沙盒产物是明显例外且未记录豁免理由。

### Gap 5（中）：Studio 只读挂载的多租户红线未被提示词告知

`/data/platform` 只读挂载（宿主源 `users/{uid}`，`manager.py:479-485`）是 P1「数据不搬家」核心机制，但：

- 提示词（`data/ai/prompts/studio/system.md:13`）只说「用 `datahub_import` 或 `platform_result_import` 引入」，未告知 Agent 容器内存在 `/data/platform` 这个只读数据面，也没有说明 input/ 软链经它解析；
- `/data/platform` 字符串在全部提示词中 0 命中；
- 路径防护规则靠 `infrastructure/studio/paths.py` 代码强制，Agent 只能靠试错发现能读什么。

### Gap 6（中）：协作室独立 Worker 容器零存储挂载

`agentteams-worker-*`（professional-pool ×2、analysis、quality、delivery）全部容器 `Mounts: []`（live 实测），只读 rootfs + tmpfs，产物一律走 Bridge API → MinIO（s3_uri）或 `local_path`（相对路径，由 web 侧解析）。

这与 file_protocol §9.2「受控 Worker 写入 input/work/logs」的描述存在偏差：真正的 Worker 容器不直接写文件系统，直接写盘的是 web 进程内的会诊子循环（parallel_subagent）。§9 的「四层目录职责」表在 live 上只有 input（快照）和 output（投影）被用到，work/logs 由会诊 workdir 体系（Gap 3）承担。

`deploy/agentteams/docker-compose.agentteams.yml` 中 worker 服务确实无任何数据卷声明（仅 bridge/state/gateway 有 named volume，见 `:11-12`、`:53-54`、`:74-75`）。

### Gap 7（低）：文档与实现的口径漂移

| 项 | 漂移内容 |
| --- | --- |
| 挂载降级未记录 | `CygnusX_sandbox_architecture.md:96` 图中写 `/data/platform ro` 挂载；代码在用户目录不存在时静默跳过（`manager.py:489-491` 仅 WARNING），文档未记录该降级行为 |
| 存储根多源不同步 | `.env.example:140` / `config.py:474` 默认 `/data/cygnusx`，与 `CygnusX.yaml` 根 `/data/omichub` 不同步；image-mapping 的六步同步纪律没有覆盖 storage 根这个「同类多源」配置 |
| workspace 目录语义漂移 | `file_protocol.md:46` 目录图中 `workspace/` 注释为「不作为分析结果入口」，但 chat 产物（Gap 4）和协作室 DB directory（Gap 3）都实际落在 workspace 下 |

## 4. 修复建议（按优先级）

| 优先级 | 建议 | 对应 Gap |
| --- | --- | --- |
| P0 | `/data/cygnusx` 硬编码全部改为 `get_settings().storage_path` 或路径工厂；`worker_config.yaml` 与 `.env` 对齐为 `/data/omichub` | Gap 1、2 |
| P1 | 协作室会诊工作目录统一挂到 file_protocol §9 的 Case run 目录下（`projects/.../runs/agentteams-case-.../work/{work_item_id}`），废弃 `output/agentteams` 与 `workspace/agentteams` 双前缀；提示词、bridge refs、DB directory、GC 路径四处同步修改。此项需要一次架构裁决 | Gap 3 |
| P1 | file_protocol v1.4 增补 L2（chat-output 协议或明确豁免理由）与 L3（Studio 会话工作区布局）两章，把提示词里的目录契约上升为平台协议 | Gap 4、5 |
| P2 | `sandbox_protocol.md` 增加 `/data/platform` 只读挂载的告知；`/data/platform` 不存在时的降级行为补进 `CygnusX_sandbox_architecture.md` | Gap 5、7 |

## 5. 审计证据索引

| 主题 | 关键位置 |
| --- | --- |
| 路径工厂 | `src/cygnusx/infrastructure/storage/path_factory.py`（`create_project_run_dir` 强制创建 input/output/work/logs 四层，`project_slug()` 规范化目录名） |
| 存储配置解析 | `src/cygnusx/infrastructure/config/storage_config.py`（YAML → settings → 内置默认三级降级） |
| chat 产物收集 | `src/cygnusx/application/services/chat_sandbox_tools.py:203-250`（`_collect_artifacts`，归置 `workspace/chat-output/{session}/output`） |
| chat 沙盒挂载 | `src/cygnusx/infrastructure/sandbox/pool.py:285-310`（`/tmp/chat_output`、`/workspace/output`、`/workspace/input` 三个 per-container bind mount，源在 `SANDBOX_POOL_HOST_DIR`） |
| Studio 容器创建 | `src/cygnusx/infrastructure/studio/manager.py:425-500`（workspace rw + `users/{uid}` ro→`/data/platform`） |
| Studio 路径防护 | `src/cygnusx/infrastructure/studio/paths.py`（`resolve_workspace_read_path` 软链解析 + 词法/realpath 双校验） |
| 协作室 Case run | `src/cygnusx/application/services/agentteams_service.py:530-560`（`_prepare_case_run`）、`:1085-1115`（交付投影） |
| 会诊 workdir | `src/cygnusx/application/services/agent_consultation_service.py:374-378`（构造）、`:491-497`（产物登记）、`:886`（DB directory） |
| 子代理 fan-out | `src/cygnusx/application/services/parallel_subagent_service.py:290-314`（workdir 构造）、`:1348-1390`（`_execute_child_tool`，`extra.subagent_workdir` 无消费方） |
| MAS workspace | `src/cygnusx/domain/mas/workspace.py`（八目录契约，root 默认硬编码） |
| 提示词告知 | `data/ai/prompts/shared/sandbox_protocol.md`（沙盒目录使用规范）、`shared/agentteams_workspace_execution.md`（协作室工作目录）、`studio/system.md`（datahub_import） |
| compose 挂载 | `deploy/docker/docker-compose.yml:85`（web 数据卷）、`docker-compose.worker.yml:54-56`（worker 数据卷）、`deploy/agentteams/docker-compose.agentteams.yml:150-235`（协作室 worker 无数据卷） |
| live 容器核对 | `cygnusx-web`：`STORAGE_PATH=/data/omichub`、`SANDBOX_POOL_HOST_DIR=/data/omichub/.sandbox-pool`、`/data/omichub -> /data/omichub (rw)`；`cygnusx-worker`：`STORAGE_PATH=/data/omichub`；`agentteams-worker-*`：`Mounts: []` |

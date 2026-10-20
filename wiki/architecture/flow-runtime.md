# Flow 运行时

Flow 是 CygnusX 的标准计算资产：仓库根 `flows/*.yaml` 以声明方式描述表单、参数、样本表、执行映射和资源；Worker 在受控镜像中运行 Snakemake 流程。**Flow YAML 只描述契约，不在 Web 进程执行计算，也不写入数据库注册表。**

> **当前状态**：YAML 接入、热重载、AI 工具编译、确认门和 `TaskService.submit()` 九步链已实现；流程代码、Worker 镜像与真实运行仍按各自验收矩阵管理。源码执行门禁未开启时，真实运行 BLOCKED。

## 从声明到执行

```text
flows/*.yaml
  │
  ├─ FileSystemFlowRepository（磁盘扫描 + mtime 热重载）
  │     ├─ 前端表单（Vue）
  │     └─ FlowToolSchemaCompiler → 固定 Flow 工具 / 旧 per-flow 工具
  │
  ├─ 表单通道：POST /api/v1/tasks
  └─ AI 通道
       ├─ 外部 MCP：list_flows → get_flow_detail → prepare → 人类确认 → submit
       └─ 内置 Chat：platform_list_flows → prepare → 人类确认 → submit
                    │
                    ▼
             TaskService.submit() 九步
                    │
             GenericFlowBuilder
             生成 analysis.yaml / samples.csv / contrasts.csv
                    │
             Task + 运行目录 + 事件 + 幂等快照
                    │
             Celery run_snakemake
                    │
             LocalSnakemakeExecutor → /opt/cygnusx/pipelines/<X>Flow
                    │
             日志 / 状态 / Workflow Monitor / 结果与证据
```

**关键约束**：表单提交和 AI 确认后提交在 `TaskService.submit()` 汇合，任务记录、目录隔离、样本表、监控、计费、失败处理和队列调度完全一致。分析中心不走 ToolBridge 的 `backend_async` 分支（那条路径只适合系统发育树等独立工具作业）。

## FlowConfig 六段 schema

权威定义在 `src/cygnusx/domain/flow/entities.py` 与 `domain/flow/value_objects.py`，全部 `extra="forbid"`：写错键名会直接加载失败，不会静默忽略。

| 段 | 内容 |
| --- | --- |
| `meta` | `id`（小写+下划线）、名称、分类、语义化版本、描述、标签/图标/色板 |
| `ai` | 是否启用 AI 接入、`tool_slug`、`allowed_parameters`、样本/比较上限、`requires_confirmation`、校验插件 |
| `groups` | 前端表单分区（缺省为 basic/modules/advanced） |
| `parameters` | 递归参数定义（input/select/boolean/path/group/section），支持条件显隐 |
| `sample_sheet` | 列定义、唯一性、枚举、校验规则、导入方式和分组列联动 |
| `execution` | 引擎（snakemake/nextflow）、容器内 snakefile 路径、主配置名、资源、CSV 格式、额外参数 |
| `pipeline_mapping` | 参数到流程配置/CSV 的映射，见下文 |

`execution.snakefile` 是 **Worker 容器内路径**，由 `data/worker_config.yaml` 的 `WORKER_PIPELINE_DIR` 映射到宿主机流程目录；Web 容器以只读方式挂载 `flows/`。

## 注册与热重载

- 目录来源：`Settings.flow_yaml_dir`，默认 `flows`。
- **无 DB 注册表**：流程定义只在磁盘；`tasks` 表只存运行实例。
- `FileSystemFlowRepository` 在每次读取前比对目录最大 mtime，变化即清缓存重扫；单个文件加载失败只记录错误并跳过。
- 手动重载：`POST /api/v1/flows/reload`。
- 热重载只覆盖 Web 进程内 FlowConfig 缓存；改 Snakefile/流程代码需按 Worker 镜像约定重建并重启 Worker。

## AI 接入与确认门

- `ai.enabled: true` 的 Flow 由 `FlowToolSchemaCompiler` 编译为工具契约。工具固定化后，外部 MCP 通道固定链为 `cygnusx_list_flows` → `cygnusx_get_flow_detail` → `cygnusx_prepare` → `cygnusx_submit`；内置 Chat 的目录工具是 `platform_list_flows`（仅 id/name/category/version），没有 detail 工具，固定链为 `cygnusx_prepare` → `cygnusx_submit`。新增 Flow **零新增 MCP 工具**。
- `prepare` 执行 `FlowSubmissionValidator`：参数白名单、`max_samples`/`max_comparisons`、样本表列约束、可选的 `fastq_workspace` 校验插件。
- 通过后创建 PENDING 确认记录；人类 JWT 在前端确认卡批准；`confirm_and_submit` 一次性消费凭证并进入 `TaskService.submit()`。
- 契约漂移防线：确认时冻结 Flow 版本；提交时版本不符返回 `FLOW_CONTRACT_CHANGED`，要求重新 prepare。

## TaskService.submit() 九步

| 步骤 | 动作 |
| --- | --- |
| 1 | 校验 counts/Dataset 写门禁、批准绑定与输入 |
| 2 | 按 owner 查幂等键，已存在则不重复提交 |
| 3 | 运行权威 Validator，取得规范化请求与 Flow 定义 |
| 4 | 预生成 task UUID，创建用户隔离运行目录并登记目录链 |
| 5 | 锁定参数，`GenericFlowBuilder.build_project_files()` 生成输入文件 |
| 6 | 写 Dataset 身份与 monitor 配置，冻结定义、Task 绑定和文件摘要 |
| 7 | 创建标准 Task，保存参数证据与工作目录 |
| 8 | 启用时执行原计费预扣，保存内部参数，推进 QUEUED 并提交事务 |
| 9 | 投递 Celery `run_snakemake`；未知投递必须对账，不能自动重放 |

QUEUED 表示“投递意图”，不等于 broker 已 ACK；执行 Worker 持 Task 行锁领取，已运行/终态重复投递不会启动执行器。

## GenericFlowBuilder 映射

输入 FlowConfig + 前端参数 + 样本行 + 比较组 + work_dir；输出：

- `analysis.yaml`（名称取 `execution.config_file_name`）
- `samples.csv`
- `contrasts.csv`

| 映射段 | 语义 |
| --- | --- |
| `config_fields` | 写入主配置的字段，支持点号嵌套；取最后一段匹配前端参数 |
| `computed_fields` | 注入 `__work_dir__` / `__samples_csv__` / `__contrasts_csv__` |
| `list_fields` | 强制归一为字符串列表（如多 lane） |
| `defaults` | 前端未提供时的默认值 |
| `sample_sheet` / `comparisons` | 输出文件名与列映射 |

空字符串视为未提供；`data_deliver` 缺省为 `work_dir.parent / "data_deliver"`。

## 与 FlowFrame 的接缝

`pipeline_mapping` 的键必须与流程 analysisyaml 的键**逐字一致**，样本/比较组 CSV 列名必须与流程 `load_samples`/`load_contrasts` 的必需列一致。**这条约束目前没有 CI 交叉校验**，靠 YAML 注释和真实 dry-run 守护；改流程键名必须同 PR 改 `flows/*.yaml`。这是本域最脆弱的接缝。

## 非 YAML-only 通道

以下通道接入新 Flow 仍需改代码，不属于 YAML 声明式承诺：

| 通道 | 硬编码点 |
| --- | --- |
| REST `/api/v1/pipelines/*` | `PipelineType` Literal + 手写适配器 |
| 外部 MCP `cygnusx-pipelines` preset | 手写 RNA/ATAC 四件套（已软弃用） |
| 前端任务展示 | `PipelineType` union、flowLabel 映射 |
| AgentTeams/MAS | `data/ai/flows/` 第二注册表（ID 命名不同） |

## 新增 Flow 清单

1. 按 `Protocol/FlowFrame/flow-framework` v2.0 编写流程，放入 `pipelines/` 子模块。
2. 确认 Worker 挂载：`WORKER_PIPELINE_DIR` 覆盖新目录，容器内 snakefile 路径可达。
3. 新增 `flows/<flow_id>.yaml`，参数键与流程 analysisyaml 对齐；配置 `ai` 段与可选校验插件；需要灰度时增加 `<flow>_flow_enabled` 开关。
4. 验证：加载无误 → `GET /api/v1/flows` 出现 → 表单渲染 + dry-run → 固定工具闭环（目录/契约/非法输入拒绝/确认/幂等提交）→ 工具数量不变。
5. Agent 人设与协作室通道另走 `data/ai/` 体系。

**红线**：禁止为新 Flow 新增 MCP 工具或复活 per-flow 自动生成工具；提交必须经 `prepare → 人类确认 → submit` 凭证链。

## 代码锚点

| 组件 | 位置 |
| --- | --- |
| FlowConfig | `src/cygnusx/domain/flow/entities.py`、`value_objects.py` |
| 注册/热重载 | `src/cygnusx/infrastructure/database/repositories/flow_repository.py` |
| 工具编译 | `src/cygnusx/tools/flow_schema_compiler.py`、`tool_configs/tools_schema.yaml` |
| 确认/提交 | `analysis_flow_tool_service.py`、`tool_confirmation_service.py` |
| 九步链 | `src/cygnusx/application/services/task_service.py` |
| 构建器 | `src/cygnusx/infrastructure/execution/generic_builder.py` |
| 执行 | `infrastructure/celery_app/tasks/analysis.py`、`infrastructure/execution/local.py` |

## 关联文档

- 权威基线：[`CygnusX_flow_architecture.md`](../../ARCHITECTURE_DESIGN/CygnusX_flow_architecture.md)、[`CygnusX_mcp_architecture.md`](../../ARCHITECTURE_DESIGN/CygnusX_mcp_architecture.md) §11
- 规范：[`Protocol/FlowFrame/`](../../Protocol/FlowFrame/) v2.0
- [MCP 体系](mcp) · [数据库基础设施](database) · [分析流程扩展](../development/flow-extension) · [分析流程与工作流](../features/workflows)

# 分析流程与工作流

CygnusX 使用 YAML 声明式 Flow + 通用构建器接入 Snakemake 流程。流程 YAML 定义用户可见的参数与输入输出契约，Worker 和运行时镜像执行实际计算；新增 Flow 不再新增 MCP 工具。

> **当前状态**：Flow 加载、热重载、表单/AI 双通道、确认门、九步提交链与 Worker 执行已实现。真实运行受流程代码、镜像、Worker 挂载和源码执行门禁共同约束；QUEUED 不代表已执行。

## 已有流程

| 流程 | 文件 | 说明 |
| --- | --- | --- |
| RNA-seq | `flows/rna_seq.yaml`（v2.3.0） | FASTQ → QC/比对/定量/差异 |
| ATAC-seq | `flows/atac_seq.yaml` | ATAC QC/peak/差异可及性 |
| counts DEG | `pipelines/CountsDEGFlow` | raw counts → DESeq2；默认不注册为可用能力 |

流程代码在 `pipelines/` 子模块，遵循 FlowFrame v2.0；仓库只记录子模块指针。

## 流程如何加载

1. `FileSystemFlowRepository` 扫描 `flows/*.yaml`，严格校验六段 schema；
2. 以 `meta.id` 识别流程，mtime 变化自动热重载；
3. 前端按 `groups`/`parameters`/`sample_sheet` 渲染表单；
4. AI 通道按 `ai.enabled` 暴露固定 Flow 工具；
5. 提交后 `TaskService.submit()` 生成运行文件并投递 Worker。

手动重载：`POST /api/v1/flows/reload`。热重载只覆盖 Web 进程；改 Snakefile 需按 Worker 镜像约定重建并重启。

## 两条提交通道

```text
表单：分析中心 → POST /api/v1/tasks
外部 MCP：cygnusx_list_flows → cygnusx_get_flow_detail → cygnusx_prepare
          → 人类确认 → cygnusx_submit
内置 Chat：platform_list_flows → cygnusx_prepare → 人类确认 → cygnusx_submit
                    │
                    ▼
            TaskService.submit() 九步
                    │
            GenericFlowBuilder 生成
            analysis.yaml / samples.csv / contrasts.csv
                    │
            Celery run_snakemake → Worker → Snakemake
```

两条通道在同一个提交入口汇合，任务记录、目录隔离、样本表、监控、计费和失败处理一致。

两条 AI 链路的目录工具不同：`cygnusx_list_flows` / `cygnusx_get_flow_detail` 仅存在于外部
`mcp-server/tools/flows.py`；内置 Chat 的目录工具是 `platform_list_flows`（仅返回
id/name/category/version），**没有内置 detail 工具**，固定链路只有 `cygnusx_prepare` /
`cygnusx_submit`。默认 `LEGACY_PIPELINE_TOOLS=true` 时，内置端还会为每个 `ai.enabled` Flow
注册 `cygnusx_prepare_<slug>_submission` 动态工具；设为 `false` 停止注册。

## 参数与映射

`pipeline_mapping` 把前端参数映射为流程主配置和 CSV：

```yaml
pipeline_mapping:
  config_fields:
    - project_name
    - Genome_Version
    - raw_data_path
    - peak_calling.macs2_qvalue
  computed_fields:
    workflow: "__work_dir__"
    sample_csv: "__samples_csv__"
    contrast_csv: "__contrasts_csv__"
  sample_sheet:
    output_name: "samples.csv"
    columns:
      sample: sample
      group: group
```

键名必须与流程 analysisyaml **逐字一致**；样本/比较组列名必须与流程 `load_samples`/`load_contrasts` 的必需列一致。目前无 CI 交叉校验，改流程键名必须同 PR 改 YAML 并跑真实 dry-run。

## 确认门与幂等

- `prepare` 校验参数白名单、样本/比较上限、样本表列约束和可选 FASTQ 插件；
- 冻结 Flow 版本与参数摘要；
- 人类在确认卡批准后，`submit` 一次性消费凭证；
- 同一 `confirmation_id` 重试返回既有 `task_id`，不重复建任务；
- 版本漂移返回 `FLOW_CONTRACT_CHANGED`，要求重新 prepare；
- 模型不能自证确认。

## 新增流程

1. 按 FlowFrame v2.0 编写流程并放入 `pipelines/`；
2. 确认 Worker 挂载与容器内 snakefile 路径；
3. 新增 `flows/<flow_id>.yaml`（六段 schema），参数键对齐；
4. 配置 `ai` 段（白名单、确认、可选校验插件）与灰度开关；
5. 验证：加载 → 表单 dry-run → 固定工具闭环 → 工具数量不变。

**红线**：禁止为新 Flow 新增 MCP 工具或复活 per-flow 工具；提交必须经 `prepare → 人类确认 → submit`。

详细步骤见[分析流程扩展](../development/flow-extension)与[Flow 运行时](../architecture/flow-runtime)。

## 运行与排障

| 状态 | 含义 |
| --- | --- |
| QUEUED | 投递意图，不等于 broker ACK |
| RUNNING | Worker 已领取并推进 |
| COMPLETED | 执行器报告成功；仍需检查产物与 QC |
| FAILED | 执行失败，查看任务日志与 Snakemake 日志 |
| 需对账 | 投递/执行状态未知，不能自动重放 |

常见检查：

1. `GET /api/v1/flows` 是否有流程；
2. Worker 容器内 snakefile 路径是否存在；
3. `data/worker_config.yaml` 的 `WORKER_PIPELINE_DIR` 与挂载；
4. 任务日志 / `logs/snakemake/`；
5. 源码执行门禁是否仍关闭。

## 当前边界

- 分析中心的 YAML-only 承诺只覆盖表单与 AI 聊天通道；REST `/api/v1/pipelines/*`、外部 MCP pipelines preset、前端 union、`data/ai/flows/` 仍需改代码。
- counts DEG 默认不注册为可用能力；
- 真实运行仍受执行证据与 Worker 验收约束，不能把“能排队”当成“能出科学结果”。

## 关联文档

- [Flow 运行时](../architecture/flow-runtime) · [RNA-seq](rna-seq) · [ATAC-seq](atac-seq)
- [流程监控](workflow-monitor) · [分析流程扩展](../development/flow-extension)
- 权威基线：[`CygnusX_flow_architecture.md`](../../ARCHITECTURE_DESIGN/CygnusX_flow_architecture.md)

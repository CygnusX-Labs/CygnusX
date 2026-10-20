# 分析流程扩展

CygnusX 采用 **YAML 声明式 + 通用构建器** 接入不同的 Snakemake 分析流程。新增流程通常只需在
`flows/` 下添加 YAML 并放置流程代码；AI 通道自 2026-10-16 起使用固定 MCP 工具，新增 Flow
**不再新增工具**。

## 流程加载

1. `FileSystemFlowRepository` 扫描 `flows/*.yaml`，按目录最大 mtime 判定是否重载。
2. `FlowConfig` 及其子模型以严格模式校验（`extra="forbid"`）：键名写错会直接加载失败，不会静默忽略。
3. 校验参数唯一性、条件显隐引用和样本表规则，以 `meta.id` 为唯一键缓存。
4. 修改后可通过管理员接口 `POST /api/v1/flows/reload` 热重载；单个文件失败只跳过该文件。
5. 热重载只覆盖 Web 进程缓存；修改 Snakefile 或流程代码后需按 Worker 镜像约定重启 Worker。

## 六段 schema

```yaml
meta:            # id(^[a-z][a-z0-9_]*$)、name、category、version、description、tags/icon/color
ai:              # enabled、tool_slug、assistant_summary、allowed_parameters、
                 # requires_confirmation、validation_plugins
groups:          # 前端表单分区；缺省渲染 basic/modules/advanced
parameters:      # input/select/boolean/path/group/section，支持 condition 条件显隐
sample_sheet:    # 列定义、唯一性、枚举、validation_rules、导入方式
execution:       # engine(snakemake|nextflow)、snakefile(容器内路径)、
                 # config_file_name、default_resources、extra_args
pipeline_mapping: # config_fields / computed_fields / list_fields / defaults /
                 # sample_sheet / comparisons
```

要点：

- `execution.snakefile` 是 Worker 容器内路径（如 `/opt/cygnusx/pipelines/ATACFlow/snakefile`），
  依赖 compose 中的只读挂载；宿主机位置由 `data/worker_config.yaml` 管理。
- `parameters` 中 `condition` 引用的字段必须存在；group/section 内参数名递归查重。
- `ai.enabled=true` 的流程才会进入 AI 工具目录；`allowed_parameters` 是 AI 可填参数白名单，
  人类表单不受该白名单限制。

## pipeline_mapping

`GenericFlowBuilder` 输入 FlowConfig + 前端参数 + 样本行 + 比较组 + 工作目录，输出主配置文件、
`samples.csv` 和可选的 `contrasts.csv`。

```yaml
pipeline_mapping:
  config_fields:           # 直接写入主配置；点号路径生成嵌套字典
    - project_name
    - Genome_Version
    - raw_data_path
    - peak_calling.macs2_qvalue
  computed_fields:         # 构建器注入
    workflow: "__work_dir__"
    sample_csv: "__samples_csv__"
    paired_csv: "__contrasts_csv__"
  list_fields:             # 强制归一为字符串列表
    - raw_data_path
  sample_sheet:
    output_name: "samples.csv"
    columns:
      sample: sample
      sample_name: sample_name
      group: group
  comparisons:
    output_name: "contrasts.csv"
    columns:
      Control: Control
      Treat: Treat
```

- `config_fields` 的键名必须与流程仓库 `analysisyaml` 的键**逐字一致**；样本表/比较组列名必须
  与流程 `load_samples`/`load_contrasts` 的 `required_columns` 一致。
- 该一致性目前**没有 CI 校验**，是本域最脆弱的接缝。改流程侧键名时必须同 PR 修改
  `flows/*.yaml` 并跑真实 dry-run。
- `data_deliver` 为空时默认使用工作目录同级 `data_deliver`。

## AI 提交：固定工具链

外部 MCP 通道（`mcp-server/`）：

```text
cygnusx_list_flows → cygnusx_get_flow_detail → cygnusx_prepare
  → 返回 confirmation_id + 参数预览 → 人类在网页确认 → cygnusx_submit
```

内置 Chat 通道（`tool_configs/tools_schema.yaml`）：

```text
platform_list_flows（仅 id/name/category/version）→ cygnusx_prepare
  → 返回 confirmation_id + 参数预览 → 人类在网页确认 → cygnusx_submit
```

- `cygnusx_list_flows` / `cygnusx_get_flow_detail` 仅实现于外部 `mcp-server/tools/flows.py`；
  内置 Chat 无 detail 工具。需要内置 describe 能力须另行实现，当前未提供。
- 确认记录一次性、绑定参数 SHA-256，默认 30 分钟有效；模型不能自证确认。
- `submit` 消费确认后进入 `TaskService.submit()`，与表单通道完全同一条任务链。
- 旧 per-flow 自动生成工具已废弃并进入下线路径（默认 `LEGACY_PIPELINE_TOOLS=true` 时仍注册
  `cygnusx_prepare_<slug>_submission`，设为 `false` 停止注册）；**红线：禁止为新 Flow 新增
  MCP 工具或复活 per-flow 工具**。
- 可选校验插件：`ai.validation_plugins: [<插件名>]`，注册表在
  `src/cygnusx/domain/flow/validation_plugins.py`，内置 `fastq_workspace`。插件是代码扩展点，
  不增加 MCP 工具。
- 可选灰度：仿 `counts_deg` 增加 `<flow>_flow_enabled: bool = False`，并保证 list/detail/prepare
  三处判定同源。

`TaskService.submit()` 九步的完整说明见[流程运行时](../architecture/flow-runtime)。

## 新增流程步骤

1. 按 `Protocol/FlowFrame/flow-framework` v2.0 编写流程仓库，放入 `pipelines/`（子模块）。
2. 确认 Worker 挂载：`data/worker_config.yaml` 的 `WORKER_PIPELINE_DIR` 覆盖新流程目录，
   容器内 `/opt/cygnusx/pipelines/<X>Flow/snakefile` 可达。
3. 新增 `flows/<flow_id>.yaml`，填写六段 schema；参数键与流程 `analysisyaml` 对齐。
4. 配置 `ai:` 段（工具 slug、摘要、参数白名单、是否需要确认、可选校验插件）。
5. 验证：
   - `FlowService().reload()` 加载无误；
   - Web 容器 `GET /api/v1/flows` 出现新流程；
   - 前端表单渲染并完成一次真实 dry-run；
   - AI 通道走固定工具完成 `list → detail → prepare → 人类确认 → submit` 闭环；
   - 工具发现清单数量不变。
6. 如需 Agent 人设或协作室通道，另走 `data/ai/` 体系，不在本清单内。

## 非 YAML-only 通道

以下通道接入新流程**需要改代码**，不属于“YAML 声明式接入”的承诺范围：

| 通道 | 硬编码点 |
| --- | --- |
| REST `/api/v1/pipelines/*` | `PipelineType = Literal["rna_seq", "atac_seq"]` + 手写适配器 |
| mcp-server `cygnusx-pipelines` preset | 手写 `rna_seq_*` / `atac_seq_*` 四件套 |
| 前端任务中心 | `PipelineType` union、flowLabel 映射、工具调用展示 |
| AgentTeams / MAS | `data/ai/flows/` 第二注册表（ID 命名规范不同） |

若接入目标只是“分析中心表单 + AI 助手聊天”，编辑/新增 `flows/*.yaml` 即可。

## 已有流程参考

- `flows/rna_seq.yaml` — RNAFlow，主配置 `config.yaml`
- `flows/atac_seq.yaml` — ATACFlow，主配置 `analysis.yaml`

## 注意事项

- `meta.id` 一旦确定尽量不要修改，数据库任务记录会关联该 ID。
- `pipeline_mapping` 缺失的流程只能展示和解析，无法提交执行。
- 嵌套字段在 `config_fields` 中使用点号路径；`list_fields` 用于多值字段归一。
- Flow 定义会随 Task 冻结，后续修改 YAML 不影响已提交任务。

## 相关页面

- [流程运行时](../architecture/flow-runtime)
- [分析流程与工作流](../features/workflows)
- [MCP 体系](../architecture/mcp)
- [项目结构](project-structure)

# 分析流程与工作流

CygnusX 使用 YAML 声明式 Flow + 通用构建器接入 Snakemake 流程。流程 YAML 定义用户可见的参数与
输入输出契约，Worker 和运行时镜像执行实际计算；新增流程前必须同时验证 YAML、Snakefile、运行时
依赖和交付目录。

## 已有流程

| 流程 | 文件 | 主配置文件 |
|---|---|---|
| RNA-seq | `flows/rna_seq.yaml`（v2.3.0） | `config.yaml` |
| ATAC-seq | `flows/atac_seq.yaml`（v0.1.0） | `analysis.yaml` |

## 流程加载

1. `FileSystemFlowRepository` 扫描并校验 `flows/*.yaml`，流程是否可提交取决于 YAML 的 `execution` 和 `pipeline_mapping` 是否完整。
2. 平台以 `meta.id` 识别流程，并将表单、样本表和比较组映射为工作目录中的运行文件。
3. 提交后由 Worker 在受控运行时中执行 Snakefile，并把日志、状态和产物回写平台。
4. 修改 YAML 后调用管理员接口 `POST /api/v1/flows/reload` 或重启服务；生产环境先在预发布环境验证。

## pipeline_mapping 示例

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
  sample_sheet:
    output_name: "samples.csv"
    columns:
      sample: sample
      group: group
```

## 新增流程步骤

1. 创建 `flows/{flow}.yaml`
2. 编写 `meta`、`parameters`、`execution`、`pipeline_mapping`
3. 放置 Snakefile
4. 使用流程重载入口或重启服务，再确认管理端已加载新 schema
5. 用真实和最小示例数据分别验证表单、样本表、执行日志、产物与权限隔离

具体的参数映射、Snakefile 约定和新增流程清单见 [分析流程扩展](../development/flow-extension)。

# 分析流程与工作流

OmicHub 使用 YAML 声明式 + 通用构建器接入 Snakemake 流程。新增流程通常只需在 `flows/` 下添加 YAML，无需修改后端代码。

## 已有流程

| 流程 | 文件 | 主配置文件 |
|---|---|---|
| RNA-seq | `flows/rna_seq.yaml` | `config.yaml` |
| ATAC-seq | `flows/atac_seq.yaml` | `analysis.yaml` |

## 流程加载

1. 服务启动后首次访问 `/api/v1/flows` 懒加载 `flows/*.yaml`
2. `FlowDomainService` 用 Pydantic 校验结构、参数唯一性、条件渲染
3. 校验通过的流程以 `meta.id` 为键缓存在内存
4. 修改后调用 `POST /api/v1/flows/reload` 热重载

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
4. 热重载：`curl -X POST http://localhost:8000/api/v1/flows/reload`
5. 前端通过 `/api/v1/flows/{id}/schema` 渲染表单

# 富集分析工具配置（tool_configs/enrichments）

本目录存放 KEGG / GO 富集分析工具的**物种配置**，仓库内源码管控（仿 `flows/`）。
R 计算镜像由用户自行构建，输入/输出契约见
[`docs/26.7.6/KEGG_Docker_契约.md`](../../docs/26.7.6/KEGG_Docker_契约.md)。

## 文件

| 文件 | 用途 |
|------|------|
| `species_config.yaml` | 物种列表：KEGG 三字码 / OrgDb / ID 类型 |

## 字段与后端映射

| YAML 字段 | 传入容器参数 | 前端 `SpeciesOption` | 说明 |
|-----------|-------------|---------------------|------|
| `id` | — | `id` | 物种唯一标识，提交时作 `species_id` 传回 |
| `display_name` | — | `label` | 展示名称 |
| `enabled` | — | — | `false` 则不出现在下拉 |
| `kegg_code` | `--kegg_code` | `kegg_code` | KEGG 物种三字码（hsa / ath） |
| `org_db` | `--org_db` | `org_db` | R OrgDb 包名 |
| `id_type` | `--id_type` | `id_type` | 基因 ID 类型（SYMBOL / TAIR） |
| `kegg_rdata` | （预留） | — | 离线 KEGG.RData 路径，在线失败 fallback 用 |
| `kegg_supported` | （预留） | — | 是否被 KEGG 注释覆盖，前端灰度用 |

> ⚠️ 物种三字码 / OrgDb / ID 类型由后端按 `species_id` 从本文件**权威解析**，
> 前端回传的同名字段仅作展示，不参与容器调用（防篡改）。

## 改完如何生效

配置加载器按文件 mtime 自动热重载，**改文件即生效，无需重启**。
若需强制立即生效，重启 web 容器即可（`docker restart omichub-web`）。

## 后端配置入口

- 路径由 `settings.enrichment_config_yaml` 决定（默认 `tool_configs/enrichments/species_config.yaml`）。
- 加载器：`src/omichub/infrastructure/config/enrichment_config.py`
- 服务：`src/omichub/application/services/enrichment_service.py`
- 容器执行器：`src/omichub/infrastructure/execution/enrichment_runner.py`
- 路由：`GET/POST /api/v1/enrichment/species`、`/api/v1/enrichment/submit`

## 新增物种

1. 在 `species_list` 追加一项，填好 `kegg_code` / `org_db` / `id_type`；
2. 确认对应 OrgDb 包已装进 R 镜像（`org.Xx.eg.db` 等）；
3. 保存即生效，前端刷新物种下拉可见。

# 2026-07-08 变更记录

## 今日完成

### 前端入口调整

- 移除主导航中的独立「代码沙盒」入口。
- 保留 `/sandbox` 兼容路由，并重定向到 `/tools/terminal`。
- 将云端沙盒终端作为统一执行环境入口，避免「代码沙盒」和「云端终端」功能重复。

### Makefile 文档

- 新增 Makefile 详细说明文档，记录常用命令、开发/部署/测试入口和使用边界。
- 将 Makefile 的使用说明从口头约定整理为可查阅文档，便于后续部署和协作。

### 日志架构优化

- 使用 loguru 的 rotation、retention、compression 能力限制应用日志体积。
- 为 Celery 单任务日志增加轮转、保留期和压缩策略。
- 为数据库任务日志增加单条 message 截断和最大条数限制，避免长任务日志撑大数据库字段。
- 增加 Docker stdout 日志大小限制，并补充 Nginx/Snakemake 的 logrotate 兜底策略。
- 更新 `LOG_ARCHITECTURE.md`，记录统一日志目录、容量保护、排障方式和本次架构更新。

### 参考数据库离线构建工具

- 新增 `scripts/pyproject.toml`，支持通过 `pip install -e ./scripts` 单独安装 `omichubtools`。
- 新增 `omichubtools` CLI，当前包含：
  - `omichubtools version`
  - `omichubtools refdb build`
  - `omichubtools build-reference-database` 兼容别名
- 复用 gpse 工具模块的设计思路，加入 logo、日志、版本和配置加载工具。
- 清理 `scripts/` 中不再需要的旧脚本，仅保留 Makefile 或部署仍引用的脚本。
- 使用 `rich-argparse` 美化 CLI help 输出，并保留缺依赖时的标准库 formatter 回退。

### FA/GFF/GO/KO/KEGG 离线构建能力

- `omichubtools refdb build` 支持从 FA、GFF、GO、KO、KEGG 原始文件生成：
  - `database.sqlite`
  - FASTA `.fai`
  - `database_manifest.json`
  - `jbrowse_assembly_snippet.yaml`
  - `build_report.json`
- SQLite 当前包含 FASTA 序列索引、GFF feature、gene、transcript、exon、GO、KO、KEGG 等表。
- 构建脚本保持离线执行，不挂到 Web API、Celery Worker 或前端点击链路，避免给平台服务造成压力。

### GO/KEGG 注释补全增强

- 新增 `--go-terms` 参数。
- `--go-terms` 支持 GO term TSV/CSV，也支持 `go-basic.obo`。
- 当 `--go` 只有 `gene_id/go_id` 两列时，可离线补全 `term` 和 `namespace`。
- 新增 `go_terms` SQLite 表，用于保存 GO ID、term、namespace、definition、source。
- 增强 `--kegg` 参数，支持三类输入：
  - `gene_id + kegg_id`
  - `gene_id + pathway_id`
  - `ko_id + pathway_id`
- 当 `kegg_id` 是 `Kxxxxx` 时写入 KO 注释；当存在 KO 到 pathway 映射时自动展开成 gene 到 pathway。

### 数据库模块现状排查

- 确认当前真实运行入口仍是 `tool_configs/jbrowse/jbrowse_config.yaml`。
- JBrowse 运行只强依赖 `fasta + fai`，GFF 需要作为 preset track 配置后才能显示。
- 当前 `/database` 页面仍读取前端 mock 数据，尚未接入真实后端数据库 API。
- 当前后端没有 `/api/database/*`，也没有服务消费 `database.sqlite`。
- 已明确后续方向：用 `omichubtools` 生成每个物种/版本的 SQLite，再新增后端数据库 API 和前端联通。

## 已验证

- `uv run ruff check scripts/omichubtools`
- `python -m compileall scripts/omichubtools`
- `PYTHONPATH=scripts python -m omichubtools --no-logo refdb build --help`
- `python -m pip install -e ./scripts --dry-run`
- 使用临时 FA/GFF/GO/GO-terms/KO/KEGG 样例构建 SQLite，验证：
  - GO term 补全正常
  - `gene_id/kegg_id` 写入 KO 正常
  - `KO -> pathway` 自动展开正常

## 当前边界

- 平台现在只注册和读取构建好的文件路径，不在运行时做 FA/GFF/GO/KO/KEGG 转换。
- `/database` 页面仍是 mock，需要后续改为真实 API。
- `database.sqlite` 已能生成，但平台后端还没有正式查询服务。


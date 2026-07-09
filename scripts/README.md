# omichubtools 工具目录

`scripts/` 现在作为 OmicHub 离线维护工具包 `omichubtools` 的源码目录。目标是把部署、数据准备、数据库构建、巡检等重型或管理员操作收敛到一个可安装的 CLI 中，避免把转换任务压到 Web 服务或 Celery 任务链路上。

## 安装方式

推荐只安装工具包本身：

```bash
pip install -e ./scripts
```

如果你同时需要安装整个平台，也可以在项目根目录执行：

```bash
pip install -e ./
```

安装后会注册命令，帮助信息由 `rich-argparse` 美化显示：

```bash
omichubtools --help
omichubtools version
omichubtools refdb build --help
```

未安装时，也可以用源码路径调试：

```bash
PYTHONPATH=scripts python -m omichubtools --help
PYTHONPATH=scripts python -m omichubtools refdb build --help
```

新自动化脚本统一使用 `omichubtools refdb build ...`。

## 当前命令结构

```text
omichubtools
├── version                         # 查看工具版本、Python 运行环境和外部工具状态
├── refdb
│   └── build                       # 离线构建 FA/GFF/GO/KO/KEGG 参考数据库资产
└── build-reference-database        # refdb build 的兼容别名
```

## 参考数据库离线构建

典型命令：

```bash
omichubtools refdb build \
  --species-id Lsat \
  --version-id Lsat_v11 \
  --version-name v11 \
  --assembly-name Lsat.1.v11 \
  --scientific-name "Lactuca sativa" \
  --common-name "生菜" \
  --fasta /data/omichub/omichub_data/db/Lsat/v11/Lsat.1.v11.fa \
  --gff /data/omichub/omichub_data/db/Lsat/v11/Lsat.1.v11.gff3 \
  --go /data/omichub/omichub_data/db/Lsat/v11/go_annotations.tsv \
  --go-terms /data/omichub/omichub_data/db/Lsat/v11/go_terms.tsv \
  --ko /data/omichub/omichub_data/db/Lsat/v11/ko_annotations.tsv \
  --kegg /data/omichub/omichub_data/db/Lsat/v11/kegg_annotations.tsv \
  --out-dir /data/omichub/omichub_data/db/Lsat/v11/build \
  --force
```

输出文件：

| 文件 | 用途 |
| --- | --- |
| `database.sqlite` | SQLite 查询库，包含 GFF feature、gene、transcript、GO term、GO、KO、KEGG 注释 |
| `*.fai` | FASTA 随机访问索引 |
| `database_manifest.json` | 构建清单 |
| `jbrowse_assembly_snippet.yaml` | 可合并到 `tool_configs/jbrowse/jbrowse_config.yaml` 的配置片段 |
| `build_report.json` | 构建统计和排查报告 |

`--go-terms` 可传 GO term TSV/CSV 或 `go-basic.obo`，用于把两列 `gene_id/go_id` 文件补全为带 term/namespace 的注释。`--kegg` 支持 `gene_id/kegg_id`、`gene_id/pathway_id` 和 `ko_id/pathway_id` 三类表。

CLI 帮助输出使用 `rich-argparse`，会保留参数默认值并用 Rich 样式突出命令、分组、参数名和 metavar。

平台只注册这些生成好的文件路径，不在 API 或 Worker 中执行转换。

## 包结构

```text
scripts/
├── pyproject.toml                    # omichubtools 独立安装配置，支持 pip install -e ./scripts
├── omichubtools/
│   ├── cli.py                         # 顶层 argparse 入口
│   ├── commands/
│   │   └── reference_database.py       # refdb build 命令实现
│   ├── config/
│   │   ├── default.yaml                # CLI 默认日志配置
│   │   └── software.yaml               # 工具元信息和外部工具声明
│   └── utils/
│       ├── configuration.py            # 包内 YAML + 项目覆盖配置加载
│       ├── logo.py                     # 终端 logo，参考 gpse LogoDisplay 风格
│       ├── log_utils.py                # loguru/rich 日志初始化
│       └── version.py                  # version 命令展示
├── check_migrations.py                 # Makefile 仍在调用，后续可迁入 omichubtools
├── download_jbrowse2.sh                # JBrowse 2 静态产物下载脚本，部署文档仍在引用
├── init_admin.py                       # Makefile/README 仍在调用，后续可迁入 omichubtools
└── init_cookies.py                     # Makefile/README 仍在调用，后续可迁入 omichubtools
```

## 配置覆盖

`omichubtools` 默认读取包内配置：

- `scripts/omichubtools/config/software.yaml`
- `scripts/omichubtools/config/default.yaml`

后续如需要项目级覆盖，可在当前工作目录放置：

- `omichubtools.yaml`
- `omichubtools.local.yaml`

或者使用全局参数传入：

```bash
omichubtools --config ./my-tools.yaml version
```

## 后续扩展规范

新增子命令建议遵循以下方式：

1. 在 `scripts/omichubtools/commands/` 下新增独立模块，例如 `downloads.py`、`deploy.py`。
2. 模块中提供 `add_<command>_arguments(parser)` 和 `run_<command>(args)`，保持 argparse 入口清晰。
3. 在 `scripts/omichubtools/cli.py` 注册到对应 subparser。
4. 重型任务必须保持离线执行，不要在 Web API、Celery Worker 或前端点击链路中隐式触发。
5. 输出产物写入 `/data/omichub/omichub_data/...` 或显式 `--out-dir`，并生成可审计的 manifest/report。
6. 新命令完成后同步更新本文档和必要的架构文档。

## 与 gpse 工具模块的关系

本目录复用了 gpse 中 `logo.py`、`log_utils.py`、`version.py`、`configuration.py` 的设计思路，但没有在运行时 import 外部 gpse 仓库。原因是 `pip install -e ./scripts` 部署时不能依赖另一个本地 checkout。

当前实现提供同类能力：

- `utils/logo.py`：启动 logo，支持 rich/rich-gradient 可选增强。
- `utils/log_utils.py`：loguru + rich 控制台日志，rich 不存在时自动降级。
- `utils/version.py`：展示 Python、依赖包和外部工具状态。
- `utils/configuration.py`：包内 YAML 配置 + 项目级覆盖。

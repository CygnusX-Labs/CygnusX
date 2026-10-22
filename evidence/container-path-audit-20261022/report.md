# 工具箱容器路径同类问题排查

> 本报告保留修复前的排查结论。后续代码整改与当前验证结果见
> `../container-path-fixes-20261022/validation.md`；`audit-results.json` 已由复现脚本更新为修复后的路径核对结果。

排查日期：2026-10-22。当前环境 `STORAGE_PATH=/data/omichub`，
`DEG_DATA_MOUNT` 和 `ENRICHMENT_DATA_MOUNT` 都派生为 `/data/omichub`。

本轮读取代码、构造实际 argv、检查本地配置和文件；没有启动分析容器、提交分析任务或修改业务代码。
命令复现脚本：`audit_paths.py`；逐参数结果：`audit-results.json`。

## 1. 已确认的同类缺陷

### 1.1 DEG：DESeq2 和 edgeR 均受影响

- 位置：`src/cygnusx/tools/deg/runner.py:81`、`:89`、`:100`。
- 挂载为 `/data/omichub:/data/cygnusx`，表达矩阵、样本表、比较表、输出目录、注释文件的路径均原样传入。
- `tools/deg/tasks.py:72` 从 Task 的实际 `work_dir` 构造参数，没有后续路径转换；当前 YAML `execution.use_docker=true`。
- 构造命令实测：两个引擎的 5 个文件参数均未落在容器数据挂载目标下。
- 修复范围：5 个路径必须转换到容器路径；Worker 读取结果仍使用原始宿主路径。

### 1.2 GSEA：输入、输出和 GO 参考注释

- 位置：`src/cygnusx/tools/gsea/runner.py:18`、`:28`、`:37`、`:48`。
- 与 GO/KEGG 一样挂载到 `/data/cygnusx`，却将任务的 `/data/omichub/...` 参数原样传入。
- 该类虽然继承 `EnrichmentDockerRunner`，但覆盖 `build_command()`，不会自动调用 GO/KEGG 新增的路径转换。
- 构造命令实测：3 个文件参数均未落在挂载目标下。
- 另一个独立阻断：Celery `include` 和 `task_routes` 缺少 `cygnusx.tools.gsea.tasks`。
  新 Python 进程执行 `celery_app.loader.import_default_modules()` 后，
  `cygnusx.tools.gsea.tasks.run_gsea_task` 的 `registered=False`；DEG、synteny、GO/KEGG 为 True。
  这项验证只证明当前源码的默认加载行为，不代表检查了生产 Worker 内存中的注册表。
- 修复范围：路径转换与任务注册都要覆盖。

### 1.3 共线性：GFF3、BLASTP 输入及 JSON 输出

- 位置：`src/cygnusx/tools/synteny/runner.py:26`、`:28`。
- `tools/synteny/tasks.py:37` 将运行目录下两个输入和一个输出的绝对路径直接传给 Runner。
- 构造命令实测：3 个文件参数均未落在 `/data/cygnusx` 挂载目标下。
- 修复范围：转换全部 3 个文件参数，并补充换根部署验证。

### 1.4 JBrowse：两套参考基因组和访问 URI

- 位置：`tool_configs/jbrowse/jbrowse_config.yaml:47`、`:59`、`:88`、`:100`；
  `src/cygnusx/tools/jbrowse/config.py:234`。
- human_hg38 和 arabidopsis_tair10 的 FASTA/FAI 共 4 个配置值仍指向
  `/data/cygnusx/cygnusx_data/...`；4 个配置文件路径均不存在，
  对应文件在 `/data/omichub/omichub_data/...` 下均存在。
- `to_tracks_uri()` 发现文件不在当前数据根下后，返回只含文件名的地址。例如：
  `/tracks/TAIR10_chr_all.fas`。按当前 nginx `alias /data/omichub/` 解析，
  对应文件也不存在。目录信息丢失，不能通过该地址读取实际参考文件。
- 同份 YAML 的 GFF/预设轨道也使用该错误根前缀，需要一起核对修正。
- 修复范围：将参考资产与配置的参考库/当前数据根统一，校验生成的完整 `/tracks/` 路径。
  本轮没有向线上 HTTP 端点发请求，不将文件和 URI 核对表述为线上 HTTP 测试结果。

## 2. 当前部署匹配，但换根部署仍有风险

| 位置 | 问题与条件 |
|---|---|
| `tool_configs/terminal/terminal_config.yaml:78` | `workspace_base=/data/omichub/users`，显式 YAML 覆盖由 Settings 派生的默认值。当前根匹配，迁移后不会仅随 `STORAGE_PATH` 改变。 |
| `tool_configs/download/download_config.yaml:12` | 下载器及云 CLI 路径固定在 `/data/omichub/bin`，加载优先级高于 Settings。同样属于迁移风险，不据此判断当前下载故障。 |
| `tool_configs/fastq_qc/config.yaml:68` | 输出根固定 `/data/omichub/qc/tasks`；该工具目前仍是预检入口，不等同于已有运行任务失败。 |
| `tool_configs/jbrowse/jbrowse_config.yaml:124`、`:141` | 用户扫描和上传目录固定旧根，与参考资产错误并存，但当前用户目录根本身匹配部署。 |
| `deploy/docker/nginx/nginx.conf:189`、`nginx.prod.conf:143` | `/tracks/` alias 固定旧根；当前匹配 `/data/omichub`，换根只改 Compose/env 不会自动改 alias。 |
| `deploy/docker/docker-compose.phylo.yml:19`、`:37` | 旧独立编排固定挂载 `/data/cygnusx:/data/cygnusx`。当前标准启动脚本使用的是 `docker-compose.worker.yml` 中 profile 门控的 phylo 服务，后者挂载已参数化；不能将旧编排问题归到当前默认运行栈。 |
| `data/CygnusX.yaml:30` | `storage.data_root=/data/omichub` 优先于 Settings 的 `storage_path`，可能产生路径工厂与 Runner 各自取不同数据根的问题。当前两个值一致，换根需同步这层配置。 |

## 3. 已检查而未复现相同参数错配的路径

- **BLAST 搜索**：数据库、查询和结果目录分别挂载为 `/blast_db`、`/query`、`/results`；
  命令参数使用相应容器路径。当前环境构造命令的 3 个文件参数均受挂载覆盖。
  当前配置实际为 `use_docker=false`；这里额外核对了 Docker 分支。
- **BLAST 建库**：源码将目录挂到 `/work`，输入与索引输出均采用 `/work/...`。
- **终端**：源码明确将宿主工作区挂到 `/home/cygnusx/workspace`，容器工作目录使用该路径。
  风险是上节固定的挂载源配置，不是将宿主文件名直接传给容器。
- **Studio/聊天沙盒**：检查了显式 `/workspace`、`/data/platform`、输入/输出目录挂载；
  未看到与 DEG/GSEA/synteny 相同的 argv 透传模式。未做真实容器运行验收。
- **MAS Scanpy / Apptainer**：命令入口采用 `/workspace/...`；Scanpy 输入被限制在 `/workspace/input`，
  Apptainer 明确将运行根挂到 `/workspace`。没有归类为本次同类参数错配。
- **FASTQ QC/普通建树执行器**：直接运行进程内可见的本地程序，不是另启 R Docker 后仍使用宿主路径的模式。
- **通用 Flow LocalSnakemakeExecutor**：在 Worker 内直接运行 Snakemake；
  本轮未审查各 pipeline 子仓内部所有规则、镜像和路径。

这些观察仅覆盖指定构造器与挂载代码，不构成整个模块或生产运行的全面通过证明。

## 4. 防复发检查的盲区

`scripts/check_storage_paths.py` 实跑通过，但它只扫描 `src/cygnusx/**/*.py` 中的
`/data/` 字面量，并豁免 `:/data/cygnusx` 挂载声明：

1. 不能判断 `params.counts_path` 等变量是否映射到容器挂载点。
2. 不扫描 `tool_configs/*.yaml`、nginx 和 Compose 中的固定路径。
3. `tests/unit/tools/test_deg_tool.py:151` 的主要路径用例把宿主和容器根都设为 `/data/cygnusx`；
   另一条命令测试使用 `c/m/p/o` 占位字符串，均不能识别本次真实部署的错配。

建议补充统一挂载路径转换及命令契约验证，至少覆盖：同根、宿主/容器根不同、
Worker/daemon 根不同、已有容器绝对路径、越界路径，以及输出写回原 Task 目录。

## 5. 建议处理顺序

1. 先覆盖 DEG、GSEA、共线性的全部文件参数；GSEA 同步修复默认 Worker 任务注册。
2. 对齐 JBrowse 的参考资产和完整访问 URI。
3. 收敛配置中的固定数据根，补足换根部署检查。
4. 在可访问 Docker 管理接口的环境重启相关进程，逐工具验证真实输入、结果 CSV/JSON、图表和下载。

此前 GO/KEGG 的工作区代码修复已在本次构造命令审计中通过；原故障的线上验收仍为受阻状态，
不能将这次排查报告作为生产故障已恢复的证明。

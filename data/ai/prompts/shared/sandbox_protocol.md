## 共享沙盒协议

### 沙盒目录使用规范

沙盒工作目录结构固定，所有文件操作必须遵守以下放置规则：
- `input/`（只读）：用户上传的原始数据。不得修改、覆盖、删除或重命名；转换结果写入 `output/`。
- `ref/`（只读）：参考基因组、注释文件和公共数据库。规则同 `input/`。
- `scripts/`：生成的脚本与代码，主脚本使用有意义的文件名。
- `output/results/`：结果表格与数据文件；`output/figures/`：图表；`output/logs/`：运行日志；`output/tmp/`：中间文件。
- 不要在工作区根目录或家目录散落数据、脚本和结果文件；真正的临时文件写入 `/tmp`，任务结束即弃。
- 文件名统一使用小写加下划线，必要时带项目名和关键参数，便于追溯与避免覆盖。
- 交付时输出每个产物的实际路径和一句话说明；每个分析在 `output/results/` 写 `<project>_summary.md`，会话结束在 `output/README.md` 汇总分析与产物。

### 现场装包与验证

- 先核对运行时能力和 import 声明；Python 包优先 `uv pip install`，pip 必须指定白名单源 `https://pypi.org/simple` 或 `https://mirrors.aliyun.com/pypi/simple/`。
- 系统级工具和 R 包使用 `micromamba install -y -n base -c <channel> <pkg>`；安装前用 `conda-meta-mcp` 的 `import_mapping`、`pypi_to_conda`、`package_search` 确认包名、channel 与 linux-64 版本；查询失败才退回 `micromamba search`。
- 禁止使用不在白名单的镜像、`install.packages()` 或 `remotes::install_github()`；GitHub 独占包无法安装时如实说明。
- 安装完成必须用 CLI `--version` 或 Python/R import 验证，记录真实包名和版本；失败时如实报告，不伪造安装或运行结果。
- 生成脚本先落盘，再执行；执行前先用小样本冒烟，长任务说明预期耗时。
- 用户单独查询软件包版本、依赖或安装方式时，优先用 `conda-meta-mcp` 查询并汇报；分析过程中的缺包安装属于后台动作。
- Studio 中若 `conda-meta-mcp` 未加载，先调用 `studio_capability_load`；查询包信息后说明当前可在 AI 工作台沙盒中直接安装和验证。

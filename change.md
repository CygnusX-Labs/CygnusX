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

# 2026-07-10 变更记录

## 今日完成

### 节日弹窗全屏沉浸式背景动画

- 新增 `frontend/src/components/FestivalBackground.vue` 独立背景动画组件。
- 实现三层核心效果：
  - 暗流涌动的径向渐变背景（中心极暗酒红 #2A0A0A 过渡到纯黑）+ 14s 缓慢呼吸缩放。
  - 26 个重度模糊、琥珀金/琉璃金色调的星火粒子，自下而上漂浮并随机闪烁。
  - 卡片正后方暗金色光晕，80px 模糊 + 6s 缓动呼吸动画。
- 组件固定 `z-index: -1` / `pointer-events: none`，并兼容 `prefers-reduced-motion`。

### 按节日特点定制背景动画

- 春节 / 国庆：红灯笼浮动 + 酒红底。
- 元宵节：水面灯影涟漪 + 暖橙底。
- 端午 / 立春：竹叶飘落 + 墨绿底。
- 七夕：鹊桥弧线 + 流星划过 + 深紫底。
- 中秋 / 冬至：月晕 + 水面涟漪 + 藏蓝底。
- 圣诞 / 元旦：雪花飘落 + 藏蓝底。
- 重阳 / 秋分 / 夏至：枫叶/落叶飘落 + 秋褐底。
- 情人节：爱心上升 + 玫红底。
- 程序员节：绿色代码雨 + 纯黑矩阵底。
- 周年庆：同心轨道旋转 + 星点绕行 + 深紫蓝底。

### 背景动画层级与清晰度修复

- 修复 `z-index: -1` 导致动画被毛玻璃 backdrop 压暗/模糊的问题：
  - `FestivalBackground.vue` 提升为 `z-index: 2`。
  - `FestivalEffect.vue` Canvas 层提升为 `z-index: 3`。
  - 保持 `festival-backdrop` 在 `z-index: 1`，先模糊页面再渲染动画。
- 降低过度模糊：
  - Canvas 层从 `blur(12px)` 降至 `blur(2px)`。
  - 节日专属图形（灯笼、雪花、枫叶、爱心、轨道等）从 1~2px 模糊降至 0~0.5px。
  - 保留光晕/星火粒子的柔和模糊作为氛围。

### 数据管理目录树计数修复

- 修复 `DirectoryTree.vue` 中系统目录（如 `raw_data`、`temp`、`workspace`）显示文件计数徽章的问题。
- 现在仅用户自建目录显示计数，系统目录保持名称整洁。

## 已验证

- `npm run type-check` 通过。
- `npm run build` 通过。

# 2026-07-11 变更记录

## 今日完成

### 实验室知识库快速入门文档重写

- 重写 `docs/knowledge/getting-started.md`，将 Carl Sagan 的引言置于文首。
- 补充 OmicHub 平台理念：让数据回归科学、过程可复现、知识沉淀与共享。
- 详细说明 10 个核心模块的平台理念与使用方法：
  数据管理、分析流程中心、任务中心、AI 聊天助手、实验室知识库、
  云端沙盒终端、饼干积分、富集分析与可视化、JBrowse 2、MCP 工具扩展。
- 增加首次使用四步上手、常见问题排查与获取帮助指引。

### 知识库文件同步机制

- 新增 `scripts/sync_knowledge_from_files.py`：
  - 将 `docs/knowledge/*.md` 按 `meta.yaml` 同步到数据库。
  - 支持 `--auto-admin` 自动选择管理员作为同步者。
  - 使用 Rich 输出彩色同步结果表格，并关闭 SQL echo 日志。
- `Makefile` 新增 `sync-knowledge` 目标，`docker-reload` 执行后自动同步知识库。
- `deploy/docker/docker-compose.yml` 挂载 `scripts` 目录到 web 容器，确保容器内可执行同步脚本。
- 说明：知识库以数据库为权威源，网页端编辑过的文档会入库；直接修改 .md 后需执行同步网页才生效。

### 知识库前端 UI 优化

- 左侧侧边栏：
  - 「新建文档」改为全宽主题蓝 CTA 按钮（无边框、圆角、白字）。
  - 「待审核」改为纯文本 + 图标的菜单项样式。
  - 目录树菜单项统一增加 hover 浅灰背景、圆角与间距。
- 底部讨论区：
  - 增加浅灰分割线与顶部间距，与正文区隔开。
  - 输入框改为 100% 宽度的多行文本域，带浅灰边框、8px 圆角、内边距与占位符。
  - 「发送」按钮移至输入框右下角，使用 Flex 靠右对齐。

### Git 提交整理

- 将工作区变更按功能拆分为 3 个 commit：
  - `feat(knowledge)`：实验室知识库重构与同步机制。
  - `feat(festival)`：节日彩蛋系统与全屏沉浸式背景动画。
  - `feat(workflow-monitor)`：Snakemake 流程监控模块（含旧 `tools/` 目录清理）。
- 剩余未提交：`pipelines/EBIDownload` 子模块仍有本地修改，需单独处理。

## 已验证

- `python -m py_compile scripts/sync_knowledge_from_files.py`
- `cd frontend && npm run type-check`
- `make docker-reload` 可正常完成并自动同步知识库。

## 当前边界

- `pipelines/EBIDownload` 子模块变更未提交。
- 知识库网页端目前缺少文档删除按钮，后续可补充。


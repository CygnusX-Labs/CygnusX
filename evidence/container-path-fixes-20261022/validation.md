# 工具箱路径整改与验证

## 已完成的代码整改

- `tools/container_paths.py::ToolDataMount` 统一表示 Docker daemon 的挂载源、Worker 数据根和固定容器目标。GO/KEGG、DEG 两个引擎、GSEA、共线性的输入、输出、注释文件全部经过转换；拒绝相对路径、卷外路径及 `..` 逃逸。Task 的原目录和结果回读路径保留。
- GO/KEGG 与 GSEA 通过参数类型明确的 `EnrichmentDockerRunnerBase` 共享原有执行/超时逻辑，消除原有 GSEA 覆盖方法的参数类型冲突。
- GSEA 同时登记 Celery `include` 和 `task_routes`。新进程的真实默认模块加载测试确认任务已注册，路由队列为 `analysis`；当前 27 个 include、26 条 routes。
- JBrowse 的人类/拟南芥参考文件、索引和预设轨道相对 `REFERENCE_GENOMES_YAML` 所在目录解析，兼容显式绝对路径。卷外路径不再退化为仅文件名的错误 URI。
- Nginx 开发/生产配置统一 `alias /srv/tracks/`，Compose 将真实数据源只读挂载到此固定容器路径，宿主目录改名不再要求修改 alias。
- 终端、下载、FASTQ QC、JBrowse 用户目录的仓库配置留空派生；`data/CygnusX.yaml` 默认数据根也留空，避免覆盖 Settings。下载 `.env.example` 同步留空，已有部署的显式 env/YAML 自定义覆盖仍优先。
- 旧独立 phylo Compose 的数据卷及进程内 `STORAGE_PATH` 已参数化，没有启用当前关闭的 phylo 服务。
- 活动存储、工具箱和异步队列架构文档已同步；新增回归覆盖挂载参数契约和配置迁移，弥补原字面量守卫的盲区。

## 当前验证证据

- 一次组合运行 **107 passed, 1 deselected**：工具挂载、富集、DEG、参考路径、存储配置、GSEA 新进程注册、FASTQ 配置、路径工厂、29 项文件服务测试及 JBrowse HTTP 配置集成测试。
- JBrowse HTTP 集成测试通过真实路由、配置加载器和服务生成响应，只替换测试身份及临时配置，不连接生产 DB。
- 实际部署数据核对：DEG 两个引擎、GSEA、共线性、GO/KEGG、BLAST 的全部受检文件参数落在正确容器挂载下。JBrowse 两套参考组的 FASTA/FAI 共 4 个路径及其完整 `/tracks/` 地址均对应已有文件。详见 `../container-path-audit-20261022/audit-results.json`。
- 本次修改的 Python 文件 Ruff 通过；8 个修改源文件的定向 mypy 通过。
- 存储路径守卫、Worker 配置一致性、迁移链、环境配置示例漂移、`git diff --check` 通过。
- `make validate-image-mapping` 通过：17 个镜像、19 个启用 Agent 的运行时契约；`load_agent_configs()` 实际加载 19 个。
- 开发、生产 override、旧 phylo 三种 Compose `config --quiet` 均通过；实际开发 Compose 展开后数据卷为 `/data/omichub -> /srv/tracks`，只读。
- 隔离的 1 项是既有 `_project_slug` 过时测试，不作为通过项计数。

## 全仓检查仍有存量限制

- 全仓 Ruff：267 项错误，本次修改的 16 个 Python 文件中无命中。原始机器结果保存在 `ruff-full.json`。
- 全仓 mypy：212 个文件中的 1,012 项错误；定向检查的 8 个修改源文件无错误。全仓原始输出见 `/tmp/omichub-path-fix-mypy.txt`。
- 文档计数守卫仍有已有 ORM/迁移数量漂移（116/120 表、119/129 迁移等），没有为本次工具修复修改其它模块的统计。
- 扩大到存储后端和生命周期套件时，在已有的异步本地存储用例挂起，90 秒有界运行最终退出 137；未将该扩展套件记为通过。文件服务 29 项在最终组合运行中单独确认通过。

## 尚未完成的部署与真实运行验收

实际尝试 `docker restart --timeout -1 cygnusx-worker` 和
`docker exec cygnusx-nginx nginx -t` 都被环境拒绝：访问 Docker socket 返回
`operation not permitted`。因此未重启 Worker、未更新 Web 进程、未重建 Nginx、未重投任务，
不声明线上故障已经恢复。

开发 bind mount 栈需要执行的部署动作：

1. 按现有部署流程加载 Web/Worker 的新 Python 代码；Worker 可使用
   `docker restart --timeout -1 cygnusx-worker` 等待在途任务退出后重启。
2. 新的 Nginx 数据卷必须通过重建容器应用，单纯 reload/restart 不会改变已有挂载。
   本地开发栈可执行：

   ```bash
   docker compose --env-file .env -f deploy/docker/docker-compose.yml up -d --no-deps --force-recreate nginx
   ```

   生产环境须沿用其实际 override 文件组合；业务镜像部署须先包含本次代码。
3. 在 Worker 内核对 GSEA 已注册且消费 `analysis`，重提 GO/KEGG、DEG、GSEA、共线性示例；
   检查任务终态、原 Task 输出目录、CSV/JSON、图表和下载。
4. 验证 JBrowse `/tracks/` 参考文件与索引的 HTTP/Range 请求。现有内网访问控制保持不变。

本次没有更改统计计算脚本、创建迁移、移动用户文件或重建 R 镜像。

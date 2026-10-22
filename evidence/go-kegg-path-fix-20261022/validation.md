# GO/KEGG 输入路径故障验证

## 已确认原因

失败任务：`5c653583-aa7e-4ffa-8b42-3fa3aaebb235`。

`/data/omichub/logs/app/cygnusx.spans.json.log` 中该任务的 `toolbox.runner` 记录显示：

- 数据卷为 `/data/omichub:/data/cygnusx`。
- R 的 `--input` / `--output` 却仍使用 `/data/omichub/...`。
- 三个参考文件原配置为 `/data/cygnusx/cygnusx_data/reference/ITAG4.1/...`，对应的宿主目录不存在。
- 实际参考文件位于 `/data/omichub/omichub_data/reference/ITAG4.1/`。

## 验证结果

- 修复前新增的路径回归测试复现 8 项失败；修复后富集相关测试为 **17 passed, 1 deselected**。隔离的是已有失效 `_project_slug` 测试。
- `ruff check`：本次修改的 4 个 Python 文件通过。
- `mypy --follow-imports=silent`：修改的两个源文件通过。
- `scripts/check_storage_paths.py`、`scripts/check_migrations.py`、`git diff --check` 通过。
- 实际任务的输入为 1,576 个不重复基因；输入与三个参考文件均能通过新命令的挂载关系映射到已有文件。输出映射回任务原 `output/enrichment_result.csv`；该结果尚未生成。明细见 `path-check.json`。
- 全仓 `ruff check src/ tests/` 报 270 项错误；全仓 `mypy src/cygnusx/` 报 213 个文件中的 1,014 项错误。上述定向检查通过，未修改其它模块来处理这些错误。
- 扩大执行 `tests/unit/tools` 时停在已有的 `test_tool_bridge.py::test_upload_ref_resolution`；中断后单独诊断也在异步等待中挂起，未将全工具箱测试记为通过。

## 尚待真实运行验收

续轮复核时 `docker ps` 可列出容器，Worker 显示持续运行 22 小时；但
`docker inspect`、`docker exec` 以及实际执行的 `docker restart --timeout -1 cygnusx-worker`
均在访问 `/var/run/docker.sock` 时返回 `operation not permitted`。Worker 未重启、原任务未重投，
原结果 CSV 仍不存在，因此无法完成真实 R 容器验收。

第三轮复核发现新任务 `5fc2555f-eb51-49b3-8a93-2d4c1de3f813`
（`enrichment-20261022-142850`）。其 Worker span 在 UTC 14:28:55 记录退出码 1，
命令仍将 `/data/omichub/.../input/gene_list.txt` 传给挂载点为 `/data/cygnusx` 的容器；
参考参数为尚未解析的 `ITAG4.1/...`。这证明运行中的 Worker 仍在使用旧 Python 模块，
仅重提任务未加载磁盘上的修复。Docker 管理操作连续三轮被拒绝，目标标记为受阻，
需要恢复执行环境权限或在宿主机重启 Worker 后继续真实验收。

在有 Docker 权限的宿主机仓库根目录执行：

```bash
./scripts/worker-compose.sh restart worker
```

然后从工具箱页面按原参数重新提交 COP1/HY5 基因列表，检查新任务成功、CSV 中 GO/KEGG 来源、图表和下载。代码与配置通过 bind mount 加载，本次变更无需重建 R 镜像。

在上述运行验收完成前，不声明线上故障已恢复。

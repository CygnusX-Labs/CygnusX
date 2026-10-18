# RI095 运行验收环境交付记录

2026-10-17：PARTIAL（配置交付），BLOCKED（真实运行）。未重写 RI01–RI13/RI09.5，未修改生产业务代码、默认门禁、旧 Manifest/ZIP 或迁移。

新增 deploy/acceptance 下 Compose、env 示例、最小镜像扩展、runtime/control/checks/summarize Python 脚本、run-checks.sh、只读 state.sql、私有卷目录、Nginx 配置、浏览器启动探针和 README。新增两份 audits 文档及 evidence/runtime-acceptance 证据。

复用现有 ReportService、ProjectReportJob、ProjectExportJob、FileRegistry、StorageBackend、Auth 和前端。运行入口禁用 .env 并检查目标与实际 PG 身份；处理 YAML 优先的存储根；专用队列/Beat，仅保留四个项目任务注册；应用 UID10001/cap_drop ALL，无生产挂载或 socket。上述运行行为仍待真实容器认证。

已执行离线 Compose 渲染、六项错误配置拒绝、Ruff/format、Node 语法检查。没有真实运行失败可供业务修复；未删除安全断言。完整业务浏览器脚本、精确阶段故障注入和全部业务执行器尚未实现，按 Docker Gate 阻断范围交付操作说明，未假报通过。

回滚：停止本专用 Compose project；私有 env 的 READS/WRITES/PDF 全改 false；如只读重启则核对实际 flags 输出。不要只改 env 留旧进程运行。保留独立 PG/Redis/私有卷、Job 和冻结证据；禁止 downgrade/drop/down -v 清除审计事实。当前未启动服务，因此无需执行关闭操作。生产下载/分析门禁与全部默认值保持原状。下一阶段准入和具体步骤见 deploy/acceptance/README.md。

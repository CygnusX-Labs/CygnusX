# RI-ENV-01 Integration Runtime Enablement

日期：2026-10-17。结论：BLOCKED，未建立运行环境。按任务的无可执行授权环境分支输出最小要求并停止，无 PASS_RUNTIME。

## 1. 环境准入与授权范围

HEAD：d9c92cf6ee1c1e8de902c2b897b93f60b4f00f33；工作树基线见 evidence/ri-env-01/status-before.txt。当前没有明确的测试主机、Environment ID、端口、目录、镜像、故障注入和清理责任清单。测试资源变量存在性见 environment.json，均未提供；没有读取根 .env 或打印凭据。Docker socket 连接和 TCP loopback bind 均返回 EPERM，未向 daemon 发送操作命令。不推断所有远端资源不存在，但本会话没有可执行且范围明确的目标。

## 2. 实际运行拓扑

本轮没有启动服务，无实际拓扑。最小目标为独立 PG、Redis Broker/result/防重放、原 FastAPI、专属 Celery Worker/Beat、独占 local storage，随后接入原 Node Research Runtime 与 Chromium。此为需求，不是运行事实。

## 3. 复用的 Compose 与配置

已检查主 Compose、Worker Compose、deploy/docker/README.md、deploy/acceptance/README.md、compose.yml、acceptance.env.example 和 AgentTeams 配置入口。模板 SHA-256 见环境证据。主栈共享网络/环境/存储不能原样接入测试。现成 acceptance 为 RI095 报告/导出栈，已有 internal 网络、独立 PG/Redis/卷、UID 10001，但仅注册 report/export 任务与 Beat，不能直接充当 S4-B1。AgentTeams bridge 也不能当作 Node Research Runtime。本轮不修改既有模板；授权后复用原服务与隔离控制模式，审查最小接线，不复制业务逻辑。

## 4. 服务版本

源码 commit 和模板摘要已记录。PG/Redis/Broker/Worker/Beat/API/Node/Chromium 服务版本、镜像 digest、工作树运行一致性均 NOT_TESTED。docker/node/chromium 客户端存在不证明服务可用。未构建或拉取镜像。

## 5. 安全隔离边界与最小部署要求

需要明确以下资源后才能部署：

- disposable Docker/Linux/VM 目标、允许操作及实际权限；TCP/Unix IPC 与进程管理可用。
- 固定 Environment ID、独立 Compose project/network、批准端口范围，不占业务端口。
- PG 专用数据库/角色、Redis 实例或严格隔离 DB/namespace、Broker 专属队列/result backend、Worker identity 和 Beat schedule。
- 专属 Storage Root、用户/项目、UID/挂载权限、CPU/内存/磁盘/连接/消息/时长额度。
- 审查过的含源码 SHA 应用镜像与固定 digest 基础镜像，记录工作树摘要；不使用 latest。
- 故障注入仅针对本环境的 Worker/Broker，明确断连/重启/丢应答范围；禁止影响共享服务。
- 清理责任人、保留期、备份与证据目录；首次连接验证真实 SQL 身份再迁移写入。

不得挂载生产数据，不使用默认业务库。凭据受控注入，不在聊天或日志明文传递。DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED=False、WRITE_RUNTIME_ACCEPTED=False；无外部下载 Worker 场景须先审查，不移除 require_download_runtime。

## 6. PostgreSQL 验证

NOT_TESTED / RUNTIME_BLOCKED。多事务、原行锁、请求幂等、唯一约束、JSON 执行计划、取消/登记竞争和性能均未运行，没有 SQLite 替代结论。

## 7. Broker / Celery 验证

NOT_TESTED。未启动 Worker/Beat、发布消息或故障注入。提交后发布、重复领取、恢复扫描、断连恢复和异常退出均待验，未来仅使用审查过的无外部下载场景。

## 8. Redis 验证

NOT_TESTED。Broker/result、委托防重放、Confirmation TTL 和单次消费待真实隔离实例验证，不以 MemoryStore 代替。

## 9. Node / FastAPI 验证

NOT_TESTED。没有运行 callback/API 地址、可信委托和身份。后续复用原 Node Research Runtime、Gateway、Legacy/LangGraph，验证双用户多项目与结果回灌，fetch 替身不算运行通过。

## 10. Chromium 验证

NOT_TESTED。本轮不重复旧浏览器失败探针。需要可用 Chromium、匹配驱动、可写 profile 和测试 UI/API 可达性；保留 sandbox，保存实际业务截图/网络/console，不以首页或 jsdom 代替 E2E。

## 11. 实际运行测试与证据

仅执行只读准入探针，环境证据见 evidence/ri-env-01/environment.json，基线见 status-before.txt。探针脚本 exit 0 表示成功记录 EPERM，不代表环境通过。无业务测试数字。后续必须逐项记录 Environment ID、commit/工作树摘要、镜像 digest、服务版本、Task/用户/项目、命令、起止时间、退出码、断言和 evidence path。当前缺失值明确未建立，不伪填运行结果。

## 12. S4-B1 验收状态

仍 RUNTIME_BLOCKED，见 [S4-B1](download-s4b1-runtime-reliability-acceptance.md)。本轮无真实 PG/Broker/Worker/Beat 新证据。

## 13. S5-C2 验收状态

仍 BLOCKED，见 [S5-C2](download-s5c2-agent-runtime-acceptance.md)。Redis、Node/API、权限、双 Runtime 与浏览器运行证据未新增。

## 14. G3 独立阻断

仍 PARTIAL_CODE / RUNTIME_BLOCKED，DOWNLOAD_EXECUTION_READY=FALSE。环境可用不等于受信 supervisor、出站限制、硬预算、逐协议认证和停止对账通过；本地文件或只读成功不能解除门禁。

## 15. 环境清理和回滚

未创建业务容器、卷、用户或数据库，无运行资源需清理。仅新增本文、本地证据和罗盘链接；无生产代码/部署修改，无提交/推送。撤回逐文件/hunk，不整仓 reset/clean。后续只停止本 Environment ID 的服务，先保存证据，不自动 down -v 或删除历史 Task/用户文件；明确保留期与备份后按授权处置。当前按无环境分支停止，不新增 Mock 框架或部署平台。

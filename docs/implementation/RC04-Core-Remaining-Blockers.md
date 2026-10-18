# RI09.5 RC04-Core Remaining Blockers

日期：2026-10-18（Asia/Shanghai）

RC04-Core 当前未签收。以下阻塞项均影响最终接受结论；未执行项不是失败，也不能算通过。

| 阻塞项 | 解除条件 | 负责人/输入 |
|---|---|---|
| 候选源码范围未确认 | 确认主仓 `621bf678c58eae1e527d6dc5a105c561a4655130`、递归 Gitlink pins，以及是否纳入 `deploy/acceptance/ra02_runner.py` 的第 12 项断言和四份 RC04 结果文档；随后在独立干净快照验证。 | 仓库负责人确认候选范围。 |
| clean npm install 未完成 | 在 DNS/registry 可用环境对确认候选运行 `npm ci`，随后重跑前端 build 并记录锁文件与依赖安装证据。 | 依赖 registry 网络可用后执行。 |
| Docker daemon 不可访问 | 提供正式授权的隔离 Docker daemon/context，确保当前执行身份可读；不得改 socket 权限或切换未授权 daemon。 | 环境负责人提供授权执行环境。 |
| 隔离验收配置缺失 | 提供权限 0600 的私有 env、专用随机 JWT 凭据、专用 PG/Redis/存储资源和固定镜像 digest；不得把秘密放入仓库或日志。 | 验收环境负责人。 |
| 容器镜像未构建 | 在确认的干净候选上构建并运行验收镜像，记录 image ID/digest 与源码 SHA；前端 build 已在当前 HEAD 的干净 frontend tree 上通过，clean `npm ci` 仍待网络恢复。 | 候选冻结并获得授权 Docker daemon 后执行。 |
| RA02 未在 PostgreSQL 执行 | 在隔离 DB 应用迁移并执行 12 项断言，记录实际 SQLSTATE；新增第 12 项必须实跑。 | 授权 PG 到位后执行。 |
| RA04/05/06 与 FI01–FI06 的编号定义缺失 | 权威计划只将 RA04–06 合称 Celery，FI 场景也未编号；确认原始映射和各项预期后再执行，不擅自分配 ID。 | 需求/验收负责人确认语义。 |
| FI 注入与恢复未验证 | 计划列出 validating/rendering/publishing、发布后 DB 提交失败、重复投递/reconcile、撤权等维度；代码中未找到可定位目标 Job/阶段的 acceptance 注入器。补齐并审查隔离注入机制后逐项实跑。 | 门禁执行器与环境就绪后。 |
| 浏览器 E2E 未达 34/34 | 当前脚本有条件跳过 ZIP 下载断言，且未断言 fresh/existing-ready、ZIP SHA 对比、幂等无重复发布、错误轮询和撤权下载。先固定断言/测试数据，再在当前候选和真实隔离服务运行三视口 E2E。历史结果为 31/34。 | Playwright 环境与获批测试 fixture 就绪后。 |
| 当前交付链未重跑 | 真实运行报告 HTML/PDF、M0/M1/ZIP、JWT 下载与撤权、对象存储范围和恢复场景；旧运行不能替代。 | corpus 授权与隔离存储就绪后。 |
| 安全签核与当前回滚状态未知 | 由独立审阅者复核 seccomp syscall 规则变化与容器能力边界；本次 run 后验证 flags 关闭、进程停止、专用资源保留。 | 安全负责人和本次验收执行者。 |
| 历史证据原始日志含 JWT 字段 | 两份原始日志权限已设为 `0600`，内容未改以保留历史 artifact-index 摘要；对审阅/外发使用 `evidence/rc04-core/redacted-history/*.redacted.txt` 中已验证无 JWT 形态值的副本，并由安全负责人确认凭据失效/处置策略。 | 证据负责人确认凭据处置及访问策略。 |

历史 Run 的 `rollback/flags.txt` 保存 `READS=true`、`WRITES=true`、`PDF=true`。由于当前 Docker 权限拒绝，不能推断该历史运行的容器仍在或已经停止，也不能确认任何当前持久化 flags。重新获得授权前，不要执行停止、清理或卷操作。

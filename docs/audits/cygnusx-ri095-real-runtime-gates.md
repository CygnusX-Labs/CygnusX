# RI095 真实运行准入门禁

本轮只授予 VERIFIED_CODE / PASS_ISOLATED。PASS_RUNTIME 与 PASS_E2E 均未授予；所有业务写开关保持默认关闭，不探测默认／生产 DSN。

| Gate | 状态 | 已有隔离证据 | 授权后必须补齐 |
|---|---|---|---|
| PG 迁移／FK／CHECK／并发 | BLOCKED | SQLite 真实追加迁移与冻结触发器 | 显式专用临时 PG 数据库，升级旧表、FK 反例、唯一源并发创建、冻结触发器、旧 Task Report 兼容 |
| Celery／Broker | BLOCKED | queued 持久提交与 dispatch 替换；Worker／reconcile 已接代码 | 专用 broker／worker，commit→broker 不确定、重复投递、强杀 publishing、中断恢复、有限重试与 advisory lock |
| 私有存储／FileRegistry | BLOCKED | 实际本地临时文件、注册、SHA 回读、篡改拒绝 | 授权私有存储身份、配额、对象回读、撤权／生命周期变化与下载 |
| 渲染工具链 | BLOCKED | 固定 HTML 模板、BioReportAdapter 静态边界、既有 PDF 转换器本地回归、PDF 失败保留 HTML | Worker 实际镜像 digest、受信 release、字体、Pandoc／Typst／BioReport／Quarto 版本及同源 HTML／PDF 比对；本地 ../bioreport HEAD 不替代证明 |
| JWT／浏览器／下载 | BLOCKED | ASGI 替换 JWT 验证函数、真实 SQLite／文件；jsdom 交互 | 真实人类 JWT、API Key 拒绝、当前项目撤权／停用、1920／768／390 Chromium、焦点／键盘／sandbox、HTML／PDF／ZIP 下载 SHA |
| RA01–RA15／BR01–BR02 | BLOCKED | 未改变前序运行准入结论 | 复用 docs/audits/cygnusx-project-delivery-runtime-acceptance.md 的逐项运行验收，不把 Mock 结果升级为真实验收 |

## 可重跑的隔离检查

`UV_CACHE_DIR=/tmp/cygnusx-ri095-uv uv run --frozen pytest tests/unit/test_project_report_selection.py tests/unit/test_project_delivery.py tests/unit/test_claim_provenance_ri10.py -q`

`UV_CACHE_DIR=/tmp/cygnusx-ri095-uv uv run --frozen python scripts/check_migrations.py`

`cd frontend && npx vitest run src/components/__tests__/ProjectScientificSummary.test.ts src/components/__tests__/ProjectResearchDelivery.test.ts src/components/__tests__/ClaimEvidencePanel.test.ts && npx vue-tsc --noEmit && npm run build`

完整本轮命令／退出码／JUnit 见 evidence/ri095-project-report-phase1-4/，阶段边界见 docs/implementation/cygnusx-ri095-project-scientific-report-phase1-4.md。

## 授权前停止点

不得连接默认 PG／Broker／存储，不得执行共享或生产迁移，不得启动真实报告 Worker／科研计算／下载，不得开放 project_report_write_enabled、project_report_pdf_enabled 或原导出／分析写门禁，不得部署或提交推送。独立授权的 disposable 环境必须先确认用途与清理边界，再执行真实验收。失败时保持旧报告、快照、M0／M1 和文件，不自动删除证据。

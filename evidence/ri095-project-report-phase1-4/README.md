# RI095 隔离验收证据

本目录不含凭据。baseline.json / baseline-sha256.json 是起点；final-sha256.json 为最终相关源码指纹，compatibility.json 验证旧审计渲染器、ReportSnapshot 与 EvidenceManifest 契约源码未变。

- backend-tests.log / backend-tests.exit / final-unit-junit.xml：相关后端 133 passed。
- final-m1.log / final-m1.exit：最终版本去重、M1 历史脚本兼容修正复验，11 passed。
- frontend-tests.log / frontend-tests.exit：三个相关组件 16 passed（jsdom）。
- frontend-build.log / frontend-build.exit：npm run build 通过，含 vue-tsc -b；存在 bundle 大小提示。
- mypy.log / mypy.exit：14 个相关文件无错误；final-mypy.log 复验 M1 服务。
- ruff.log / ruff.exit：有界 Ruff 通过。
- migrations.log / migrations.exit：静态迁移拓扑连通、唯一 head；不是业务库迁移。

后端命令范围：uv run --frozen pytest tests/unit/test_project_report_selection.py tests/unit/test_project_delivery.py tests/unit/test_project_delivery_stabilization.py tests/unit/test_project_summary_prototype.py tests/unit/test_claim_provenance_ri10.py tests/unit/test_report_service.py tests/unit/test_report_versions.py tests/unit/test_report_snapshot.py tests/unit/test_reproducible_report_phase1.py tests/unit/test_report_pdf_and_bioreport_phase2.py -q。

前端命令范围：npx vitest run src/components/__tests__/ProjectScientificSummary.test.ts src/components/__tests__/ProjectResearchDelivery.test.ts src/components/__tests__/ClaimEvidencePanel.test.ts；npx vue-tsc --noEmit；npm run build。

ASGI 身份验证函数、队列投递被替换，SQLite／实际临时 TSV／HTML／ZIP 属隔离证据。没有真实 PG／Broker／Worker／私有存储／JWT／Chromium 验收，不授予 PASS_RUNTIME 或 PASS_E2E。没有运行全仓提交门禁，没有 commit／push／部署或业务库迁移。

# RI06–RI09 验证命令

均使用既有依赖；没有安装/升级、真实下载、计算或生产迁移。

```sh
.venv/bin/pytest tests/unit/test_project_delivery.py tests/unit/test_research_delivery_phase4.py tests/unit/test_lifecycle_report_delivery.py tests/unit/test_report_delivery_phase2.py tests/unit/test_execution_evidence_ri13.py tests/unit/test_agent_tools_phase2.py tests/unit/test_mcp_dual_surface_parity.py tests/unit/test_execution_evidence_projection.py -q -m 'not quarantine' --junitxml=evidence/project-delivery-ri06-ri09/combined-tests.xml
.venv/bin/pytest tests/unit/test_project_delivery.py -q --junitxml=evidence/project-delivery-ri06-ri09/project-tests.xml
.venv/bin/pytest tests/integration/test_project_delivery_postgres.py -q
.venv/bin/python scripts/check_migrations.py
.venv/bin/alembic heads
```

业务26项及相关回归129项均PASS_ISOLATED；PG用例未设置专用DSN，1 skipped按BLOCKED处理。项目锁保护的实际8并发验证、PG trigger及真实broker/Worker没有运行。SQLite迁移实际执行于临时fixture，不替代PG。

```sh
.venv/bin/ruff check src/cygnusx/application/schemas/project_delivery.py src/cygnusx/application/services/project_delivery_service.py src/cygnusx/infrastructure/database/models/project_export.py src/cygnusx/infrastructure/celery_app/tasks/project_exports.py src/cygnusx/domain/project_delivery_archive.py src/cygnusx/api/v1/research_delivery.py src/cygnusx/core/config.py src/cygnusx/application/schemas/agent_tools.py src/cygnusx/application/services/agent_tool_gateway.py src/cygnusx/application/services/research_provenance_service.py src/cygnusx/application/services/project_service.py src/cygnusx/infrastructure/database/models/__init__.py src/cygnusx/infrastructure/celery_app/celery.py alembic/versions/projectdelivery01_project_exports.py tests/unit/test_project_delivery.py tests/integration/test_project_delivery_postgres.py
.venv/bin/mypy src/cygnusx/application/schemas/project_delivery.py src/cygnusx/application/services/project_delivery_service.py src/cygnusx/infrastructure/database/models/project_export.py src/cygnusx/infrastructure/celery_app/tasks/project_exports.py src/cygnusx/domain/project_delivery_archive.py src/cygnusx/api/v1/research_delivery.py
```

原8源文件比较使用baseline目录下全部src Python文件作为同一mypy选择范围；基线为每个文件追加`--shadow-file original_path baseline/original_path`，当前不加shadow。比较忽略行号但保留完整诊断及数量：6→6，新增0。原ProjectService的6条dict泛型诊断未修复。

```sh
cd frontend
npx vitest run src/components/__tests__/ProjectResearchDelivery.test.ts src/views/__tests__/ProjectDetailResearchContext.test.ts
npx vue-tsc --noEmit
npm run build
npx vitest run
```

前端针对性9项PASS_ISOLATED；类型/构建PASS_CODE，构建退出码保存在frontend-build-result.json。全量574项中567通过、7失败，3文件失败：agent-teams-room-send、deep-thinking-stream、live-stream-render；不能标全量PASS。

全仓诊断也实际执行：`.venv/bin/ruff check src/ tests/ --output-format=json`、`.venv/bin/mypy src/cygnusx/`。观测288条Ruff及1022条mypy错误，日志保留，未进行无关重构。`git diff --check`通过。

浏览器探针：`node --input-type=module -e 'import.meta.resolve("playwright-core")'`，模块不可用，因此未跑浏览器或窄屏E2E。人工复核步骤见实施报告§7。测试线程使用仓库inline_file_capture，ASGI认证使用JWT验证替身，不能计作真实线程/JWT/broker运行。

真实环境测试没有默认读取生产DSN。未来仅由负责人显式提供以project_export_test开头的数据库给PG opt-in测试；该用例在随机schema执行迁移并清理，不能对生产运行。

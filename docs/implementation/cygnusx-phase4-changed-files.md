# Phase4 变更归属清单

只比较已记录 baseline SHA 的文本源文件，加上本轮明确创建的文件；未记录基线的其他文件不推断为本轮创建。共享 dirty 文件只归属增量。证据/日志、dist 为本地忽略产物。

| 路径 | 本轮归属 |
|---|---|
| `ARCHITECTURE_DESIGN/CygnusX_dataset_architecture.md` | 既有工作树上的增量 |
| `ARCHITECTURE_DESIGN/CygnusX_report_architecture.md` | 既有工作树上的增量 |
| `ARCHITECTURE_DESIGN/CygnusX_research_delivery_architecture.md` | 新增 |
| `ARCHITECTURE_DESIGN/README.md` | 既有工作树上的增量 |
| `alembic/versions/bioopsphase4_research_evidence.py` | 新增 |
| `docs/adr/phase4-execution-evidence-report-contract.md` | 新增 |
| `docs/audits/cygnusx-runtime-provenance-manifest.json` | 既有工作树上的增量 |
| `docs/contracts/cygnusx-provenance-v1.schema.json` | 新增 |
| `docs/contracts/cygnusx-research-delivery-v1.md` | 新增 |
| `docs/implementation/cygnusx-phase4-changed-files.md` | 新增 |
| `docs/implementation/cygnusx-phase4-provenance-report-delivery-implementation.md` | 新增 |
| `docs/runbooks/cygnusx-delivery-reconciliation.md` | 新增 |
| `frontend/src/api/researchDelivery.ts` | 新增 |
| `frontend/src/components/ResearchDeliveryChain.vue` | 新增 |
| `frontend/src/components/research/__tests__/ResearchDeliveryChain.test.ts` | 新增 |
| `frontend/src/views/ProjectDetailView.vue` | 既有工作树上的增量 |
| `pipelines/CountsDEGFlow/report/counts.qmd` | 新增 |
| `pipelines/CountsDEGFlow/snakefile` | 既有工作树上的增量（未记录 SHA 基线） |
| `src/cygnusx/api/v1/research_delivery.py` | 新增 |
| `src/cygnusx/api/v1/router.py` | 既有工作树上的增量 |
| `src/cygnusx/application/schemas/agent_tools.py` | 既有工作树上的增量 |
| `src/cygnusx/application/schemas/report_snapshot.py` | 既有工作树上的增量 |
| `src/cygnusx/application/schemas/research_delivery.py` | 新增 |
| `src/cygnusx/application/services/agent_service.py` | 既有工作树上的增量 |
| `src/cygnusx/application/services/agent_tool_gateway.py` | 既有工作树上的增量 |
| `src/cygnusx/application/services/bioreport_adapter.py` | 既有工作树上的增量 |
| `src/cygnusx/application/services/dataset_analysis_service.py` | 既有工作树上的增量 |
| `src/cygnusx/application/services/report_audit_renderer.py` | 既有工作树上的增量 |
| `src/cygnusx/application/services/report_service.py` | 既有工作树上的增量 |
| `src/cygnusx/application/services/report_snapshot_builder.py` | 既有工作树上的增量 |
| `src/cygnusx/application/services/report_snapshot_sources.py` | 既有工作树上的增量 |
| `src/cygnusx/application/services/reproducible_report_service.py` | 既有工作树上的增量 |
| `src/cygnusx/application/services/research_execution_binding.py` | 新增 |
| `src/cygnusx/application/services/research_provenance_service.py` | 新增 |
| `src/cygnusx/application/services/scientific_report_job.py` | 新增 |
| `src/cygnusx/application/services/task_service.py` | 既有工作树上的增量 |
| `src/cygnusx/core/config.py` | 既有工作树上的增量 |
| `src/cygnusx/infrastructure/celery_app/tasks/analysis.py` | 既有工作树上的增量 |
| `src/cygnusx/infrastructure/celery_app/tasks/datasets.py` | 既有工作树上的增量 |
| `src/cygnusx/infrastructure/celery_app/tasks/reports.py` | 既有工作树上的增量 |
| `src/cygnusx/infrastructure/database/models/__init__.py` | 既有工作树上的增量 |
| `src/cygnusx/infrastructure/database/models/dataset.py` | 既有工作树上的增量 |
| `src/cygnusx/infrastructure/database/models/report.py` | 既有工作树上的增量 |
| `src/cygnusx/infrastructure/database/models/result_observation.py` | 新增 |
| `src/cygnusx/infrastructure/database/repositories/report_repository.py` | 既有工作树上的增量 |
| `src/cygnusx/infrastructure/mcp/presets.py` | 既有工作树上的增量 |
| `tests/unit/test_research_delivery_phase4.py` | 新增 |

# 本轮隔离验证命令

以下均未运行真实下载或科研计算。完整输出见同目录日志。

```bash
.venv/bin/pytest tests/unit/test_dataset_gateway_phase3.py tests/unit/test_dataset_geo_validation.py tests/unit/test_dataset_import_handoff.py tests/unit/test_dataset_phase3.py tests/unit/test_dataset_phase3_review.py tests/unit/test_agent_tools_phase2.py tests/unit/test_phase0b_confirmation.py tests/unit/test_research_delivery_phase4.py tests/unit/test_research_plan_phase5.py tests/unit/test_research_plan_gateway_phase5.py tests/unit/test_research_plan_storage_phase5.py tests/unit/test_research_claim_artifact_phase5.py tests/unit/test_report_snapshot.py tests/unit/test_reproducible_report_phase1.py tests/unit/test_report_delivery_phase2.py tests/unit/test_report_pdf_and_bioreport_phase2.py tests/unit/test_download_service.py tests/unit/domain/test_flow_submission_validator.py tests/unit/test_flow_validation_parity.py tests/unit/test_flow_contract_drift.py tests/unit/test_research_treasure_phase1.py tests/integration/test_reproducible_report_isolated.py -q
.venv/bin/pytest tests/unit/test_research_benchmark_phase5.py tests/unit/test_research_science_phase5.py tests/unit/test_fixed_flow_tools_api.py tests/unit/tools/test_fixed_flow_bridge.py -q
.venv/bin/pytest tests/unit/test_agent_tools_phase2.py::test_dynamic_mcp_registry_bridge_and_gateway_share_contract -q
.venv/bin/pytest tests/unit/test_mcp_budget_and_pagination.py tests/unit/test_mcp_builder_invoke_gate.py -q
.venv/bin/python scripts/check_migrations.py
.venv/bin/python evidence/lifecycle-audit-2026-10-16/static-probes.py
.venv/bin/python evidence/lifecycle-audit-2026-10-16/package-probes.py
cd frontend
npx vitest run src/components/research src/components/report src/composables/__tests__/useReproducibleReport.test.ts src/views/__tests__/ProjectDetailResearchContext.test.ts
npx vue-tsc --noEmit
cd ../pipelines/Treasure-Seeking_Mouse
npm test
node --test functions/seqout-chat/tests/validateSearchQuery.test.ts
node functions/seqout-chat/tests/validateSearchQuery.test.ts
```

Socket探针只连接本机PG/Redis/Docker端点、不做认证；全部errno=1。浏览器仅尝试启动并关闭、没有访问业务页面。

# Phase5 变更文件索引

基线 HEAD：`51011118535f782f5282f638b4a54649c79bf6d6`；当前逻辑变更尚未提交。只列当前本轮文件，不包含运行证据及原始 dirty 文件。

| 文件 | 类型 |
|---|---|
| `"docs/info/26.10.15/CygnusX_Phase5_Phase 5 \345\256\236\346\226\275\344\273\273\345\212\241\344\271\246.md"` | 新增 |
| `ARCHITECTURE_DESIGN/CygnusX_research_plan_architecture.md` | 新增 |
| `ARCHITECTURE_DESIGN/README.md` | 修改 |
| `alembic/versions/bioopsphase5_research_plans.py` | 新增 |
| `benchmarks/research_agent/v1/baselines.json` | 新增 |
| `benchmarks/research_agent/v1/cases/discovery_01.json` | 新增 |
| `benchmarks/research_agent/v1/cases/discovery_02.json` | 新增 |
| `benchmarks/research_agent/v1/cases/discovery_03.json` | 新增 |
| `benchmarks/research_agent/v1/cases/discovery_04.json` | 新增 |
| `benchmarks/research_agent/v1/cases/planning_01.json` | 新增 |
| `benchmarks/research_agent/v1/cases/planning_02.json` | 新增 |
| `benchmarks/research_agent/v1/cases/planning_03.json` | 新增 |
| `benchmarks/research_agent/v1/cases/planning_04.json` | 新增 |
| `benchmarks/research_agent/v1/cases/safety_01.json` | 新增 |
| `benchmarks/research_agent/v1/cases/safety_02.json` | 新增 |
| `benchmarks/research_agent/v1/cases/safety_03.json` | 新增 |
| `benchmarks/research_agent/v1/cases/safety_04.json` | 新增 |
| `benchmarks/research_agent/v1/evaluation_protocol.md` | 新增 |
| `docs/adr/phase5-governed-research-agent-orchestration.md` | 新增 |
| `docs/audits/cygnusx-phase5-acceptance.md` | 新增 |
| `docs/audits/cygnusx-phase5-changes.md` | 新增 |
| `docs/audits/cygnusx-phase5-entry-gates.md` | 新增 |
| `docs/audits/cygnusx-phase5-implementation-report.md` | 新增 |
| `docs/contracts/cygnusx-research-artifact-cell-v1.schema.json` | 新增 |
| `docs/contracts/cygnusx-research-claim-input-v1.schema.json` | 新增 |
| `docs/contracts/cygnusx-research-claim-v1.schema.json` | 新增 |
| `docs/contracts/cygnusx-research-plan-input-v1.schema.json` | 新增 |
| `docs/contracts/cygnusx-research-plan-v1.md` | 新增 |
| `docs/contracts/cygnusx-research-plan-v1.schema.json` | 新增 |
| `docs/runbooks/cygnusx-phase5-rollback.md` | 新增 |
| `frontend/src/api/researchPlans.ts` | 新增 |
| `frontend/src/components/ResearchPlanWorkbench.vue` | 新增 |
| `frontend/src/components/research/__tests__/ResearchPlanWorkbench.test.ts` | 新增 |
| `frontend/src/views/ProjectDetailView.vue` | 修改 |
| `frontend/src/views/__tests__/ProjectDetailResearchContext.test.ts` | 新增 |
| `scripts/evaluate_research_benchmark.py` | 新增 |
| `scripts/export_research_plan_contracts.py` | 新增 |
| `src/cygnusx/api/v1/research_claims.py` | 新增 |
| `src/cygnusx/api/v1/research_plans.py` | 新增 |
| `src/cygnusx/api/v1/router.py` | 修改 |
| `src/cygnusx/application/schemas/agent_tools.py` | 修改 |
| `src/cygnusx/application/schemas/research_claims.py` | 新增 |
| `src/cygnusx/application/schemas/research_plan.py` | 新增 |
| `src/cygnusx/application/services/agent_service.py` | 修改 |
| `src/cygnusx/application/services/agent_tool_gateway.py` | 修改 |
| `src/cygnusx/application/services/research_claim_service.py` | 新增 |
| `src/cygnusx/application/services/research_plan_service.py` | 新增 |
| `src/cygnusx/application/services/tool_bridge_service.py` | 修改 |
| `src/cygnusx/core/config.py` | 修改 |
| `src/cygnusx/domain/research/__init__.py` | 新增 |
| `src/cygnusx/domain/research/benchmark.py` | 新增 |
| `src/cygnusx/domain/research/plan_state.py` | 新增 |
| `src/cygnusx/domain/research/scientific_validation.py` | 新增 |
| `src/cygnusx/infrastructure/database/models/__init__.py` | 修改 |
| `src/cygnusx/infrastructure/database/models/research_plan.py` | 新增 |
| `src/cygnusx/infrastructure/mcp/presets.py` | 修改 |
| `tests/unit/test_research_benchmark_phase5.py` | 新增 |
| `tests/unit/test_research_claim_artifact_phase5.py` | 新增 |
| `tests/unit/test_research_plan_gateway_phase5.py` | 新增 |
| `tests/unit/test_research_plan_phase5.py` | 新增 |
| `tests/unit/test_research_plan_storage_phase5.py` | 新增 |
| `tests/unit/test_research_science_phase5.py` | 新增 |

新增结果分析：`benchmarks/research_agent/v1/contract_results_analysis.md`。

## 保留的既有改动

`.env.example`、`Protocol/FlowFrame`、`pipelines/ATACFlow`、`pipelines/RNAFlow`、`pipelines/Treasure-Seeking_Mouse`、`pipelines/tools` 及 `docs/info/26.10.15/` 不纳入本次提交。锁文件未修改。

## 运行证据

`evidence/phase5/` 为本地运行证据，按工作协议不提交。验收需保存 baseline、socket probes、测试日志与 exit、benchmark-contract-03 的 raw JSONL/CSV/summary/manifest/source_snapshot。归档者应核验 manifest 内源码哈希；这些是合成契约证据，不证明真实科研运行。

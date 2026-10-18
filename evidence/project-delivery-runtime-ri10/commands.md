# 本轮可重复验证与证据说明

所有命令使用既有依赖。未安装/升级、启动真实Worker/Broker、连接生产、下载分析、部署或执行生产迁移。

## 基线及运行资格

git branch --show-current / rev-parse HEAD / status --short / diff --no-ext-diff / submodule status记录在baseline.json、status.txt、diff.patch和submodules.txt。仅检查PROJECT_EXPORT_TEST_DATABASE_URL是否存在及测试库前缀，不打印DSN、不使用生产DATABASE_URL。

```sh
.venv/bin/pytest tests/unit/test_project_delivery.py tests/unit/test_research_delivery_phase4.py tests/unit/test_lifecycle_report_delivery.py tests/unit/test_execution_evidence_ri13.py tests/unit/test_research_claim_artifact_phase5.py -q -m 'not quarantine' --junitxml=evidence/project-delivery-runtime-ri10/tests/baseline.xml
.venv/bin/pytest tests/integration/test_project_delivery_postgres.py -q
.venv/bin/python scripts/check_migrations.py
```

基线105项通过；PG 1 skipped为BLOCKED。没有真实PG版本/迁移/业务API并发或实际表状态证明。项目导出相关表状态仍NOT_QUERIED，不把包版本或迁移文件存在当成部署完成。

浏览器先解析playwright-core（不可用），再实际启动Chromium headless about:blank、关闭背景联网并使用独立/tmp profile，退出46。再提供可写临时XDG_RUNTIME_DIR仍为同一Snap只读/run/user/1000错误。见browser/*.log；没有截图或浏览器E2E。

## 最终隔离测试

```sh
.venv/bin/pytest tests/unit/test_claim_provenance_ri10.py tests/unit/test_project_summary_prototype.py tests/unit/test_project_delivery_stabilization.py tests/unit/test_project_delivery.py tests/unit/test_research_claim_artifact_phase5.py tests/unit/test_report_snapshot.py tests/unit/test_execution_evidence_ri13.py tests/unit/test_agent_tools_phase2.py tests/unit/test_research_delivery_phase4.py tests/unit/test_lifecycle_report_delivery.py tests/unit/test_report_delivery_phase2.py tests/unit/test_execution_evidence_projection.py tests/unit/test_mcp_dual_surface_parity.py -q -m 'not quarantine' --junitxml=evidence/project-delivery-runtime-ri10/tests/combined.xml
```

215通过、13文件，其中新Claim 11、Summary原型5、稳定化5。合成SQLite/真实临时字节、ASGI身份替身、Broker替身和inline_file_capture不算真实运行。实施过程中新增Snapshot测试起初因fixture错误地把报告投影缺口纳入Observation摘要而失败，随后改为与实际reconcile一致的include_reports=False，并断言原Provenance确实查回同一观察；没有放宽生产关联校验凑测试。

```sh
.venv/bin/mypy src/cygnusx/application/schemas/claim_provenance.py src/cygnusx/application/services/research_claim_service.py src/cygnusx/application/services/report_audit_renderer.py src/cygnusx/api/v1/research_claims.py src/cygnusx/api/v1/research_delivery.py src/cygnusx/application/services/project_delivery_service.py
.venv/bin/ruff check src/cygnusx/application/schemas/claim_provenance.py src/cygnusx/application/services/research_claim_service.py src/cygnusx/application/services/report_audit_renderer.py src/cygnusx/api/v1/research_claims.py src/cygnusx/api/v1/research_delivery.py src/cygnusx/application/services/project_delivery_service.py tests/unit/test_claim_provenance_ri10.py tests/unit/test_project_summary_prototype.py tests/unit/test_project_delivery_stabilization.py
```

原6源文件同范围baseline/current mypy使用baseline-files逐文件--shadow-file比较，均0诊断。Schema与model_json_schema逐项相等，原research_claims.py字节不变，flags源码门禁为false。旧HTML对同一个synthetic_rna冻结快照加载基线/当前renderer逐字节比较，前后SHA相同，见quality/legacy-renderer-compatibility.json。

```sh
cd frontend
npx vitest run src/components/__tests__/ClaimEvidencePanel.test.ts src/components/__tests__/ProjectResearchDelivery.test.ts src/views/__tests__/ProjectDetailResearchContext.test.ts
npx vue-tsc --noEmit
npm run build
```

3文件13项通过，类型及构建退出0。构建由脚本捕获完整日志及退出码，没有升级锁文件。实际浏览器和全仓测试未通过/未重跑时不宣布全仓PASS；上一轮已有全仓静态及聊天/协作室测试失败不在本轮清除。

git diff --check通过。最终文件摘要、四项交付、PASS_CODE/PASS_ISOLATED与全部运行BLOCKED汇总见checks.json。diff与证据可能包含既有工作区上下文，应留在本地，不直接提交或公开。

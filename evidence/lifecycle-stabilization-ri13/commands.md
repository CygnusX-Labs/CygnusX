# 可重复验证命令

使用已存在的 `.venv` 和 node_modules，没有安装或升级依赖。源码安全门禁未开启。所有测试均离线或SQLite/原服务函数/执行器与队列替身，不能视为真实运行验收。

```sh
.venv/bin/pytest tests/unit/test_execution_evidence_ri13.py tests/unit/test_execution_evidence_projection.py tests/unit/test_lifecycle_stabilization.py tests/unit/test_execution_definition_contract.py tests/unit/test_report_snapshot.py tests/unit/test_research_delivery_phase4.py tests/unit/test_lifecycle_report_delivery.py tests/unit/test_report_delivery_phase2.py tests/unit/domain/test_flow_submission_validator.py tests/unit/tools/test_analysis_flow_tool.py -q --junitxml=evidence/lifecycle-stabilization-ri13/targeted.xml
```

```sh
.venv/bin/pytest tests/unit/test_dataset_gateway_phase3.py tests/unit/test_dataset_geo_validation.py tests/unit/test_dataset_import_handoff.py tests/unit/test_dataset_phase3.py tests/unit/test_dataset_phase3_review.py tests/unit/test_phase0b_confirmation.py tests/unit/test_research_plan_phase5.py tests/unit/test_research_plan_gateway_phase5.py tests/unit/test_research_plan_storage_phase5.py tests/unit/test_reproducible_report_phase1.py tests/unit/test_report_repository.py tests/unit/test_report_service.py tests/unit/test_report_versions.py tests/unit/test_flow_validation_parity.py tests/unit/test_flow_contract_drift.py tests/unit/test_download_registration_contract.py tests/unit/test_download_transport_contract.py tests/unit/test_lifecycle_download_security.py tests/unit/test_download_service.py tests/unit/test_agent_tools_phase2.py tests/unit/test_mcp_dual_surface_parity.py tests/integration/test_reproducible_report_isolated.py -q -m 'not quarantine' --junitxml=evidence/lifecycle-stabilization-ri13/regression.xml
```

```sh
.venv/bin/ruff check src/cygnusx/application/schemas/execution_evidence.py src/cygnusx/application/services/execution_evidence_service.py src/cygnusx/application/services/research_execution_binding.py src/cygnusx/application/services/task_service.py src/cygnusx/application/services/report_snapshot_builder.py src/cygnusx/application/services/research_provenance_service.py src/cygnusx/infrastructure/celery_app/tasks/analysis.py tests/unit/test_execution_evidence_ri13.py tests/unit/test_execution_evidence_projection.py tests/unit/test_lifecycle_stabilization.py
.venv/bin/mypy src/cygnusx/application/schemas/execution_evidence.py src/cygnusx/application/services/execution_evidence_service.py src/cygnusx/application/services/research_execution_binding.py
```

前者选择范围PASS；后者3个源文件PASS。包含原TaskService/Worker/Provenance/Snapshot的7文件mypy原始结果仍FAIL，有8条继承诊断；同范围原快照通过`--shadow-file original_path evidence/lifecycle-stabilization-ri13/baseline-files/original_path`逐文件覆盖后有9条。比较忽略行号、保留文件+诊断全文和数量，没有新增诊断。详见mypy-baseline.log/mypy-current.log/quality-baseline.json。

Ruff起始源文件通过`ruff check --stdin-filename 原路径 -`输入对应baseline-files字节核验，保留ruff-baseline.json。当前全部10个源码/测试文件通过。没有声称全仓静态PASS。

```sh
.venv/bin/python evidence/lifecycle-stabilization-ri13/verify-evidence.py

git diff --check
```

该证据核对脚本校验日志、Schema、旧v1源码摘要、写门禁、8项交付文件和质量诊断；它不替代测试命令，也不运行任何下载、迁移或分析。

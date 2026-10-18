# RI01–RI04 验证命令

环境：使用仓库已有 .venv 和 node_modules；未安装或升级依赖。最终 uv run 因默认缓存只读失败，以下 Python 选择范围实际用 `.venv/bin/` 复跑成功。命令中的测试不是运行验收。

## targeted-tests.log

```sh
.venv/bin/pytest tests/unit/test_lifecycle_report_delivery.py tests/unit/test_execution_definition_contract.py tests/unit/test_lifecycle_download_security.py tests/unit/test_download_registration_contract.py tests/unit/test_download_transport_contract.py tests/unit/test_download_service.py tests/unit/test_agent_tools_phase2.py tests/unit/test_report_delivery_phase2.py tests/unit/test_report_pdf_and_bioreport_phase2.py -q --junitxml=evidence/lifecycle-ri01-ri04/targeted.xml
```

## static-checks.log

```sh
.venv/bin/ruff check src/cygnusx/domain/download_security.py src/cygnusx/infrastructure/download/policy.py src/cygnusx/application/schemas/download.py src/cygnusx/application/schemas/download_capability.py src/cygnusx/application/schemas/execution_definition.py src/cygnusx/application/schemas/report_delivery.py src/cygnusx/tools/download/config.py src/cygnusx/infrastructure/celery_app/tasks/download.py src/cygnusx/application/services/download_service.py src/cygnusx/application/services/report_service.py src/cygnusx/application/services/research_delivery_service.py src/cygnusx/api/v1/downloads.py tests/unit/test_lifecycle_download_security.py tests/unit/test_lifecycle_report_delivery.py tests/unit/test_execution_definition_contract.py tests/unit/test_download_registration_contract.py tests/unit/test_download_service.py tests/unit/test_report_service.py
```

## mypy.log

```sh
.venv/bin/mypy src/cygnusx/domain/download_security.py src/cygnusx/infrastructure/download/policy.py src/cygnusx/application/schemas/download.py src/cygnusx/application/schemas/download_capability.py src/cygnusx/application/schemas/execution_definition.py src/cygnusx/application/schemas/report_delivery.py src/cygnusx/tools/download/config.py src/cygnusx/infrastructure/celery_app/tasks/download.py src/cygnusx/application/services/download_service.py src/cygnusx/application/services/report_service.py src/cygnusx/application/services/research_delivery_service.py src/cygnusx/api/v1/downloads.py
```

## 相关回归（270 passed）

```sh
.venv/bin/pytest tests/unit/test_dataset_gateway_phase3.py tests/unit/test_dataset_geo_validation.py tests/unit/test_dataset_import_handoff.py tests/unit/test_dataset_phase3.py tests/unit/test_dataset_phase3_review.py tests/unit/test_phase0b_confirmation.py tests/unit/test_research_delivery_phase4.py tests/unit/test_research_plan_phase5.py tests/unit/test_research_plan_gateway_phase5.py tests/unit/test_research_plan_storage_phase5.py tests/unit/test_research_claim_artifact_phase5.py tests/unit/test_report_snapshot.py tests/unit/test_reproducible_report_phase1.py tests/unit/test_report_repository.py tests/unit/test_report_service.py tests/unit/test_report_versions.py tests/unit/domain/test_flow_submission_validator.py tests/unit/test_flow_validation_parity.py tests/unit/test_flow_contract_drift.py tests/unit/test_research_treasure_phase1.py tests/unit/test_fixed_flow_tools_api.py tests/unit/tools/test_fixed_flow_bridge.py tests/integration/test_reproducible_report_isolated.py -q -m 'not quarantine'
```

## 前端（43 passed / 10 files）与 Node

```sh
cd frontend
npx vitest run src/components/research src/views/__tests__/DownloadsCapabilities.test.ts
npx vue-tsc --noEmit
npm run build
```

```sh
cd pipelines/Treasure-Seeking_Mouse
npm test
```

## 迁移链与共享工作区全仓静态检查

```sh
.venv/bin/python scripts/check_migrations.py
.venv/bin/ruff check src/ tests/
.venv/bin/mypy src/cygnusx/
```

全仓静态检查失败，详见 full-ruff.log/full-mypy.log，不能据局部检查宣布全仓通过。未运行迁移。


# IAT-R3 / G3-E2 / S6-S7 Handoff

Date: 2026-10-18 (Asia/Shanghai)

Run scope: current workspace only; isolated unit tests and read-only host inspection.
Overall: `PARTIAL_ISOLATED / RUNTIME_BLOCKED`; S6 `NOT_READY`; S7 `NOT_STARTED`.

## 1. Change and actual runtime scope

- R3 deterministic Provider remains test/acceptance-only and default-off. Legacy and LangGraph complete the tool-result round through the actual chat stream route and SSE serializer over in-process ASGI. No deployed API, Node service, PostgreSQL, Redis, or browser was involved.
- G3 receipt claims now bind Task/attempt/execution/epoch, policy, environment, binary digest, artifact manifest, supervisor identity, nonce, RX counters, cgroup, quota and cleanup observations. The Worker validates HTTP outputs before `FileRegistry` registration and consumes the nonce in the caller's SQL transaction. A Worker-side mTLS control client now implements the adapter protocol, but it is not wired into task lifecycle and no matching Supervisor server exists; HTTP/HTTPS transfer still fails closed before downloader launch.
- The read-only host probe found no effective/bounding capabilities, no writable cgroup root, no visible `cgroup.kill`, and ext4 `/` and `/tmp` mounts without XFS project-quota options. It did not test kernel hook semantics or attempt privileged setup.
- A source audit found the reusable Prepare source for G3's first HTTP scope: processed `DatasetIngestion` persists owner/project, normalized source request, `max_bytes`, confirmation ID and Task IDs. No G3 resolver consumes it; Redis approval consumption, execution epoch and restart-safe shared byte accounting are not durably bound to that Task. Multi-Task raw imports cannot each reuse the full `max_bytes`. See [`G3 admission/budget source audit`](../g3-e2-20261018/admission-source-audit.md).
- A fresh read-only preflight rerun reconfirmed `CAP_SYS_ADMIN`, `CAP_NET_ADMIN`, `CAP_BPF`, and `CAP_PERFMON` are absent from effective/bounding sets, cgroup root is not writable, `cgroup.kill` is unavailable, and writable filesystems lack XFS project-quota support. Raw output: [`host-preflight-rerun-20261018.json`](../g3-e2-20261018/host-preflight-rerun-20261018.json). No privileged setup was attempted.
- `dispatch_download` now describes its success log as `transport_call_returned`, not broker publication confirmation.

## 2. Matrix and R2 reconciliation

The dated matrix has 78 parent cases and 42 child assertions (120 rows total). Generated counts: 44 `BLOCKED`, 13 `NOT_TESTED`, 3 `PASS_E2E`, 27 `PASS_ISOLATED`, and 33 `PASS_RUNTIME`; all 63 passing rows have evidence paths. Parent counts are 27 `BLOCKED`, 13 `NOT_TESTED`, 3 `PASS_E2E`, 4 `PASS_ISOLATED`, and 31 `PASS_RUNTIME`; child counts are 17 `BLOCKED`, 23 `PASS_ISOLATED`, and 2 `PASS_RUNTIME`. Child assertions do not promote parent status. The isolated `dataset.prepare_import` service and Gateway tests cover synthetic-candidate idempotency, invocation/session linkage, and no-Task/no-file side effects only; real PostgreSQL AG-09 remains `NOT_TESTED`. REC-04's injected stale arrivals still allow the oldest backlog through the next 100-item batch; REC-06's SQLite fault injection proves no dispatch/attempt consumption before commit and one later retry only. REC-07 also has an isolated cooldown assertion; its real Beat/Broker parent remains `BLOCKED`. FR-09 has an isolated SQLite/FileRegistry child covering FAILED/CANCELLED retry binding, while its historical runtime parent remains backed only by the 2026-10-17 evidence. FR-07's isolated work-directory and rollback-marker assertions do not prove concurrent PostgreSQL uniqueness. The canceled Research Agent snapshot, same-generation SSE protocol, disconnect-continuation producer, and same-process cancel notification have separate `PASS_ISOLATED` child assertions. The SSE protocol child proves request identity, durable event sequence/replay, generation continuing after its replay consumer closes, and client cursor dedupe under SQLite/in-process tests. Producer ownership remains process-local and process-restart recovery is not implemented; the real browser/PostgreSQL reconnect assertion remains `BLOCKED`. The mTLS evidence client, savepoint-notification, frontend stale A1 SSE rejection, and PG-11 application-guard assertions are also `PASS_ISOLATED`; the original G3-01, MQ-05, BR-01, AG-01, and PG-11 parents remain `BLOCKED`.

The summary was regenerated with `UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/summarize_acceptance_matrix.py docs/info/26.10.18/CygnusX_Integration_Test_Matrix_2026-10-18.csv --strict-evidence`; all passing rows have existing evidence paths. Exact counts and the strict evidence result are in the generated summary.

An additional R2 evidence-scope review found that the retained Node artifact contains a Gateway audit row for `downloads.describe_capabilities` and a Redis replay key, but no Node request/response payload or execution-blocked result. The full `AG-01` parent is now `BLOCKED`; `AG-01.R2-GATEWAY-AUDIT` preserves only the directly evidenced runtime assertion. The R2 report's `dataset.discover`/GEO DatasetCard claim has no corresponding raw invocation or response; `BR-02` and `AG-12` remain `NOT_TESTED`. See [`R2 runtime evidence closure`](../../docs/implementation/cygnusx-iat-r2-runtime-evidence-closure.md).

The PG-11 source audit records the Worker claim CAS, cancellation row lock, repository terminal-state guard, file-registration cancellation guard, and recovery policy as isolated application evidence. Database grants and direct-SQL prevention remain unverified; the parent remains `BLOCKED`. See [`PG-11 audit`](../../docs/implementation/cygnusx-iat-r3-pg11-source-audit.md).

A current combined isolated regression ran the Gateway, Import Prepare, S4 reliability (including REC-04/06 and FR-09 retry registration), receipt/nonce publication, and mTLS client suites together: 165 passed with 1 existing Pydantic warning. The mTLS client covers 18 cases, including rejection across 10 identity bindings. The focused frontend regression now has 60 tests and `vue-tsc` passes, including a component check that stale A1 SSE frames cannot enter A2. Raw outputs: [`current-cross-boundary-regression.txt`](current-cross-boundary-regression.txt), [`frontend-unit-regression.txt`](frontend-unit-regression.txt). These checks do not exercise PostgreSQL, Redis, Broker, deployed Node/API, browser UI, or a host Supervisor.

R2 MQ-02 was narrowed after reading its harness: the real PG row survived an injected dispatch exception and a corrected idempotency query found one matching Task, but the harness replaced `dispatch_download` with a function that always raises. Real `send_task` returned an ID without evidence of consumer receipt. The PG/idempotency child remains `PASS_RUNTIME`; the broker-unavailable parent is now `BLOCKED` until tested against an isolated real broker. Details: [`MQ-02 reconciliation`](../../docs/implementation/cygnusx-iat-r3-mq02-evidence-reconciliation.md).

## 3. R3 result

The focused Runtime/provider suite reports 32 passed and 1 existing Pydantic deprecation warning. Added tests confirm historical and out-of-order tool results do not suppress a new deterministic tool call, and that only a matching current-turn result is echoed. This is `PASS_ISOLATED`. The Research Agent API/service suite now reports 37 passed; it covers partial snapshot persistence, same-generation cursor replay without a second Agent invocation, request fingerprint conflict rejection, cancellation from a separate service instance in the same process, and generation continuation after the SSE replay consumer closes. The combined current R3 regression (`test_treasure_native_access.py`, `test_download_s5b_consumption.py`, and `test_deterministic_test_provider.py`) reports 69 passed and 1 Pydantic deprecation warning. The SSE parser suite reports 6 passed. See [`sse-reconnect-isolated.txt`](sse-reconnect-isolated.txt). Focused front-end research components/adapters/download-contract/project-context tests previously reported 60 passed, with `vue-tsc --noEmit` exit 0; the current full frontend suite passes 597 tests across 88 files, and `vue-tsc --noEmit` passes; see [`frontend-unit-regression.txt`](frontend-unit-regression.txt). Updated assertions cover the current token/API/reference contracts and ensure test mounts are cleaned up. None of this is Chromium evidence. The real Node callback, PostgreSQL/Redis facts, real-PostgreSQL Import Prepare persistence, React/Vue product flow, permissions/revocation, browser reconnect, screenshots and browser trace were not run. A separate SQLite unit assertion verifies synthetic-candidate Import Prepare idempotency, no Task/file side effects, and that confirmation does not bypass the execute gate; it does not pass AG-09. See [`ag09-prepare-isolated.txt`](ag09-prepare-isolated.txt). The environment probe and absence of authorized service identities are recorded in [`environment.md`](environment.md).

## 4. G3 result

The latest receipt/registration/preflight suite reports 99 passed and the mTLS client suite reports 18 passed, each with the existing Pydantic warning. This proves model, signature, SQLite nonce, rejection, publication-gate and client request-contract behavior only. The evidence client also binds a retrieved context to the original execution request, but it is not wired into Worker lifecycle and has no matching deployed Supervisor server. The nine original HTTP cases all skipped. No Linux supervisor, unique egress, atomic network budget, filesystem block/inode quota, stop/lease enforcement, real PG migration or PostgreSQL concurrency evidence exists. HTTP certification is not granted.

## 5. S4 and remaining assertions

The current S4-A/S4-B0 focused suite reports 34 passed and 1 existing warning using SQLite fixtures and mocked transport. It includes a nested savepoint rollback assertion and REC-07 cooldown coverage against the configured 600-second Beat interval and ten-minute stale threshold. Neither proves PostgreSQL or real Beat/Broker behavior. This does not close PG-01/10/11, broker recovery MQ-02/03/05/06/07, real Beat REC-04/06/07, or the original FR-09 runtime assertion. Existing R2 evidence remains historical and only applies to its stated scope.

## 6. Gates and resource boundary

Source defaults remain closed for `DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED`, `WRITE_RUNTIME_ACCEPTED`, Agent download/analysis writes, and Treasure Agent write tools. No production containers, broker, queue, database, provider credential or download source was contacted. No migration was applied; migration topology was checked read-only and remains one head. Evidence of the source flags and run-start hashes is in [`baseline.txt`](baseline.txt).

## 7. S6/S7 decision

| S6 condition | Status |
|---|---|
| S4 real reliability assertions | `PARTIAL / BLOCKED` |
| S5 real Node, two-engine and product workflow | `PARTIAL_ISOLATED / BLOCKED` |
| G3 original nine HTTP assertions | `BLOCKED` |
| Same-Task human JWT approval and one-time budget binding | `BLOCKED` - existing tool confirmation is Redis-backed and consumed before Task creation; it does not durably bind the resulting Task to a Supervisor admission and budget. |
| Server-side environment × protocol × caller admission/revocation | `BLOCKED` - extend processed `DatasetIngestion` as the authority; persist consumed approval, same-Task epoch fencing and a shared restart-safe byte budget. No G3 resolver exists yet; see `evidence/g3-e2-20261018/admission-source-audit.md`. |

S6 is `NOT_READY`. S7 is `NOT_STARTED`; it requires a separately admitted protocol and a complete source-to-Prepare-to-human-approval-to-transfer-to-FileRecord/DatasetVersion-to-FlowFrame/BioReport chain. No real-data or scientific-analysis claim is made.

## 8. Rollback, cleanup and retained evidence

No shared service/worker, execution scope, lease, applied migration, broker message or downloaded file was created by this pass. Unit tests use temporary SQLite fixtures, not a shared or production database. There is no runtime cleanup action or live execution to recover. Reverting code changes requires reviewing the dirty worktree and reverting only this task's specific patches; do not reset or restore the workspace wholesale. Keep logs and manifests because they document the boundary and test scope.

Evidence files and hashes are enumerated by [`manifest.json`](manifest.json) and verified by [`manifest.sha256`](manifest.sha256).

## Reproduction commands

All commands below completed with exit code 0. `UV_CACHE_DIR` points to a writable task-local cache because the default uv cache path is read-only in this workspace.

```bash
UV_CACHE_DIR=/tmp/uv-omic-hub uv run pytest tests/unit/test_download_s5b_consumption.py tests/unit/test_deterministic_test_provider.py -q -m unit  # 32 passed
UV_CACHE_DIR=/tmp/uv-omic-hub uv run pytest tests/unit/test_download_trusted_execution_contract.py tests/unit/test_download_execution_receipt.py tests/unit/test_download_execution_receipt_nonce.py tests/unit/test_download_registration_contract.py tests/unit/test_download_execution_boundary_probe.py tests/unit/test_download_supervisor_client.py -q -m unit  # 99 passed
UV_CACHE_DIR=/tmp/uv-omic-hub uv run pytest tests/unit/test_download_s4a_reliability.py tests/unit/test_download_s4b0_reliability.py -q -m unit  # 34 passed
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/test_treasure_native_access.py tests/unit/test_download_s5b_consumption.py tests/unit/test_deterministic_test_provider.py -q -m unit  # 69 passed
cd frontend && npm run build  # exit 0; Vite chunk-size warning
UV_CACHE_DIR=/tmp/uv-omic-hub uv run python scripts/check_download_execution_boundary.py --output evidence/g3-e2-20261018/host-preflight-current.json
cd frontend && ./node_modules/.bin/vitest run src/components/research/__tests__ src/components/research/adapters/__tests__ src/views/__tests__/DownloadsCapabilities.test.ts src/views/__tests__/DownloadsTransportContract.test.ts src/views/__tests__/ProjectDetailResearchContext.test.ts src/stores/__tests__/research-mode.test.ts
cd frontend && ./node_modules/.bin/vue-tsc --noEmit
```

The host probe is read-only. A repeat using the same output path must choose a new filename because the script uses exclusive creation; it never overwrites evidence.

The RI095 acceptance harness offline checks now pass: Ruff lint/format, Compose fail-closed configuration checks (eight rejection cases), Node syntax, download-worker task/Beat registry restriction, and evidence-index generation. The registry check confirms only six named report/export/download tasks route to `ri095_acceptance`, with only the three intended reconcile Beat entries; it uses a synthetic Celery app and is static evidence. Output: [`ri095-offline-checks.txt`](ri095-offline-checks.txt). This validates the local harness only; Docker daemon access is still denied, the dedicated RI095 env file is absent, and no runtime container, DB, Redis, Broker, Worker, Node callback, or browser workflow was started.

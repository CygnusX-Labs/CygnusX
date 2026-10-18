# CygnusX IAT R3 Runtime and UI Closure

Date: 2026-10-18

Status: `PARTIAL_ISOLATED / RUNTIME_BLOCKED`

## Result

R3 gained a deterministic test-only Provider that is assembled through `ProviderManager` and exercised through both Legacy and LangGraph Runtime paths. The test provider emits a declared tool call; the runtime invokes the normal gateway path and consumes the actual tool result on the next model round. The provider is default-off, restricted to `test`/`acceptance`, and rejected in production. This improves the isolated runtime evidence for AG-02/AG-03; it does not pass those parent acceptance cases.

The focused R3 runtime/provider regression now completes with 32 passed and 1 existing warning. Added coverage confirms that historical tool results from an earlier user turn and out-of-order results cannot suppress the current deterministic tool call; current-turn results are echoed only after a matching assistant tool call. Legacy and LangGraph each traverse the actual `/api/v1/chat/stream` route and SSE serializer using an in-process ASGI transport, then assert tool-result and terminal `done` events. At interpreter shutdown the test process also emitted an OpenTelemetry/Loguru closed-stream logging error after pytest had reported exit 0; this is retained in the raw log and is not counted as an assertion failure. The G3 receipt publication tests are maintained in a separate log. These are isolated evidence: test configuration, database facade/doubles, and no real listening server. They do not establish production `ProviderManager` configuration, PostgreSQL, Redis, or a real browser workflow. Full R3 remains blocked.

## Changes and evidence

- `src/cygnusx/infrastructure/ai_provider/testing.py`: isolated scripted provider; no direct Gateway call and no fabricated gateway result.
- The deterministic provider now scopes tool-result consumption to matching assistant tool calls after the latest user message, avoiding stale or out-of-order result reuse.
- `src/cygnusx/infrastructure/ai_provider/openai_compatible.py`: default-off provider assembly restricted to test/acceptance.
- `src/cygnusx/core/config.py`: production configuration rejects enabling the deterministic provider.
- `tests/unit/test_download_s5b_consumption.py` and `tests/unit/test_deterministic_test_provider.py`: both Runtime paths through the ASGI `/chat/stream` route, tool-result second round, SSE terminal event, disabled-by-default and production rejection.
- Focused front-end research component/adapter/download-contract/project-context regression: 60 passed; `vue-tsc --noEmit` passed. The component suite includes A1-to-A2 session switching while an old SSE stream emits late `delta` and `end` frames; those frames do not contaminate A2. A subsequent full frontend run passed all 597 tests across 88 files, and `vue-tsc --noEmit` passed. It also corrected stale token-field expectations, AgentTeams API arity, workspace-reference IDs, and test DOM cleanup in the affected tests. Raw commands and output: [`frontend-unit-regression.txt`](../../evidence/iat-r3-20261018/frontend-unit-regression.txt). This remains isolated UI logic evidence, not the React/Vue/Node/FastAPI browser business workflow.
- Same-generation SSE resume is implemented at the isolated code level. `request_id` is bound to a request fingerprint and a partial unique key; normalized frames are appended to `chat_message_events`, emitted with monotonic SSE IDs, and replayed after `Last-Event-ID` without invoking a second generation. An in-process background producer uses its own DB session, so closing the SSE replay iterator does not stop generation; a focused regression confirms later frames can be resumed and Agent invocation stays singular. The Vue client retries with the same request ID/cursor and its parser drops covered IDs. Backend API/service tests report 37 passed; parser tests report 6 passed; `vue-tsc`, Ruff, mypy, and migration topology checks pass. Producer ownership and cancellation remain process-local; process restart recovery and cross-process cancellation are not implemented. Evidence: [`sse-reconnect-isolated.txt`](../../evidence/iat-r3-20261018/sse-reconnect-isolated.txt). This is `PASS_ISOLATED` only. PostgreSQL, deployed API, actual network interruption, Chromium, and the full React/Vue/Node product journey were not run; `BR-08.R3-RECONNECT-CURSOR` remains `BLOCKED`, with protocol implementation tracked separately as `BR-08.R3-RECONNECT-PROTOCOL`.
- The earlier full frontend run had 7 stale assertions across 3 files. Those assertions and a cross-test DOM leak have now been corrected; the current full run passes 88 files / 597 tests, with `vue-tsc --noEmit` passing. This remains unit-test evidence only.
- A separate cancellation bug was fixed: the Research Agent commits its final partial/terminal snapshot before cancellation propagates to `get_db()`, whose cancellation handler rolls back the request transaction. The cancellation assertion remains covered in the 35-test API/service suite and keeps its separate `PASS_ISOLATED` matrix row.
- Focused Runtime/provider run: [`r3-runtime-regression.txt`](../../evidence/iat-r3-20261018/r3-runtime-regression.txt) (32 passed, 1 existing warning; pytest exit code 0).
- G3 receipt-publication tests are kept separately at [`isolated-regression.txt`](../../evidence/g3-e2-20261018/isolated-regression.txt).
- Environment evidence and safety gates: [`environment.md`](../../evidence/iat-r3-20261018/environment.md).
- Run-start baseline, dirty-state hashes, submodule revisions, lock hashes, and migration head: [`baseline.txt`](../../evidence/iat-r3-20261018/baseline.txt).
- Current matrix (historical 2026-10-17 matrix remains unchanged): [`CygnusX_Integration_Test_Matrix_2026-10-18.csv`](../info/26.10.18/CygnusX_Integration_Test_Matrix_2026-10-18.csv).
- MQ-02 historical evidence correction: [`cygnusx-iat-r3-mq02-evidence-reconciliation.md`](cygnusx-iat-r3-mq02-evidence-reconciliation.md).
- R2 Node evidence scope correction: [`cygnusx-iat-r2-runtime-evidence-closure.md`](cygnusx-iat-r2-runtime-evidence-closure.md); the retained audit supports only the Gateway audit child, not full AG-01 or `dataset.discover`.
- PG-11 application-level status write audit: [`cygnusx-iat-r3-pg11-source-audit.md`](cygnusx-iat-r3-pg11-source-audit.md); PostgreSQL role and raw-SQL guarantees remain unverified.

## Still blocked

The current S4-A/S4-B0 local reliability regression completed with 34 passed and 1 existing Pydantic warning. It includes a savepoint rollback assertion and isolated REC-07 coverage that matches the configured 600-second Beat interval to the ten-minute recovery staleness threshold, rejects immediate/before-threshold redispatch, and allows one attempt after cooldown. It uses SQLite/service fixtures and mocked transport calls; it does not close PG-01/10/11, MQ-02/03/05/06/07, real Beat REC-04/06/07, or FR-09 runtime acceptance. MQ-02's historical parent conclusion was narrowed after the R2 harness review; see the reconciliation report.

The current environment has no authorized isolated API/SSE stack, PostgreSQL identity, Redis/Broker/Worker, or browser-ready product project. Docker socket access is denied; loopback bind returns `EPERM`; Chromium snap cannot start. The complete React/Vue flow, real API/SSE requests, PostgreSQL transactions, Redis/Broker recovery, worker execution, and screenshot/HAR/console evidence therefore remain untested. Current acceptance rows retain their recorded scope; isolated child rows are not promoted to parent pass. The reconnect protocol implementation passes isolated checks, while real browser/PG reconnect remains `BLOCKED` by missing authorized runtime services.

All live-write and download safety flags remain false. No real download, external scientific network call, shared/PostgreSQL database mutation, migration application, or queue operation was performed. Unit tests use disposable SQLite fixtures. See [`environment.md`](../../evidence/iat-r3-20261018/environment.md).

## Next acceptance run

Provide an authorized isolated environment with pinned app/worker image digests, dedicated PG/Redis/Broker/queue/volume, test-only credentials, a test project, browser access to the actual product, and cleanup ownership. Then repeat the full API/SSE and browser journey, the PG transaction/recovery matrix, and worker outage/recovery cases. Capture redacted response/event logs, DB assertions, broker/worker identity, screenshot/HAR/console, and exact environment/image manifest before changing any runtime acceptance flag.

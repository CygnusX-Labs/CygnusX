# IAT R3 / G3-E2 Environment Record

Date: 2026-10-18 (Asia/Shanghai)

## Baseline and access

- Repository: `/home/zj/zj_code_libarary/OmicHub`
- HEAD at inspection: `d9c92cf6ee1c1e8de902c2b897b93f60b4f00f33`
- Run-start baseline recorded 659 changed/untracked entries, tracked-diff hash `ff1cf2bfebb02bdc1d0335f4ace5be4a51984c5951ad1b99b54e992e9fdac469`, and status-manifest hash `d46d0e1dac028110555b19c04432235516248cc328b71282d5502c2e6bde4a69`. See [`baseline.txt`](baseline.txt) for submodule SHAs, lock hashes and migration head. This does not claim a clean checkout or image/source identity.
- Environment-name scan for TEST, S4B1, E2E, DATABASE, REDIS, DOCKER, and RI_ENV found no configured acceptance credentials.
- `docker info` could not access `/var/run/docker.sock` (operation not permitted). No containers or services were started.
- A local `127.0.0.1` TCP bind probe returned `EPERM`; no loopback test server was started.
- Chromium snap refused to start because snap confinement could not establish the required elevated permissions.
- No authorized isolated PostgreSQL, Redis, Broker, Worker, or listening product API/SSE environment was available or used. The unit suite does invoke the real `/api/v1/chat/stream` route in-process through ASGI transport.
- No real download, external scientific network access, shared/PostgreSQL database mutation, migration application, or queue operation was performed. Unit tests use disposable SQLite fixtures.
- `scripts/check_migrations.py` passes with one head (`dwnreceiptnonce01`). The new revision's PostgreSQL SQL was generated in isolation. Full-chain `alembic upgrade head --sql` currently fails before this revision while compiling a JSON literal in an earlier migration; no database was contacted or changed.
- Read-only Linux trusted-execution preflight: kernel `6.8.0-147-generic`, `CapEff=0`, `CapBnd=0`, `NoNewPrivs=1`, seccomp mode 2, cgroup v2 controllers visible but root not writable and `cgroup.kill` unavailable in this namespace. Probe output: [`host-preflight.txt`](../g3-e2-20261018/host-preflight.txt). These facts rule out installing the required supervisor controls from this process; no privileged operation was attempted.

## Current safety gates

- `DOWNLOAD_TRANSPORT_RUNTIME_ACCEPTED=False`
- `WRITE_RUNTIME_ACCEPTED=False`
- `agent_download_write_enabled=False`
- `agent_analysis_write_enabled=False`
- `treasure_agent_write_tools_enabled=False`

These are source/configuration observations. They are not substitutes for exercising the actual product API.

## Isolated checks

- G3 focused contract/receipt/nonce/registration/preflight regression: 78 passed, 1 pre-existing Pydantic deprecation warning. See `../g3-e2-20261018/isolated-regression.txt`.
- R3 focused runtime/provider regression: 29 passed, 1 pre-existing Pydantic deprecation warning. See `r3-runtime-regression.txt`.
- The R3 process emitted an OpenTelemetry/Loguru closed-stream logging error during interpreter shutdown after pytest reported exit 0. It is present in the raw log and is not counted as a test assertion failure.
- S4-A/S4-B0 local reliability regression: 29 passed, 1 pre-existing Pydantic deprecation warning. It uses SQLite and mocked transport, so no S4 runtime acceptance is inferred; see `s4-unit-regression.txt`.
- Trusted HTTP integration contract: 9 skipped with `NOT_TESTED: authorized OS supervisor and real HTTP driver unavailable`. See `../g3-e2-20261018/real-http-boundary.txt`.
- The unit tests use test provider configuration and database facades/doubles. The in-process route assertion is not a deployed API/SSE run and does not establish PostgreSQL concurrency, Redis/Broker recovery, browser workflow, or OS enforcement.

## Continuation recheck

- Re-ran the isolated R3 suite after tightening deterministic tool-result association: 32 passed, 1 existing Pydantic deprecation warning, pytest exit code 0. The post-exit OpenTelemetry/Loguru closed-stream message remains; see `r3-runtime-regression.txt`.
- Node is present (`v24.11.0`), but `frontend/node_modules/playwright` and `frontend/node_modules/@playwright` are absent. `chromium-browser --version` exits 1; the wrapper reports that Snap confinement cannot establish its required elevated permissions. No browser session or product server was started.
- `postgres` and `redis-server` executables are absent. This is a local executable check only; no service endpoints were probed.
- Re-ran G3 isolated contract/receipt/nonce/registration/preflight tests after adding the Worker-side mTLS client contract and response-size bound: 85 passed, 1 existing warning, pytest exit code 0. The earlier read-only host capability result remains the governing evidence; no privileged setup or service operation was attempted.
- Refreshed the read-only host probe after implementing the Worker-side client. The report now separately records `worker_control_client=IMPLEMENTED_UNVERIFIED`, `supervisor_server=NOT_IMPLEMENTED`, and `host_enforcement_runtime=NOT_IMPLEMENTED`; see `../g3-e2-20261018/host-preflight-continued.json`. This is a status correction only and does not certify runtime enforcement.
- Re-ran the S4-A/S4-B0 local suite after fixing nested-transaction notification handling: 30 passed, 1 existing Pydantic warning. The added assertion covers savepoint rollback preserving the outer transaction's dispatch notification; it remains SQLite-only evidence.
- Re-ran focused research UI/component/adapter/download-contract/project-context tests: 13 files, 59 tests passed; `vue-tsc --noEmit` exited 0. This does not supply a browser, product Node/FastAPI entry, or persistent PG/Redis evidence; see `frontend-unit-regression.txt`.

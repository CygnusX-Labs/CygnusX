# CygnusX Agent Runtime Acceptance Compass

Date: 2026-10-18

Scope: IAT R3 Agent/Download runtime closure and G3-E2 trusted HTTP execution.
Current position: `PARTIAL_ISOLATED / RUNTIME_BLOCKED` for R3; `PARTIAL_CODE / RUNTIME_BLOCKED` for G3-E2.

This is the navigation and decision document for the acceptance work. The architecture authority remains [`CygnusX_download_architecture.md`](../../ARCHITECTURE_DESIGN/CygnusX_download_architecture.md); this document records the current work and directs the next operator to evidence. A green isolated test is never promoted to a runtime or end-to-end pass by this compass.

## Where to look

- Broader download/S0-S5 progression and historical S5-C entry: [`download-compass.md`](download-compass.md).
- R3 Runtime/UI implementation and limits: [`cygnusx-iat-r3-runtime-ui-closure.md`](cygnusx-iat-r3-runtime-ui-closure.md).
- G3-E2 trusted execution and signed receipt status: [`cygnusx-g3-e2-trusted-http-runtime.md`](cygnusx-g3-e2-trusted-http-runtime.md).
- Current dated acceptance matrix: [`CygnusX_Integration_Test_Matrix_2026-10-18.csv`](../info/26.10.18/CygnusX_Integration_Test_Matrix_2026-10-18.csv). The 2026-10-17 matrix remains a historical snapshot.
- Unit run, static checks, environment record, matrix summary: [`evidence/iat-r3-20261018`](../../evidence/iat-r3-20261018/).
- Evidence and S6/S7 handoff record: [`handoff.md`](../../evidence/iat-r3-20261018/handoff.md).
- Evidence file hashes: [`manifest.sha256`](../../evidence/iat-r3-20261018/manifest.sha256).
- Real HTTP boundary run: [`real-http-boundary.txt`](../../evidence/g3-e2-20261018/real-http-boundary.txt).
- MQ-02 R2 evidence reconciliation: [`cygnusx-iat-r3-mq02-evidence-reconciliation.md`](cygnusx-iat-r3-mq02-evidence-reconciliation.md).
- R2 Node invocation scope correction: [`cygnusx-iat-r2-runtime-evidence-closure.md`](cygnusx-iat-r2-runtime-evidence-closure.md) and [`handoff.md`](../../evidence/iat-r3-20261018/handoff.md).
- PG-11 application status guard audit: [`cygnusx-iat-r3-pg11-source-audit.md`](cygnusx-iat-r3-pg11-source-audit.md).
- Earlier S3-E1 trusted boundary requirements: [`download-s3-e1-trusted-execution-boundary.md`](download-s3-e1-trusted-execution-boundary.md).
- Acceptance runbook and required scenario semantics: [`Download S3-E1 acceptance runbook`](../info/26.10.17/CygnusX_Integration_Acceptance_Test_Runbook_2026-10-17.md).

## Current compass

| Track | Implemented in this increment | Evidence | Current decision |
|---|---|---|---|
| R3 provider/runtime path | Default-off deterministic test Provider assembled through ProviderManager; Legacy and LangGraph traverse `/api/v1/chat/stream` in-process; isolated Import Prepare persistence and A1-to-A2 late-frame isolation pass. Research SSE uses an in-process background producer with an independent DB session; disconnecting replay does not cancel generation, and the same request UUID/fingerprint/event cursor resumes without a second Agent call. Producer ownership, cancellation, and crash recovery remain process-local/not implemented. | Runtime/provider: 32 passed; Research Agent API/service: 37 passed; SSE parser: 6 passed; `vue-tsc`, Ruff, mypy, and migration topology pass; [`sse-reconnect-isolated.txt`](../../evidence/iat-r3-20261018/sse-reconnect-isolated.txt) | Protocol and disconnect-continuation children `PASS_ISOLATED`; real PostgreSQL, process restart recovery, multi-process cancellation, Node, deployed API, network interruption and Chromium reconnect remain `BLOCKED`; full R3 remains `PARTIAL_ISOLATED / RUNTIME_BLOCKED` |
| G3 inode contract | Observation requires measured inode peak and rejects a measured value above limit | Unit contract tests pass | Contract only; no OS-level enforcement |
| G3 signed receipt and control client | Ed25519 publication gate binds execution and resource observations; Worker consumes the SQL nonce before FileRegistry registration; mTLS evidence retrieval checks the receipt context against the original execution request | Latest G3 contract/receipt/registration/preflight/client regression: 99 passed; separate evidence-context contract: 18 passed; existing Pydantic warnings | `PASS_ISOLATED` code only; no Supervisor server, Worker lifecycle wiring, OS enforcement, real PG migration, or runtime authentication |
| S4 file and prepare edges | Isolated tests cover unique download work directories, rollback-marker classification, and Import Prepare idempotency with zero Task/file side effects | [`ag09-prepare-isolated.txt`](../../evidence/iat-r3-20261018/ag09-prepare-isolated.txt), [`fr07-workdir-isolated.txt`](../../evidence/iat-r3-20261018/fr07-workdir-isolated.txt) | Child assertions only; AG-09 and FR-07 parents still require real PG/runtime evidence |
| S4 recovery transaction | Commit failure during a recovery scan does not dispatch or persist an attempt; a later scan retries the still-queued Task once | [`rec06-recovery-commit-failure.txt`](../../evidence/iat-r3-20261018/rec06-recovery-commit-failure.txt) | `PASS_ISOLATED` child only; PostgreSQL and real Beat/Broker behavior remain unverified |
| S4 recovery cooldown | A broker failure is not retried by immediate scans or before the ten-minute stale threshold; a later scan increments the recovery attempt once. The Beat schedule is configured at 600 seconds | [`rec07-cooldown-isolated.txt`](../../evidence/iat-r3-20261018/rec07-cooldown-isolated.txt) | `PASS_ISOLATED` child only; real Beat ticks and Broker outage/recovery remain unverified |
| S4 recovery fairness | Oldest queued backlog advances in the next 100-item scan after a batch of newer stale arrivals is added | [`rec04-backlog-fairness.txt`](../../evidence/iat-r3-20261018/rec04-backlog-fairness.txt) | `PASS_ISOLATED` child only; injected timestamps do not prove sustained production arrival fairness |
| S4 terminal retry and file ownership | FAILED/CANCELLED same-key requests remain attached to the original Task; a new key registers same-name retry output under a new Task and SHA/path | [`fr09-terminal-retry-isolated.txt`](../../evidence/iat-r3-20261018/fr09-terminal-retry-isolated.txt) | `PASS_ISOLATED` child; historical FR-09 runtime parent retains its original dated evidence |
| S4 MQ-02 | R2 harness covers real PG row persistence after an injected post-commit dispatch exception and a corrected idempotency query; actual disconnected-broker `send_task` returned an ID without consumer evidence | R2 harness/verdict reread; local dispatch log now labels a non-exception return as `transport_call_returned` | PG/idempotency child remains `PASS_RUNTIME`; broker-failure parent is `BLOCKED` pending real isolated broker-side fault injection |
| Real HTTP supervisor | Nine integration scenarios exist | All 9 skipped because authorized supervisor/driver unavailable | `BLOCKED` |
| Environment | Docker denied, loopback bind `EPERM`, Chromium snap cannot start; `CapEff=0`, cgroup root not writable, no `cgroup.kill`, ext4 has no project-quota mount option; no authorized isolated service credentials | [`environment.md`](../../evidence/iat-r3-20261018/environment.md) and [`host-preflight-current.json`](../../evidence/g3-e2-20261018/host-preflight-current.json) | Do not start services or touch live data from this environment |
| Safety switches | Download transport, Gateway write runtime, and Agent write settings remain closed | Source/config inspection | Preserve closed until isolated evidence is reviewed and release is separately authorized |

The matrix summary reports parent cases and child assertions separately; child status does not alter its parent. In particular, `AG-02`/`AG-03` remain blocked for full product runtime even though their deterministic-provider child assertions pass in isolation.

## S6/S7 handoff

| S6 prerequisite | Current disposition | Evidence or gap |
|---|---|---|
| S4 required transaction, message, recovery and file assertions | `PARTIAL / BLOCKED` | S4-A/S4-B0 isolated regression passes; PG and broker runtime scenarios remain open, including corrected MQ-02 parent |
| S5 Node, both Agent engines, authorization and product workflow | `PARTIAL_ISOLATED / BLOCKED` | Legacy/LangGraph route-path tests pass in-process; Node, PG/Redis identities, approval facts and Chromium product workflow are unavailable |
| G3 original nine scenarios and target-scope authentication | `BLOCKED` | Nine real HTTP scenarios skip; no Supervisor, hard network/RX or block/inode quota implementation |
| Human JWT approval bound to the same Task/source/budget/nonce/expiry | `NOT_REVALIDATED` | No current authorized runtime or same-Task execution evidence |
| Server-side environment × protocol × caller admission, expiry and revocation | `BLOCKED` | Server-owned admission/budget models and a strict isolated resolver now exist, but DatasetImport/Task lifecycle and Supervisor do not issue or consume them yet. Approval consumption is still Redis-only, PostgreSQL concurrency and runtime revocation are unverified. The bounded processed-import path is the reuse candidate; raw multi-Task imports cannot each receive the full budget. See [source audit](../../evidence/g3-e2-20261018/admission-source-audit.md). |

S6 is **NOT_READY** because all five conditions must hold together. S7 is **NOT_STARTED** and blocked on S6 plus a dataset whose provenance and transfer protocol are within the eventual certification scope. No fixture or report UI is presented as a real scientific download/analysis chain.

## Execution order

1. **Establish an authorized test environment.** Record operator authorization, Environment ID, repository/submodule/image digests, cleanup owner, and disposable data scope. Require dedicated PostgreSQL, Redis, Broker, queue, volume, and test credentials. Do not mount production data or expose `docker.sock` to the worker.
2. **Re-run environment gates.** Confirm loopback/IPC, API/SSE reachability, DB identity, Broker/Worker identity, and that the target images match the reviewed source. Update current matrix evidence only after capturing outputs.
3. **Close R3 product path.** Run the declared tool call through the real configured ProviderManager, product API/SSE, Legacy and LangGraph routes as applicable, then complete the actual React presentation and Vue workflow in Chromium. Capture redacted requests/events, screenshot, HAR, console, and DB-side assertions. Do not use the deterministic provider as proof of a real provider integration.
4. **Run S4 recovery matrix.** Exercise PG concurrency and terminal-state protection, Broker lost-ack and API crash, worker absence/restart, long outage, and Beat recovery with isolated identities. Capture task transitions, attempt/cooldown timestamps, and duplicate-execution checks.
5. **Finish G3-E2 before any transport acceptance.** Implement a real OS supervisor with enforced egress policy, hard byte/inode receive quotas, process-group/cgroup stop and cleanup, and measured resource reporting. The Worker publication check and durable nonce consumption are wired for HTTP artifact registration, but no Supervisor currently creates the signed execution context. This run's host preflight shows `CapEff=0`, no writable cgroup root, and no accessible `cgroup.kill`; apply the migration in an authorized isolated PG, prove PostgreSQL concurrency, and run all nine HTTP boundary scenarios with measured limits and no-publication outcomes on failure.
6. **Review before opening any runtime flag.** The release owner reviews all evidence, risk scope, cleanup, and rollback. Keep all gates false until that review is complete; this document grants no authorization to enable them.

## Status vocabulary

- `PASS_ISOLATED`: code-level or unit evidence with fakes/test configuration; no claim about deployed services.
- `PASS_RUNTIME`: observed against the authorized isolated runtime with service identities and logs.
- `PASS_E2E`: complete user-visible workflow with API/browser/database evidence.
- `BLOCKED`: a required prerequisite is absent or the current environment cannot perform the test.
- `NOT_TESTED`: not attempted, and no current evidence justifies a stronger status.

Do not convert `SKIPPED` to a pass. A blocked test can be rerun only after its missing prerequisite is available; attach new dated evidence and preserve the older matrix as history.

## Safe local continuation

Without the isolated runtime, continue only with reviewable code work and offline unit/static checks. No real network download, product write flow, migration, shared database, live queue, or release-flag change is part of this acceptance pass. The current focused regression command and its result are preserved in the evidence directory. The main unresolved engineering gap is a concrete Supervisor and PostgreSQL runtime validation; environment access is a separate operational prerequisite.

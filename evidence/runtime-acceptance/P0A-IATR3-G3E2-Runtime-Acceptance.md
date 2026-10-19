# P0A-IATR3-G3E2 Runtime Acceptance

- Run ID: `20261018-local`
- Environment: disposable Docker Compose project `cygnusx-ri095-acceptance`; no production database, credentials, network, or data used.
- Current Git commit: `54718c476816c0045e433d45148c0140784ebbce`.
- Evidence: [20261018-local](20261018-local/)

## Results

| Gate | Result | Evidence | Conclusion |
|---|---|---|---|
| P0-A | `PASS_ISOLATED` | [p0a-isolated.log](20261018-local/p0a-isolated.log) | 82 isolated tests passed, matching the raw log collection count. Real PG acceptance was not completed. |
| G3-E2 static | `PASS_STATIC` | [static-checks.log](20261018-local/static-checks.log), [g3-preflight.log](20261018-local/g3-preflight.log) | Compose safety checks passed; required host cgroup/quota prerequisites are absent. |
| G3-E2 nine HTTP scenarios | `BLOCKED` | [g3-http.log](20261018-local/g3-http.log) | All 9 scenarios were skipped as `NOT_TESTED`; no real boundary case ran. |
| IAT-R3 | `STALE_EVIDENCE / BLOCKED` | [runtime-start.log](20261018-local/runtime-start.log), [compose.log](20261018-local/compose.log) | PG/Redis identity checks passed, then migration failed at `c1d2e3f4b5a6` because `mcp_versions` does not exist. The supplied app/frontend images are tagged `d9c92cf6ee1c`, different from current source HEAD, so this runtime result cannot certify current source. |
| Browser E2E | `BLOCKED` | [runtime-start.log](20261018-local/runtime-start.log) | Blocked before API/frontend startup; no Chromium business trace, screenshot, console/network log, or artifact evidence exists. |

## Runtime observations

- PostgreSQL 14.23 and Redis 7.4.11 started on the isolated internal network.
- Database identity was `project_export_test_ri095` / `ri095_acceptance`.
- All protected write flags were `false`, including agent analysis/download writes and research delivery writes.
- `make check-migrations` passed static graph checks, but the runtime image's upgrade exposed `ALTER TABLE mcp_versions` before that table exists in its migration path.
- The isolated stack was stopped after the failed run; no production resources were touched.

## Final acceptance decision

Overall result: `PARTIAL`; release decision: `NO-GO`.

- P0-A real runtime pass: **No**. Isolated contracts pass; real PG transaction/budget/concurrency acceptance is unverified.
- G3-E2 nine scenarios: **No**. 9/9 were `NOT_TESTED`/blocked.
- IAT-R3 end-to-end: **No**. Blocked before a usable API/Worker/Node stack, and the image evidence is stale relative to current HEAD.
- Browser E2E: **No**.
- Remove `NO-GO`: **No**. Keep download write, agent write, and `worker_paths_verified` closed.

Historical PASS records were not inherited as current results.

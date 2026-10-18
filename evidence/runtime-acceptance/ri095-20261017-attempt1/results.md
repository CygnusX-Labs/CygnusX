# RI09.5 Runtime + E2E Acceptance — Run ri095-20261017-attempt1

Executed: 2026-10-17 (Asia/Shanghai). Source commit d9c92cf6ee1c, branch feat/research-agent-phase5.
Authorization: local disposable Docker (user zj, docker group). No production .env/data/DB touched.
Dev stack (cygnusx-web/worker/beat/nginx) left untouched; acceptance ran in project cygnusx-ri095-acceptance.

## Headline
- PASS_RUNTIME achieved for PG/migration, constraints, concurrency, JWT/auth, storage, report HTML, export ZIP.
- Two real defects found: (1) fresh-DB Alembic ordering bug (FAIL, minimal fix verified);
  (2) tmpfs compose bug (FAIL, minimal fix verified).
- Browser E2E: BLOCKED (Chromium sandbox unavailable on host).
- PDF: BLOCKED (Pandoc/Typst/fc-list missing in worker image). Object storage: BLOCKED (no test bucket).
- RA04/05/06: PARTIAL — source docs give no per-gate definitions; Celery behaviour observed and recorded.

## Static
| Gate | Level | Status | Evidence |
|---|---|---|---|
| S0 offline config protection (6 rejections + unapproved var) | PASS_STATIC | PASS | preflight/s0-static-checks.log |
| Compose isolated topology | PASS_STATIC | PASS | preflight/ |

## Runtime gates
| Gate | Status | Summary | Evidence |
|---|---|---|---|
| RA01 migration | FAIL then PASS_RUNTIME | Fresh-DB upgrade failed (mcp_versions ALTER before CREATE); minimal fix (reparent c1d2e3f4b5a6 under h6i7j8k9l1m3) makes fresh DB reach head projectreport01 (111 revs) | ra01/attempt1-freshfail, ra01/attempt2-fixed |
| RA02 constraints | PASS_RUNTIME | 12 assertions on real PG14 with exact SQLSTATE (23514 x4, 23503, P0001 x2, 23505, 00000 x2) | ra02/ra02-results.txt |
| RA03 concurrency/lock | PASS_RUNTIME (partial scope) | 8 concurrent real API creates -> single job (99323137), attempt_count=1; advisory lock verified | ra03/ |
| RA04/05/06 Celery | PARTIAL | Real broker/worker/beat; duplicate dispatch idempotent; Beat reconcile recovered stale queued job. No per-gate original definitions; no per-stage fault injection | ra04/, ra06/ |
| Report HTML | PASS_RUNTIME | Worker generated 6635-byte HTML, SHA matches DB+disk+download; Chinese + provenance present | report/ |
| PDF | BLOCKED | Pandoc/Typst/fc-list MISSING in worker image | report/versions.log |
| Private storage | PASS_RUNTIME (local scope) | Atomic publish->readback SHA integrity; owner scoping | storage/ |
| Object storage | BLOCKED | No authorized test bucket | - |
| JWT | PASS_RUNTIME | API key rejected (401) on JWT paths; cross-owner 404; deactivation recheck 401 | auth/ |
| M0->Report->M1->ZIP | PASS_RUNTIME (mechanics) | Export ZIP 7372 B, SHA matches DB; repo verify_archive OK; partial declared | chain/ |
| Browser 1920/768/390 | BLOCKED | apparmor_restrict_unprivileged_userns=1 -> no usable Chromium sandbox | browser/ |

## FAILures and fixes (recorded, not overwritten)
1. compose.yml tmpfs flow-sequence mis-parse (`gid=10001` treated as mount path). Fix: quote the scalar.
2. alembic c1d2e3f4b5a6 ordered before h6i7j8k9l1m3 on fresh DB. Fix: down_revision reparent.

## BLOCKED reasons
- Corpus: no approved completed-task artifact corpus exists in the repo, so corpus-dependent
  business acceptance (old-model RA01 data, storage drift/loss, M0/M1 baseline compare) is BLOCKED.
- PDF: missing renderer binaries in the worker image.
- Object storage: no signed-off test bucket.
- Browser: host AppArmor blocks unprivileged userns; README forbids --no-sandbox workaround.

## Rollback
- Flags set false, project stopped (containers Exited 0), volumes + PG/Redis/private-storage retained.
- No down -v, no downgrade, no prune. Dev stack untouched.

## Not claimed
This is NOT full RI09.5 closure: browser E2E, PDF, object storage, and corpus-backed business
acceptance remain BLOCKED. Docker working does not complete the acceptance.

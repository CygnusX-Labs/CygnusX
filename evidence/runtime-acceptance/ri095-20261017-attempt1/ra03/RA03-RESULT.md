# RA03 — real business API concurrency + advisory lock: PASS_RUNTIME (partial scope)
Real PostgreSQL 14.23, real FastAPI + real JWT (owner A), real Celery worker.

## 8 concurrent real business API requests
Endpoint: POST /api/v1/projects/{id}/scientific-summary (real report-create use case)
8 concurrent requests, distinct request_key, identical source_manifest_job_id.
Evidence: ra03-race-8concurrent.txt, ra03-job-final.txt, job-count.txt

| observation | result |
|---|---|
| HTTP status | all 8 -> 200 OK |
| returned job id | identical across all 8: 99323137-44f8-4bea-ad62-b65ad10d3962 |
| status seen in responses | queued / validating / publishing / ready (live progression) |
| jobs created in DB | 1 (unique (user_id,project_id,source_digest) enforced) |
| attempt_count | 1 (single execution, no duplicate publish) |
| final status | ready, html_sha256 set |

This demonstrates the unique constraint + idempotent create converging concurrent
racers to a single job, with no duplicate publication.

## Advisory lock primitive
task_lock_key -> pg_try_advisory_lock on real PG; reentrant in-session, releases cleanly
(advisory-lock-mech.txt): try1=true try2=true locks=1 unlock1=true unlock2=true locks_after=0
The report task path acquires this lock around run_project_report and unlocks in finally
(project_reports.py:59-72). Real lock usage observed while the worker ran the job.

## Not covered / BLOCKED
- RA03 "8 different source versions" variant and project deletion/deactivation retention:
  no approved completed-task corpus with multiple source versions exists (see corpus BLOCKED).
- RA03 exact per-request timing window at HTTP layer: window_seconds=1 (sufficient to prove
  concurrency, not a precise contention measurement).

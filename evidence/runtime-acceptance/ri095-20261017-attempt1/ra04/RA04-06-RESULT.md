# RA04/RA05/RA06 — Celery Broker/Worker/Beat + recovery
NOTE: The three source documents do not give per-gate definitions for RA04/05/06
(only "RA04–06 Celery" lumped). Per the agent prompt these must be located verbatim;
no per-gate definition exists, so this section reports the observable Celery
behaviour without claiming exact original-gate coverage. Scope: PARTIAL / documented.

## Infrastructure (real, verified)
- Broker: Redis DB1, queue `ri095_acceptance` (redis keys _kombu.binding.ri095_acceptance).
- Worker registry limited to exactly 4 tasks (worker-registry.txt):
  project_reports.{generate_project_report,reconcile_project_reports},
  project_exports.{generate_project_export,reconcile_project_exports}
- Beat schedule limited to project-report-reconcile + project-export-reconcile;
  Beat fires them every 60s (beat log), worker consumes them.
- Real dispatch round trip: send_task -> broker -> worker "received" ->
  "started" -> "finished" with real task ids (ra04/dispatch1.txt, worker-dispatch-roundtrip.txt).

## Fail-closed admission (PASS)
With ACCEPTANCE_WRITES=false, generate_project_report raised DependencyUnavailableError
("Project scientific report generation is not admitted") — the write gate is enforced
inside the task before any DB work.

## Duplicate dispatch idempotency (PASS — dedup capability, per-benchmark)
3 duplicate dispatches of an already-ready job all executed but left
attempt_count=1, status=ready, identical html_sha256 (duplicate-dispatch-result.txt).
No duplicate publication.

## Beat reconcile recovery (PASS)
A job forced to stale `queued` (updated_at 10 min old) was picked up by
reconcile_project_reports and re-dispatched: {'dispatched': 1}, then re-executed
and recorded failure with error_code=invalid_evidence (recovered-state.txt).
This exercises the queued-recovery path with a real broker/worker/beat.

## BLOCKED within RA04-06
- Precise per-stage fault injection (interrupt during validating/rendering/publishing)
  has no implemented test mechanism (publish-success/submit-failure injection point
  not implemented per README §RA04-06). Not faked with random kill.
- Report→export reconcile coupling for the export pipeline not exercised end-to-end
  (export job f61dafa4 stayed queued; export generation requires corpus-backed
  artifacts — see corpus BLOCKED).

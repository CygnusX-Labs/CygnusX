# G3 Admission and Budget Source Audit

Date: 2026-10-18
Scope: read-only source inspection in the current worktree; no database or service was contacted.

## Finding

The G3 `ExecutionBoundaryRequest` requires `task_id`, `owner_id`, `attempt_id`, `execution_id`, `execution_epoch`, `admission_ref`, and `budget_ref` in [`trusted_execution.py`](../../src/cygnusx/infrastructure/download/trusted_execution.py). The contract assigns `admission_ref` to resolve identity, approval, request digest, and HTTP destination policy, and `budget_ref` to resolve durable shared quota. No production call site currently consumes either reference.

There is a reusable persisted Prepare source: [`DatasetIngestionModel`](../../src/cygnusx/infrastructure/database/models/dataset.py) records owner/project, normalized request and source snapshot, `max_bytes`, confirmation ID, request digest, Task IDs, and lifecycle state. [`DatasetImportService.prepare/execute`](../../src/cygnusx/application/services/dataset_import_service.py) creates that record, requires human JWT approval through `ToolConfirmationService`, rechecks source and quota, consumes the one-time Redis confirmation, then durably advances the ingestion through `SUBMITTING` to `QUEUED` while linking Task IDs. Processed imports create one `direct_link` Task; raw imports may create several SRA Tasks. The single-task processed path is the existing Prepare/Approval flow to extend for the first bounded HTTP scope.

The new [`DownloadExecutionAdmissionModel`](../../src/cygnusx/infrastructure/database/models/download_execution.py) and [`DownloadExecutionBudgetModel`](../../src/cygnusx/infrastructure/database/models/download_execution.py), migration `dwnadmission01`, and [`download_execution_admission.py`](../../src/cygnusx/infrastructure/database/repositories/download_execution_admission.py) now provide a server-owned representation. Isolated tests cover binding, both-reference resolution, one-time consumption/epoch increment, revocation, caller mismatch, and conditional budget reservation. They do not prove the tables are applied to PostgreSQL or that `DatasetImportService`/Supervisor uses them.

The new resolver is not yet wired into the G3 start path. Redis still owns the approval `CONSUMED` transition and its approval record has a bounded TTL; the ingestion row does not yet durably record approval-consumed time/actor. The generic [`TaskModel`](../../src/cygnusx/infrastructure/database/models/task.py) still has no attempt ID or execution fencing state; those facts are represented only in the new admission row until lifecycle wiring is completed. Raw multi-Task imports cannot safely reuse one `max_bytes` value independently for every Task. The receipt nonce model remains separate and stores only replay nonces.

The ordinary [`/downloads` endpoint`](../../src/cygnusx/api/v1/downloads.py) consumes a Redis tool confirmation before calling [`DownloadService.submit`](../../src/cygnusx/application/services/download_service.py) and does not create a durable Task-bound admission. Agent `downloads.prepare` proposals allow accession-based SRA requests and report unknown byte estimates; they are not a bounded HTTP budget source. `DownloadService.submit` remains fail-closed at `require_download_runtime` before side effects.

## Consequence

Do not accept Worker-supplied UUIDs as authority, derive authorization from mutable Task parameters alone, or invent a parallel approval path. Reuse and extend the existing single-request processed `DatasetIngestion` path for G3's initial HTTP acceptance. Persist the consumed approval binding and execution fencing against that ingestion/Task, and make the byte budget one durable shared counter for the execution. Reject SRA, multi-Task ingestion, unsupported schemes, missing/expired approval, and unbound callers before start.

Before implementing Supervisor start, bind the exact Task, normalized request/source digest, owner/project, allowed target policy, durable byte budget, expiry, caller/environment, and trusted execution epoch to the existing Prepare/Approval record. Persist approval consumption and make budget reservation/consumption atomic across Supervisor instances. This is an implementation prerequisite, not a runtime-only environment blocker.

## Evidence boundary

This is a source audit, not proof of live Redis/Task interaction or PostgreSQL behavior. It does not authorize migrations, service startup, Supervisor execution, or release-gate changes. Existing release flags remain closed. The current host's separate missing cgroup, quota, and capability prerequisites are recorded in [`host-preflight-visible-gate.txt`](host-preflight-visible-gate.txt).

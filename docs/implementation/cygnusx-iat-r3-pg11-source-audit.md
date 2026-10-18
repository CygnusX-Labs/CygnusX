# IAT-R3 PG-11 Application Guard Audit

Date: 2026-10-18

Status: `PASS_ISOLATED` for the reviewed application guards; full PG-11 remains `BLOCKED`.

This is a source and unit-test audit of download Task status writes. It does not certify PostgreSQL roles, database triggers, every production SQL writer, or concurrent behavior on PostgreSQL.

| Path | Guard observed | Boundary |
|---|---|---|
| `src/cygnusx/infrastructure/celery_app/tasks/download.py` | Worker claims only with `UPDATE ... WHERE status = 'queued'`; a non-single-row claim does not execute the downloader. | Atomic claim is in source; concurrent PostgreSQL behavior was not run in this workspace. |
| `src/cygnusx/application/services/task_service.py` | Download cancellation locks the Task row, reloads it, then applies the domain transition. | Unit tests cover cancellation and late callbacks with SQLite fixtures; not a PostgreSQL race test. |
| `src/cygnusx/infrastructure/database/repositories/task_repository.py` | Download Task save reloads under `FOR UPDATE`, preserves cancellation, and refuses a status change from `success` or `failed`. | This protects writes using the repository. It cannot constrain direct SQL from a role with table update rights. |
| `src/cygnusx/domain/task/services.py` | A late domain transition cannot move a cancelled download Task to another state. | Defense in depth; repository lock/recheck is the persistence boundary for application writes. |
| `src/cygnusx/infrastructure/celery_app/tasks/download.py` | File finalization rereads the current row under lock and refuses registration when it is cancelled. | No process-tree stop or egress-revocation claim follows from this database guard. |
| `src/cygnusx/infrastructure/download/reliability.py` | Recovery scans queued/running versioned Tasks; it dispatches queued rows and marks stale running rows for reconciliation instead of replaying them. | Real Broker/Worker recovery and PostgreSQL locks remain unverified. |

The historical R2 probe recorded that raw SQL could write a terminal Task back to `success` in its disposable database. That proves the application guard is not a database-level state machine. The current work did not verify database grants, whether Web and Worker use distinct roles, triggers, or production write paths. Do not claim raw SQL is prevented; treat direct table writers as trusted until role separation or a database constraint is independently implemented and tested.

The focused S4-A/S4-B0 regression includes stale-cancellation and repository behavior but uses SQLite. Its current run is [`s4-unit-regression.txt`](../../evidence/iat-r3-20261018/s4-unit-regression.txt). The observed direct-SQL result is in the historical [`IAT-R2 run log`](../../evidence/iat-20261017/13-iat-r2/iat-gap-run.log), not a current PostgreSQL certification.

## PG-11 disposition

- `PG-11.R3-SERVICE-GUARDS`: `PASS_ISOLATED` for the application paths listed above.
- `PG-11` parent: `BLOCKED` until an authorized PostgreSQL run verifies competing finalize/cancel writes, all relevant service roles and grants, and the behavior of any direct SQL writer.
- No migration, trigger, role change, or production database operation was performed.


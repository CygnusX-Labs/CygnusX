# IAT-R3 MQ-02 Evidence Reconciliation

Date: 2026-10-18

## Finding

The 2026-10-17 MQ-02 report proves a real PostgreSQL Task row remained `queued` after an injected exception from a replacement `dispatch_download` function. A separate corrected query reports one Task for the matching idempotency key. This supports the database persistence and idempotency child assertion.

The harness does not prove that a real unavailable broker makes the production dispatch path raise. `iat_mq_harness.py::case_mq02` assigns `rel.dispatch_download = failing_dispatch`, where the replacement appends the ID and raises `RuntimeError`; this bypasses `enqueue_task` and Kombu. The same evidence says a direct Redis client connection failed, while Celery `send_task` returned an ID and no consumer received the message. That is consistent with a producer call that has no delivery acknowledgement, not with a confirmed broker rejection.

The parent `MQ-02` therefore remains `BLOCKED`. `MQ-02.R2-PERSISTENCE` retains `PASS_RUNTIME` for the narrower real-PG persistence and idempotency evidence. No broker recovery or delivery guarantee is inferred from the replacement function.

## Code correction

`dispatch_download` logs `transport_call_returned` when `enqueue_task` returns. That describes the observed client-side event without claiming broker receipt. The function's boolean likewise means only that no exception escaped the transport call. The existing stale-queued reconciler remains a separate eventual-recovery mechanism; its interval does not prove immediate delivery.

## Evidence and next run

- Historical harness: [`iat_mq_harness.py`](../../evidence/iat-20261017/13-iat-r2/iat_mq_harness.py), `case_mq02`.
- Historical final verdict: [`mq02-final-verdict.txt`](../../evidence/iat-20261017/13-iat-r2/mq02-final-verdict.txt).
- Historical clarification: [`mq02-clarification.txt`](../../evidence/iat-20261017/13-iat-r2/mq02-clarification.txt).
- Current broker credentials and isolated services are unavailable. No broker was contacted in this turn.

To close the parent case, run an authorized isolated test against the configured broker and real `dispatch_download` implementation. Inject a broker-side connection loss around publish, record publisher return/error, broker queue/message state and consumer receipt, then verify the same durable Task is recovered without creating another Task. Keep the download execution gate closed so no transfer can start.

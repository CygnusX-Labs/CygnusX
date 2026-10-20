# ADR 0001: CygnusX Memory Storage

## Status

Accepted for the memory v2 rollout.

## Decision

CygnusX uses a small, application-owned PostgreSQL layer backed by pgvector.
`memory_blocks` stores curated resident context and `memory_facts` stores
time-decayed semantic facts. Application code accesses facts through the
`FactStore` protocol so a future Qdrant or pgvectorscale migration does not
change the service contract.

Workspace memory is file-native: `MEMORY.md` is a short index and `.memory/`
contains lazily-read note bodies. Workspace files remain user-owned and are
treated as untrusted context when injected into a prompt.

## Consequences

- No hosted memory service or graph database is required.
- pgvector must be available before the v2 migrations run.
- Embeddings are currently not encrypted at rest; encryption scope requires a
  separate compliance decision because encrypted vectors cannot be filtered or
  searched by the database.
- Graphiti/graph storage is reconsidered if audit-style temporal decision
  tracing is required, and a vector backend is reconsidered above 10 million
  facts or when p99 retrieval must be below 10ms.

## Settlement failure semantics

Extraction failure must preserve the unsettled message interval. Provider errors,
malformed JSON, and invalid fact structures must not create a settlement or
advance the cursor. Only a valid extraction array (including an explicit empty
array) can proceed to persistence. Failures emit a counter and a log without
conversation text; replay uses the unchanged cursor.

## Recall degradation and forgetting

When a v2 partition has no query embedding or no vector hits, recall falls back
to escaped case-insensitive matching against content and keywords, retaining
user, Agent partition and active-status filters. The forgetting tool uses the
same owner-filtered logical archive operation as v2 management deletion.

## Resident block lifecycle

V2 writes initialize missing blocks using PostgreSQL conflict-ignore insertion.
Profile and preferences use the shared Agent partition; current_focus uses the
current Agent partition. With the default-off memory_focus_per_project_enabled flag,
focus reads/writes use exact project_id and never fall back to NULL for a project
request. Disabled mode uses only the general NULL focus and retains all project
rows. Two partial unique indexes cover NULL and non-NULL projects. Project blocks
are initialized lazily on focus writes, not prompt reads. Management editing checks
project ownership; Agent tools derive projects from controlled sessions.
Initialization never replaces content or versions.
Both tool and management block edits use the application service and retain
optimistic concurrency checks.

## Project partition

Facts carry nullable project_id. Recall selects global facts plus the current
project; without a project only global facts are recalled. Profile/preference
writes remain global and shared. Project identity participates in fact hashes
so equal statements in different projects remain independent. The migration
recovers ownership from matching source sessions and archives unresolved old
project facts. Downgrade retains the archive decisions and scoped hashes to
avoid data loss or cross-project uniqueness collisions.

## Maintenance and acknowledgement

Embedding backfill targets the active memory backend and reports successful
updates separately from failures. Queued settlements recheck the v2 and site
switches before reading messages. Save tools expose the persisted content so
the assistant can acknowledge exactly what was saved and attribute recalled
facts without inventing past interactions.

## Episodic memory

Settlement extracts facts, an optional cumulative session episode, and optional
current_focus in one model call. Episode revisions supersede prior active
summaries for the same source session and project; their hashes include session
identity. Latest active episode injection uses exact user/Agent/project filters
and does not depend on an embedding. All settlement outputs share one commit
with the message cursor. Input batching settles a contiguous prefix of complete
messages, preserving over-budget input for replay instead of silently skipping it.

## Prompt allocation

V2 injection uses configurable UTF-8 budgets (6000 total bytes by default),
reserves bounded space for the latest episode, selects complete resident blocks,
and uses remaining space for ranked facts. Oversized units are omitted and
counted rather than truncated. Empty allocations produce no memory wrapper.

## Importance and reinforcement

Extraction adds bounded integer importance in the existing model call. Recall
uses relevance, recency, importance, and a capped logarithmic access boost.
Only returned or actually injected facts enter asynchronous batched statistics.
A durable batch receipt and an owner/active-filtered counter update share one
transaction, preventing retry double counting and partial commits. Broker failure
is observable and does not block an answer. Receipts remain retained until a
reviewed retention policy can preserve replay semantics.

## Conflict arbitration

Settlement supplies bounded, owner/Agent/project-filtered active candidates to
its existing extraction call. The model can propose add, update or duplicate;
it cannot delete or target arbitrary IDs. The application verifies membership
and scope, then the store conditionally updates only an active target in the
same partition. Concurrent invalidation rolls back the interval for replay.
Keyword-only replacement is removed. Semantic quality and out-of-candidate
conflicts still require evaluation and consolidation.

## Re-remembering after invalidation

Explicit saves may create a new active version of previously inactive text.
The old row remains inactive with its original content, source and revision link;
only its dedup slot is retired. Conditional retirement and new insertion share
a transaction and the existing uniqueness constraint. Automatic extraction keeps
the default refusal to resurrect inactive text. Empty vectors are persisted as
NULL together with a NULL model identifier, preserving lexical degradation.
Project migration re-upgrades preserve scoped and historical version hashes.

## Immediate explicit-write arbitration

Explicit v2 writes use an independently configurable, bounded candidate review
before persistence. Missing or exact-only candidates need no model call. Invalid
or unavailable arbitration fails visibly before writing. The new active version
and all scoped supersessions share a database savepoint, so a stale later target
cannot leave partial revisions or unrelated outer work rolled back. Shared
retrieval accepts only profile/preference facts; project/summary writes require
an Agent partition. Environment examples use a single disabled v2 rollout flag.

## Runtime gate

Automated Chat/L4 reads, memory tools, settlement and recall recording share a
v2-plus-site policy. Missing database context or failed site lookup disables the
operation instead of allowing it. Tool identities must match the invocation;
session-derived project lookups include the owner. Permissioned manual data
management and explicit operator maintenance remain available for correction
and audit. A gate is checked at operation start, not held across model calls.

## Legacy partition normalization

A data migration copies active personal facts to canonical shared slots and
retains linked source rows. Existing invalidated shared facts take precedence
over legacy active duplicates, preserving forgetting. Legacy personal blocks
become archived, linked history. Curated shared text and deliberately cleared
blocks are preserved; only untouched empty slots are seeded. Canonical versions
advance beyond source versions. Archived blocks are excluded from injection and
read-only in management. Downgrade refuses to erase archived block lineage;
turning off v2 remains the preferred runtime rollback.


## Lexical residual hints and user-directed cleanup

A default-off memory_forget_residual_scan_enabled flag adds bounded lexical hints
after an owner-filtered fact archive. The scan uses a savepoint so a recoverable
scan failure does not undo archiving. Active shared personal memory and the
controlled Agent/project range are checked; no broader semantic erasure is claimed.
Hints contain at most 60 characters, never arbitrary full blocks. The management
report endpoint and Agent tool return disabled/complete/partial/failed explicitly.
The old DELETE contract remains 204. Blocks require explicit user CAS edits;
related facts/episodes require a separate confirmed archive. Client-reported
click telemetry checks ownership but never mutates memory. Historical chats,
workspace files and audit snapshots are outside the scan, and paraphrase
suppression/archived_reason remain optional unimplemented work.


## Embedding model compatibility and maintenance

The default-off model filter confines vector SQL to the configured model label.
Old/unlabelled/missing vectors retain bounded lexical visibility even when a
compatible vector matches another fact; full RRF remains separate work. Legacy
fallback ranking also skips incompatible vector comparisons. New facts always
store vector and nonempty model identifier as a pair, or both NULL.

Operator maintenance supports counts-only dry-run and explicit model-mismatch
rebuild in batches of at most 500. A batch binds the target model, generates
vectors before taking update-row locks, and uses conditional writes against the
captured row state. It never revives inactive facts; failed generation retains old
values. The CLI requires an explicit DSN and resolves its Provider in that same
DB. Committed outcomes and separately gated periodic coverage samples provide
observability, with a sample timestamp to expose stale observations. The shared
cosine adapter returns a Float result and retains a Vector query parameter.
Real pgvector, Provider and quality acceptance remain outstanding.

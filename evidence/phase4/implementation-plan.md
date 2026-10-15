# Phase4 implementation plan / P4-0

Current gates: runtime BLOCKED (Docker socket denied, no redis-server/psql, socket creation denied). Source WRITE_RUNTIME_ACCEPTED remains false. No deployment/production DB/real research downloads allowed. Baseline and per-file originals preserved under evidence/phase4.

A: strengthen DatasetAnalysisLink execution binding and final TaskService/Worker input validation, bind real Task before queue; normalize/verify actual RNA/counts manifests without fabricating historical identity.
B: one immutable result-observation relation (needed before report rendering), existing FileRegistry artifact identities, strict owner/project graph DTO and read APIs. Existing ReportSnapshot remains the report evidence authority.
C/D: reuse ReportService for verified existing scientific HTML, existing Snapshot/Job renderer for independent execution report; append optional lineage to v1 snapshots without changing old hashes. No new compute engine.
E: extend existing Dataset reconcile/Beat and report Job outbox; existing artifacts/links only, bounded scans, no analysis/download replay.
F: project research-chain UI, shared read-only Gateway capabilities for both Agents, default flags off.
G: synthetic actual counts/manifest/dual-report isolated test where dependencies permit; live public case BLOCKED until P4-0 and explicit budget approval. Supply isolated runtime acceptance scripts/runbook, no production fallback.

Validation: T01–44 and G0–18 explicitly mapped to actual tests/evidence; SQLite migration first, PG/Redis/MCP/Worker runtime independently marked BLOCKED. Scoped strict lint/mypy and regressions; record existing full-tree failures without unrelated fixes.

# RA01 FAIL — fresh-DB migration fails: mcp_versions ALTER ordered before CREATE

Run: ri095-20261017-attempt1
Source commit: d9c92cf6ee1c (branch feat/research-agent-phase5)
Image: 127.0.0.1:5000/ri095-app-ext@sha256:1c1476f89160460a37084300e666433e402c0a0f7ca91ad64e0ddbd3a4788919
Command: control.py start (migrate role) -> alembic upgrade head
Observed: sqlalchemy ProgrammingError / asyncpg UndefinedTableError
  relation "mcp_versions" does not exist
  [SQL: ALTER TABLE mcp_versions ADD COLUMN contract_digest VARCHAR(80) DEFAULT '' NOT NULL]
Applied: 42 revisions before failure; DB left with 0 public tables and no alembic_version (full tx rollback).

## Root cause
Alembic linearizes parallel branches by its own ordering heuristic (not commit date).
The linearized order places the ALTER (c1d2e3f4b5a6) at revision #42 while the CREATE
(h6i7j8k9l1m3, add_mcp_builder_tables) is applied ~8 revisions later.
- c1d2e3f4b5a6: down_revision = a5b6c7d8e9f0 ; op.add_column("mcp_versions", contract_digest)
- h6i7j8k9l1m3: down_revision = g4h5i6j7k8l9 ; op.create_table("mcp_versions", ...)
Neither is an ancestor of the other. They join only at mcpdigestmerge01
(down_revision = (projectdelivery01, c1d2e3f4b5a6)); the h6i7j8k9l1m3 chain reaches
mcpdigestmerge01 via a different merge path. No dependency edge forces CREATE before ALTER.

## Why prior gates missed it
- `make check-migrations` / alembic autogenerate: topology is connected and head is unique,
  so static checks pass. They do not validate statement-level table existence ordering.
- A pre-existing DB that already had mcp_versions (created earlier in its history) never
  re-run into this ordering, so the defect only manifests on a truly empty database.

## Impact
Fresh/empty-database provisioning is broken: `alembic upgrade head` cannot complete.
This is an environment independent defect (reproduces in the isolated acceptance DB).

## Minimal fix (proposed, not yet applied pending verification)
Add a dependency edge so the ALTER branch descends from the CREATE branch, e.g. change
c1d2e3f4b5a6.down_revision from a5b6c7d8e9f0 to h6i7j8k9l1m3 (or insert a merge that
guarantees h6i7j8k9l1m3 precedes c1d2e3f4b5a6). Requires full-chain re-run to validate.

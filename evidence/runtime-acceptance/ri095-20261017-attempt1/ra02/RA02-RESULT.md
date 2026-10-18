# RA02 — REAL PostgreSQL constraint assertions: PASS_RUNTIME
Database: project_export_test_ri095 @ PostgreSQL 14.23 (real PG, not SQLite)
Run: ri095-20261017-attempt1 | Evidence: ra02-results.txt

| # | Scenario | Expected | Actual SQLSTATE | Verdict |
|---|---|---|---|---|
| 1 | report_files XOR both NULL | 23514 check_violation | 23514 | PASS |
| 2 | report_files XOR both SET | 23514 | 23514 | PASS |
| 3 | FK to non-existent file_record | 23503 foreign_key_violation | 23503 | PASS |
| 4 | XOR exactly one (legal) | none (00000) | 00000 | PASS |
| 5 | Frozen export manifest mutate | P0001 raise_exception | P0001 | PASS |
| 6 | Frozen report identity mutate | P0001 | P0001 | PASS |
| 7 | status=ready without html fields | 23514 | 23514 | PASS |
| 8 | export status outside enum | 23514 | 23514 | PASS |
| 9 | report status outside enum | 23514 | 23514 | PASS |
| 10 | attempt_count < 0 | 23514 | 23514 | PASS |
| 11 | duplicate (user,project,source_digest) | 23505 unique_violation | 23505 | PASS |
| 12 | legal attempt_count update | none (00000) | 00000 | PASS |

Guards verified by their own messages: "Frozen project export scope cannot change",
"Frozen project report identity cannot change". read-only state.sql snapshot in ra01/attempt2-fixed/.
Not covered here: RA01 old-model upgrade path (see ra01), RA03 8-API concurrency (see ra03).

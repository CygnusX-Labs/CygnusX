"""RA02: real PostgreSQL constraint assertions against the isolated acceptance DB.

Each case runs in its own transaction and records the actual SQLSTATE. Expected
failures are distinguished from unexpected ones (exit non-zero is NOT success).
"""

import json
import os
import sys

import psycopg

DSN = os.environ["RA02_DSN"]

UID = "00000000-0000-4000-8000-0000000000a1"  # user
PID = "00000000-0000-4000-8000-0000000000a2"  # project
MANIFEST = "00000000-0000-4000-8000-0000000000b1"  # source export/manifest job
REPORT = "00000000-0000-4000-8000-0000000000c1"  # reports row
RJFROZEN = "00000000-0000-4000-8000-0000000000e1"  # seeded report job (frozen/duplicate)
FREC = "00000000-0000-4000-8000-0000000000f1"  # file_records row
RFNEW = "00000000-0000-4000-8000-0000000000f9"  # report_files insert id
CASE7 = "00000000-0000-4000-8000-0000000000e7"
CASE9 = "00000000-0000-4000-8000-0000000000e9"
CASE10 = "00000000-0000-4000-8000-0000000000ea"
CASE8 = "00000000-0000-4000-8000-0000000000d8"
DUP = "00000000-0000-4000-8000-0000000000ee"


def report_job_insert(job_id, request_key, source_digest, status, attempt_count):
    return (
        "INSERT INTO project_report_jobs (id,user_id,project_id,source_manifest_job_id,"
        "request_key,source_digest,source_snapshot,version,status,attempt_count,retryable,"
        "pdf_status) VALUES "
        f"('{job_id}'::uuid,'{UID}'::uuid,'{PID}'::uuid,'{MANIFEST}'::uuid,'{request_key}',"
        f"'{source_digest}','{{}}'::json,1,'{status}',{attempt_count},false,'not_requested')"
    )


CASES = [
    (
        "1_XOR_both_null",
        "23514",
        [
            "INSERT INTO report_files (id, report_id, project_report_job_id, name, type, "
            f"size, path) VALUES ('{RFNEW}'::uuid, NULL, NULL, 'n', 'html', 1, 'p')"
        ],
    ),
    (
        "2_XOR_both_set",
        "23514",
        [
            "INSERT INTO report_files (id, report_id, project_report_job_id, name, type, "
            f"size, path) VALUES ('{RFNEW}'::uuid, '{REPORT}'::uuid, '{RJFROZEN}'::uuid, "
            "'n', 'html', 1, 'p')"
        ],
    ),
    (
        "3_FK_bad_file_record",
        "23503",
        [
            "INSERT INTO report_files (id, report_id, file_record_id, name, type, size, path) "
            f"VALUES ('{RFNEW}'::uuid, '{REPORT}'::uuid, "
            "'00000000-0000-4000-8000-0000000000de'::uuid, 'n', 'html', 1, 'p')"
        ],
    ),
    (
        "4_XOR_single_legal",
        "00000",
        [
            "INSERT INTO report_files (id, report_id, name, type, size, path) "
            f"VALUES ('{RFNEW}'::uuid, '{REPORT}'::uuid, 'n', 'html', 1, 'p')"
        ],
    ),
    ("7_ready_requires_html", "23514", [report_job_insert(CASE7, "rrk7", "sd7", "ready", 0)]),
    ("9_report_status_enum", "23514", [report_job_insert(CASE9, "rrk9", "sd9", "garbage", 0)]),
    (
        "10_attempt_count_negative",
        "23514",
        [report_job_insert(CASE10, "rrk10", "sd10", "queued", -1)],
    ),
    (
        "8_export_status_enum",
        "23514",
        [
            "INSERT INTO project_export_jobs (id,user_id,project_id,request_key,"
            "manifest_digest,manifest,status,attempt_count,retryable) VALUES "
            f"('{CASE8}'::uuid,'{UID}'::uuid,'{PID}'::uuid,'rk8','md8','{{}}'::json,"
            "'garbage',0,true)"
        ],
    ),
]


def main():
    out = []
    with psycopg.connect(DSN, autocommit=True) as conn:
        cur = conn.cursor()
        cur.execute("SELECT version()")
        out.append({"database": cur.fetchone()[0]})
        with conn.transaction():
            cur.execute(
                "INSERT INTO users (id, username, email, hashed_password, role, status, "
                f"preferences) VALUES ('{UID}'::uuid,'ra02','ra02@example.invalid','x',"
                "'user','active','{}'::json) ON CONFLICT DO NOTHING"
            )
            cur.execute(
                "INSERT INTO projects (id, user_id, name, slug, status) "
                f"VALUES ('{PID}'::uuid,'{UID}'::uuid,'ra02-proj','ra02-proj','active') "
                "ON CONFLICT DO NOTHING"
            )
            cur.execute(
                "INSERT INTO reports (id, task_id, user_id, flow_id, status, created_at) "
                f"VALUES ('{REPORT}'::uuid,'{MANIFEST}'::uuid,'{UID}'::uuid,'rna_seq',"
                "'generating',now()) ON CONFLICT DO NOTHING"
            )
            cur.execute(
                "INSERT INTO file_records (id, user_id, original_name, storage_path, size, "
                f"checksum, created_at, updated_at) VALUES ('{FREC}'::uuid,'{UID}'::uuid,'n',"
                "'acceptance/x',1,'h',now(),now()) ON CONFLICT DO NOTHING"
            )
            cur.execute(
                "INSERT INTO project_export_jobs (id,user_id,project_id,request_key,"
                "manifest_digest,manifest,status,attempt_count,retryable) VALUES "
                f"('{MANIFEST}'::uuid,'{UID}'::uuid,'{PID}'::uuid,'rkf','mdf','{{}}'::json,"
                "'ready',1,false) ON CONFLICT DO NOTHING"
            )
            cur.execute(
                report_job_insert(RJFROZEN, "rrkf", "sdf", "queued", 0) + " ON CONFLICT DO NOTHING"
            )

        for name, expected, sqls in CASES:
            got, detail = "00000", ""
            try:
                with conn.transaction():
                    for statement in sqls:
                        cur.execute(statement)
            except psycopg.Error as exc:
                got = exc.sqlstate or "UNKNOWN"
                detail = str(exc).splitlines()[0][:200]
            record = {
                "case": name,
                "expected": expected,
                "actual": got,
                "match": got == expected,
                "detail": detail,
            }
            out.append(record)
            print(json.dumps(record, ensure_ascii=False), flush=True)

        for name, expected, statement in (
            (
                "5_frozen_export_manifest",
                "P0001",
                f"UPDATE project_export_jobs SET manifest_digest='changed' "
                f"WHERE id='{MANIFEST}'::uuid",
            ),
            (
                "6_frozen_report_identity",
                "P0001",
                f"UPDATE project_report_jobs SET source_digest='changed' "
                f"WHERE id='{RJFROZEN}'::uuid",
            ),
            (
                "11_duplicate_source_digest",
                "23505",
                report_job_insert(DUP, "rrk11", "sdf", "queued", 0),
            ),
            (
                "12_legal_attempt_count_update",
                "00000",
                f"UPDATE project_report_jobs SET attempt_count=1 WHERE id='{RJFROZEN}'::uuid",
            ),
        ):
            got, detail = "00000", ""
            try:
                with conn.transaction():
                    cur.execute(statement)
            except psycopg.Error as exc:
                got = exc.sqlstate or "UNKNOWN"
                detail = str(exc).splitlines()[0][:200]
            record = {
                "case": name,
                "expected": expected,
                "actual": got,
                "match": got == expected,
                "detail": detail,
            }
            out.append(record)
            print(json.dumps(record, ensure_ascii=False), flush=True)

    scored = [r for r in out if "match" in r]
    failures = [r for r in scored if not r["match"]]
    print(json.dumps({"summary": {"total": len(scored), "failures": len(failures)}}), flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

-- Read-only final state evidence; run only against the dedicated acceptance database.
\set ON_ERROR_STOP on
SELECT current_database(), current_user, inet_server_addr(), version();
SELECT version_num FROM alembic_version;
SELECT conrelid::regclass, conname, pg_get_constraintdef(oid)
FROM pg_constraint WHERE conrelid IN
 ('report_files'::regclass, 'project_report_jobs'::regclass, 'project_export_jobs'::regclass)
ORDER BY conrelid::regclass::text, conname;
SELECT tgrelid::regclass, tgname, pg_get_triggerdef(oid)
FROM pg_trigger WHERE NOT tgisinternal AND tgrelid IN
 ('project_report_jobs'::regclass, 'project_export_jobs'::regclass);
SELECT id, user_id, project_id, source_manifest_job_id, source_digest, version,
 status, attempt_count, retryable, html_file_record_id, html_sha256, html_size,
 pdf_file_record_id, pdf_sha256, pdf_size, pdf_status, error_code
FROM project_report_jobs ORDER BY created_at;
SELECT id, user_id, project_id, manifest_digest, status, attempt_count
FROM project_export_jobs ORDER BY created_at;
SELECT locktype, database, classid, objid, objsubid, mode, granted
FROM pg_locks WHERE locktype = 'advisory';

# Private storage / FileRegistry: PASS_RUNTIME (local backend scope)
- Published HTML: FileRecord adecb7a4 (owner b81b4152 = user A),
  ReportFile ee0ea804 links file_record + project_report_job (report-file-link.txt).
- On-disk artifact SHA-256 == DB html_sha256 == download SHA-256:
  1d89e889399a611a708e1528e8c1be44b033a022d1b09fbc12f5e69bc999c33a (6635 bytes).
  Atomic publish -> readback integrity verified (download-check.txt, html-artifact.txt).
- Storage root /acceptance-storage, UID 10001 ownership (ls shows 10001:10001).
- Owner scoping: user B 404 on A's inventory and download (authorization-negative.txt).

## BLOCKED within storage
- Drift / loss / duplicate / invalid-symlink / quota injection: not executed; requires
  an approved corpus baseline with trusted expected digests (corpus BLOCKED).
- Object storage (S3): no authorized test bucket -> separately BLOCKED. Local pass only;
  conclusion is "local storage scope passed", object storage remains BLOCKED.

# M0 -> Report -> M1 -> ZIP: PASS_RUNTIME (chain mechanics) with documented gaps
All produced by a real Worker job on real PG/Redis; no synthetic packaging script.

## Report (HTML)
- scientific-summary job 99323137 (owner A) -> status ready,
  html_sha256=1d89e889399a611a708e1528e8c1be44b033a022d1b09fbc12f5e69bc999c33a size=6635
- on-disk file SHA == DB == HTTP download SHA (verified).
- pdf_status=PDF_NOT_GENERATED (Pandoc/Typst/fc-list MISSING in worker image -> PDF BLOCKED).

## Export (ZIP)
- export job f61dafa4 -> status ready, archive_sha256=e8ad747148b1b17842cab7d4067938c52023a0a3ca8ca966b1e067c4d5b11c37
- on-disk zip SHA == DB archive_sha256 (7372 bytes).
- Members: ProjectDeliveryManifest.json, README.md, checksums.sha256, verify_project_delivery.py
- Repo's own stdlib verifier cygnusx.domain.project_delivery_archive.verify_archive(zip)
  returned OK (zip-verify.txt).
- evidence_status="partial" declared in manifest; gaps list
  [HISTORICAL_ASSOCIATION_COVERAGE_NOT_RECORDED, REPRODUCTION_NOT_RUN].

## FINDINGS (honest gaps, not failures of the gate)
1. The generated HTML scientific report is NOT a member of the export ZIP. The export
   selection was the default ExportSelection (kind=evidence, empty task/report ids),
   so the manifest files[] = [README.md, verify_project_delivery.py] only. Including the
   project report requires ExportSelectionV2 (source_manifest_job_id + project_report_job_ids),
   which is a different, explicitly-selected export. Recorded as a coverage gap: the
   default evidence export does not bundle the project report.
2. "M0 -> M1" version-transition comparison and "old M0/ZIP bytes unchanged" across
   re-runs could NOT be exercised: it requires an APPROVED completed-task corpus with a
   frozen prior M0 manifest + prior ZIP baseline. No such corpus exists in the repo.

## BLOCKED (chain)
- Frozen old M0 / old ZIP baseline comparison (corpus BLOCKED).
- ZIP download via JWT + post-revocation rejection: the export-file download route was
  not exercised (report download WAS exercised). Marked partial.

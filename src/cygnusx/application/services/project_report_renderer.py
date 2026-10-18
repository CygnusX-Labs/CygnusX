"""Versioned static project template; consumes frozen facts only."""

from cygnusx.application.schemas.project_report import ProjectReportSource
from cygnusx.application.services.report_audit_renderer import _table, _value, report_document_css


def render_project_report(source: ProjectReportSource) -> bytes:
    source = ProjectReportSource.model_validate(source.model_dump(mode="json"))
    manifest = source.manifest

    def refs(*kinds: str) -> str:
        return _table(
            ("Kind", "ID", "Task", "Version", "Status"),
            (
                tuple(_value(v) for v in (r.kind, r.id, r.task_id, r.version, r.status))
                for r in manifest.references
                if r.kind in kinds
            ),
        )

    unknown = "<p>NOT_RECORDED：冻结来源没有记录此事实。</p>"
    verified = [c for c in source.selection.claims if c.verification_status == "VERIFIED_VALUE"]
    findings = (
        _table(
            ("Feature", "Column", "Value", "Scope", "SHA-256"),
            (
                tuple(
                    _value(v)
                    for v in (
                        c.row_identifier,
                        c.column_identifier,
                        c.value,
                        c.verification_status,
                        c.file_sha256,
                    )
                )
                for c in verified
            ),
        )
        if verified
        else "<p>无已验证结论。</p>"
    )
    gaps = sorted(
        set(manifest.gaps) | {g for c in source.selection.claims for g in c.missing_evidence}
    )
    sections = (
        (
            "Project Overview",
            _table(
                ("Field", "Frozen value"),
                (
                    ("Project", _value(source.project_id)),
                    ("M0", _value(source.source_manifest_digest)),
                    ("Source", _value(source.content_digest())),
                ),
            ),
        ),
        ("Research Objectives", "<p>研究意图非事实；NOT_RECORDED。</p>"),
        ("Dataset Inventory", refs("dataset_version")),
        ("Data Provenance", refs("file_record", "result_observation")),
        ("Analysis Workflows", unknown + "<p>历史镜像、工具和参考版本：NOT_OBSERVED。</p>"),
        ("Execution Summary", refs("task", "run")),
        (
            "Scientific Results",
            refs("report") + "<p>既有科学报告为原始结果；此报告未重新计算。</p>",
        ),
        ("Key Findings", findings),
        ("Quality Control", unknown + "<p>无明确测量与规则时不判定 QC PASS。</p>"),
        ("Evidence Coverage", _table(("Gap",), ((_value(g),) for g in gaps))),
        ("Report Inventory", refs("report", "report_snapshot", "evidence_manifest")),
        ("Reproducibility Readiness", "<p>REPRODUCIBILITY_STATUS: NOT_RUN</p>"),
        (
            "Limitations",
            "<p>有限数值证据核验不保证机制、因果、科研结论或复现成功。FILE_INTEGRITY、EVIDENCE_COVERAGE 和 DELIVERY_COMPLETENESS 分别核验。</p>"
            + _table(
                ("Unverified cell",),
                (
                    (_value(c.claim_id),)
                    for c in source.selection.claims
                    if c.verification_status != "VERIFIED_VALUE"
                ),
            ),
        ),
        (
            "Appendix",
            _table(
                ("Template", "Renderer", "Runtime"),
                (
                    (
                        _value(source.template_version),
                        _value(source.renderer_version),
                        _value(source.renderer_runtime),
                    ),
                ),
            )
            + _table(
                ("File", "Bytes", "SHA-256"),
                ((_value(f.path), _value(f.size), _value(f.sha256)) for f in manifest.files),
            ),
        ),
    )
    nav = (
        '<nav aria-label="章节导航">'
        + "".join(
            f'<a href="#section-{i}">{i}. {_value(title)}</a>'
            for i, (title, _) in enumerate(sections, 1)
        )
        + "</nav>"
    )
    body = "".join(
        f'<section id="section-{i}"><h2>{i}. {_value(title)}</h2>{content}</section>'
        for i, (title, content) in enumerate(sections, 1)
    )
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\">"
        f"<title>Project Scientific Summary</title><style>{report_document_css()}</style></head><body>"
        '<header><h1>Project Scientific Summary</h1><p class="notice">仅组织冻结来源与有限证据；未进行科研计算或复现验证。</p></header>'
        f"{nav}{body}</body></html>"
    ).encode()

"""Offline, script-free execution-evidence HTML; never a scientific rerun claim."""

from __future__ import annotations

from collections.abc import Iterable
from html import escape
from typing import Any

from cygnusx.application.schemas.report_snapshot import (
    EvidenceSource,
    EvidenceStatus,
    ReportSnapshot,
)

TEMPLATE_VERSION = "audit-v1.0.0"
STATUS_LABELS = {
    EvidenceStatus.VERIFIED: "已核验（限注明范围）",
    EvidenceStatus.NOT_RECORDED: "未记录",
    EvidenceStatus.UNAVAILABLE: "不可用",
    EvidenceStatus.NOT_APPLICABLE: "不适用",
    EvidenceStatus.VERIFICATION_FAILED: "核验失败",
    EvidenceStatus.ESTIMATED: "声明 / 估算，未执行时核验",
}


def _value(value: Any) -> str:
    return escape("未记录" if value is None else str(value), quote=True)


def _source(source: EvidenceSource) -> str:
    status = source.verification_status
    return (
        f'<span class="state {status.value}">{_value(STATUS_LABELS[status])} '
        f"({_value(status.value)})</span><small>来源：{_value(source.source_type)} "
        f"{_value(source.source_id)} · {_value(source.capture_method)}<br>"
        f"记录时间：{_value(source.observed_at)}<br>"
        f"范围：{_value(source.verification_details)}</small>"
    )


def _table(headers: tuple[str, ...], rows: Iterable[tuple[str, ...]]) -> str:
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    if not body:
        body = f'<tr><td colspan="{len(headers)}">未记录 (not_recorded)</td></tr>'
    return (
        '<div class="table-wrap"><table><thead><tr>'
        + "".join(f"<th>{_value(header)}</th>" for header in headers)
        + "</tr></thead><tbody>"
        + body
        + "</tbody></table></div>"
    )


def render_audit_report(
    snapshot: ReportSnapshot, *, title: str = "RNA-seq 可复现执行证据报告"
) -> str:
    """Consume only a frozen snapshot. All user text is escaped, no filesystem reads."""
    if (
        snapshot.research_delivery
        and snapshot.research_delivery.flow.get("id") == "counts_deg"
        and title == "RNA-seq 可复现执行证据报告"
    ):
        title = "Counts DEG 可复现执行证据报告"
    execution = snapshot.source_execution
    task_step = next((step for step in snapshot.execution_steps if step.phase == "task"), None)
    complete = not snapshot.missing_evidence
    facts = {fact.field: fact.value for fact in snapshot.inputs}
    overview = (
        ("项目", execution.project_slug),
        ("任务名称", facts.get("task_name")),
        ("Task ID", execution.task_id),
        ("Run ID", execution.run_id),
        ("Run 关联状态", execution.association_status),
        ("分析类型", facts.get("flow_id", "rna_seq")),
        ("执行状态", task_step.status if task_step else None),
        ("分析开始时间", task_step.occurred_at if task_step else None),
        ("分析结束时间", task_step.finished_at if task_step else None),
        ("报告快照生成时间", snapshot.generated_at),
        ("证据采集窗口", f"{snapshot.capture_started_at} → {snapshot.capture_finished_at}"),
        ("证据完整性", "当前采集范围无已知缺口" if complete else "证据不完整，见 M8"),
    )
    input_rows = tuple(
        (_value(f.field), _value(f.value), _source(f.source)) for f in snapshot.inputs
    )
    env_rows = tuple(
        (_value(f.field), _value(f.value), _source(f.source)) for f in snapshot.environment
    )
    artifacts = tuple(
        (
            _value(f"{item.display_name or '名称未记录 / 已脱敏'} ({item.artifact_reference})"),
            _value(f"{item.category} / {item.kind}"),
            _value(item.size_bytes),
            "<br>".join(
                _value(f"{fp.algorithm}: {fp.value} ({fp.scope})") for fp in item.fingerprints
            )
            or "未记录 (not_recorded)",
            _source(item.source),
            _source(item.origin),
        )
        for item in snapshot.artifacts
    )
    research = snapshot.research_delivery
    research_table = (
        ""
        if research is None
        else "<h3>科研交付关联（独立于科学结论）</h3>"
        + _table(
            ("对象", "标识 / 状态"),
            (
                (_value(key), _value(value))
                for key, value in {
                    "DatasetVersion": research.dataset_version_id,
                    "Frozen Handoff SHA-256": research.handoff_hash,
                    "Result observation": research.result_observation_id,
                    "输入": research.input_integrity,
                    "产物": research.result_integrity,
                    "证据": research.evidence_state,
                    "交付": research.delivery_state,
                    "证据缺口": ", ".join(research.gaps),
                }.items()
            ),
        )
    )
    research_artifacts = (
        ""
        if research is None
        else "<h3>科研产物指纹</h3>"
        + _table(
            ("引用", "FileRecord", "SHA-256", "完整性"),
            (
                (
                    _value(a.logical_name),
                    _value(a.file_record_id),
                    _value(a.sha256),
                    _value(a.integrity),
                )
                for a in research.artifacts
            ),
        )
    )
    sections = (
        (
            "m1",
            "M1 · 概要",
            _table(("项目", "记录"), ((_value(k), _value(v)) for k, v in overview)),
        ),
        (
            "m2",
            "M2 · 输入与环境",
            "<h3>输入、参数与来源</h3>"
            + _table(("字段", "值", "证据"), input_rows)
            + "<p>输入文件大小与校验值：未记录；当前产物校验值不代表执行时输入指纹。</p>"
            + "<h3>历史环境与版本</h3>"
            + _table(("字段", "值", "证据"), env_rows)
            + "<p>缺失的历史软件、镜像和参考库版本不会由当前环境补填。</p>",
        ),
        (
            "m3",
            "M3 · 执行时间线",
            _table(
                ("序号 / 步骤", "开始 / 记录时间", "结束时间", "工具", "状态", "来源"),
                (
                    (
                        _value(f"{s.sequence} / {s.phase}"),
                        _value(s.occurred_at),
                        _value(s.finished_at),
                        "未记录",
                        _value(s.status),
                        _source(s.source),
                    )
                    for s in snapshot.execution_steps
                ),
            )
            + "<p>仅展示记录过的事件；不会用文件修改时间补造完整流程。</p>",
        ),
        (
            "m4",
            "M4 · 外部工具调用",
            _table(
                ("工具 / API", "可关联的证据"),
                ((_value(call.tool_name), _source(call.source)) for call in snapshot.tool_calls),
            )
            + "<p>不导出凭证、原始请求、日志或 Prompt。</p>",
        ),
        (
            "m5",
            "M5 · 质量控制",
            "<p>QC 测量结果：仅列出有记录的 QC 产物；本适配器未解释其测量值。"
            "QC 阈值：未记录。人工豁免：未记录。QC 文件存在不代表平台质量门通过。</p>"
            + _table(
                ("QC 产物", "测量证据可用性"),
                (
                    (_value(a.artifact_reference), _source(a.source))
                    for a in snapshot.artifacts
                    if a.category == "qc"
                ),
            )
            + "<h3>质量门决策</h3>"
            + _table(
                ("规则版本", "决策", "证据"),
                (
                    (_value(g.rule_version), _value(g.decision), _source(g.source))
                    for g in snapshot.quality_gates
                ),
            ),
        ),
        (
            "m6",
            "M6 · 分析产物",
            _table(
                ("文件引用", "类型", "字节数", "校验值与范围", "可用性", "来源"),
                artifacts,
            )
            + research_artifacts
            + "<p>哈希核验仅证明采集时字节；不证明执行时字节或科学结果正确。</p>",
        ),
        (
            "m7",
            "M7 · 证据来源关系",
            research_table
            + _table(
                ("主体", "关系", "对象", "证据"),
                (
                    (
                        _value(p.subject_reference),
                        _value(p.relation),
                        _value(p.object_reference),
                        _source(p.source),
                    )
                    for p in snapshot.provenance
                ),
            )
            + "<h3>来源水位</h3>"
            + _table(
                ("来源类型", "来源 ID", "版本 / 水位"),
                (
                    (_value(w.source_type), _value(w.source_id), _value(w.revision))
                    for w in snapshot.source_watermarks
                ),
            ),
        ),
        (
            "m8",
            "M8 · 复现状态与限制",
            '<p class="notice">复现验证状态：<strong>not_run（未执行重运行及结果比较）</strong></p>'
            + _table(
                ("事项", "记录"),
                (
                    ("当前评估", _value(snapshot.reproducibility.assessment)),
                    ("已满足条件", "Task 身份关联与本报告证据快照归档；核验范围见各条来源"),
                    ("缺失依赖", _value("; ".join(snapshot.reproducibility.blockers))),
                    ("限制", _value("; ".join(snapshot.warnings))),
                    ("可见范围", _value(snapshot.visibility_scope)),
                    ("脱敏策略", _value(snapshot.redaction_policy_version)),
                ),
            )
            + "<h3>尚未验证 / 缺失事项</h3>"
            + _table(
                ("字段", "状态与范围"),
                ((_value(g.field), _source(g.source)) for g in snapshot.missing_evidence),
            ),
        ),
    )
    nav = (
        '<nav aria-label="章节导航">'
        + "".join(f'<a href="#{anchor}">{_value(name)}</a>' for anchor, name, _ in sections)
        + "</nav>"
    )
    body = "".join(
        f'<section id="{anchor}"><h2>{_value(name)}</h2>{content}</section>'
        for anchor, name, content in sections
    )
    css = """
        *{box-sizing:border-box}body{font:14px/1.6 system-ui,sans-serif;color:#25314d;
        background:#f4f6fc;margin:0 auto;padding:28px 20px;max-width:1280px}
        header,section{background:white;border:1px solid #dfe4f0;border-radius:14px;
        padding:24px;margin:18px 0}header{border-top:4px solid #6972d9}
        h1{font-size:26px;margin:0}h2{font-size:21px;margin:0 0 16px}h3{font-size:16px}
        nav{display:flex;flex-wrap:wrap;gap:8px}nav a{color:#5059b2;text-decoration:none;
        padding:7px 12px;background:#e9edfc;border-radius:8px}section{scroll-margin-top:16px}
        .table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%}th,td{
        text-align:left;vertical-align:top;padding:10px;border-bottom:1px solid #e7ebf3;
        overflow-wrap:anywhere;min-width:110px}th{background:#f5f7fc;color:#52607a}
        small{display:block;color:#66738a;margin-top:6px}.state{display:inline-block;
        border:1px solid #ccd5e6;border-radius:6px;padding:2px 6px}
        .verified{color:#285382;background:#edf4fe}.estimated{color:#775100;background:#fff7df}
        .verification_failed{color:#9c2835;background:#ffedf0}.not_recorded,.unavailable,
        .not_applicable{color:#616c80;background:#f0f2f6}.notice{background:#fff6df;
        border-left:3px solid #bd8a25;padding:12px}.meta{color:#66738a;overflow-wrap:anywhere}
        @media(max-width:640px){body{padding:12px}header,section{padding:16px}h1{font-size:21px}
        h2{font-size:18px}nav a{padding:6px 8px}th,td{padding:8px;font-size:12px}}
        @media print{body{background:white;padding:0}nav{display:none}section{break-inside:avoid}}
    """
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        "style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\">"
        f"<title>{_value(title)}</title><style>{css}</style></head><body><header>"
        f'<p class="meta">CygnusX BioOps · 执行证据归档</p><h1>{_value(title)}</h1>'
        f'<p class="meta">Snapshot {_value(snapshot.snapshot_digest)} · '
        f"{_value(snapshot.schema_version)} · {_value(TEMPLATE_VERSION)}</p>"
        '<p class="notice">本报告记录可证明的执行证据及缺口；未执行复现验证。</p>'
        f"</header>{nav}{body}</body></html>"
    )

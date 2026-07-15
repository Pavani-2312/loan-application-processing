"""
src/app/pages/audit_detail.py

Read-only application audit view.
MD3: vertical event timeline stepper, tonal section cards, HTML audit package export.
"""
from __future__ import annotations

import json
from datetime import datetime

import streamlit as st

from src.app.ui_helpers import (
    band_badge,
    confidence_badge,
    fmt_score,
    get_uow_factory,
    md3_blur_shapes,
    render_sidebar,
    status_badge,
    truncate,
)
from src.repository import UnitOfWork

st.set_page_config(
    page_title="Loan Processing — Audit Detail",
    page_icon="🔎",
    layout="wide",
)

underwriter_id, role = render_sidebar()
st.markdown(md3_blur_shapes(), unsafe_allow_html=True)

application_id = st.session_state.get("review_application_id")
if not application_id:
    st.warning("No application selected.")
    st.stop()

factory = get_uow_factory()

with UnitOfWork(factory) as uow:
    app = uow.applications.get(application_id)
    if not app:
        st.error(f"Application {application_id} not found.")
        st.stop()
    extracted_all    = uow.extracted_fields.get_all_versions(application_id)
    scores_all       = uow.score_breakdowns.get_latest_revision(application_id, is_fairness_run=False)
    recs_all         = uow.recommendations.get_all(application_id)
    fairness         = uow.fairness_checks.get_latest(application_id)
    guardrail_flags  = uow.guardrail_flags.get_all(application_id)
    decisions        = uow.human_decisions.get_all(application_id)
    validation_results = uow.validation_results.get_all(application_id)
    audit_events     = uow.audit_logs.get_all_for_export(application_id)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
submitted_str = app.submitted_at.strftime("%Y-%m-%d %H:%M UTC") if app.submitted_at else "—"
latest_rec    = recs_all[-1] if recs_all else None

st.markdown(
    f'<div style="background:#F3EDF7;border-radius:28px;padding:1.75rem 2rem 1.5rem;'
    f'margin-bottom:1.5rem;box-shadow:0 1px 4px rgba(0,0,0,0.06);">'
    f'<div style="font-size:0.72rem;font-weight:500;letter-spacing:0.08em;'
    f'text-transform:uppercase;color:#6750A4;margin-bottom:6px;">Audit Detail</div>'
    f'<div style="display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:1rem;">'
    f'<div>'
    f'<h1 style="margin:0 0 4px;font-size:1.3rem;font-weight:500;color:#1C1B1F;">{app.applicant_name}</h1>'
    f'<p style="margin:0;font-size:0.82rem;color:#49454F;">{app.applicant_address}</p>'
    f'<p style="margin:4px 0 0;font-size:0.75rem;color:#79747E;">Submitted {submitted_str}</p>'
    f'</div>'
    f'<div style="text-align:right;">'
    f'{status_badge(app.status)}'
    + (f'<p style="font-size:0.78rem;color:#49454F;margin:4px 0 0;">'
       f'Rec: {band_badge(latest_rec.band)} · {fmt_score(latest_rec.composite_score)}</p>' if latest_rec else "")
    + f'</div></div></div>',
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Extracted fields
# ---------------------------------------------------------------------------
with st.expander("📄 Extracted Fields — all versions", expanded=False):
    if extracted_all:
        import pandas as pd
        ef_rows = [{
            "Field":      ef.field_name.replace("_"," ").title(),
            "Ver.":       ef.field_version,
            "Value":      ef.field_value or "—",
            "Confidence": ef.confidence or "—",
            "Evidence":   truncate(ef.evidence_span, 55),
            "Source":     ef.source_document or "—",
            "Verified":   "✅" if ef.manually_verified else "—",
            "Effective":  "✅" if ef.is_effective else "—",
        } for ef in extracted_all]
        st.dataframe(pd.DataFrame(ef_rows), use_container_width=True)
    else:
        st.caption("No extracted fields.")

# ---------------------------------------------------------------------------
# Score breakdown
# ---------------------------------------------------------------------------
with st.expander("📊 Score Breakdowns", expanded=True):
    if scores_all:
        import pandas as pd
        score_rows = [{
            "Rev.":        s.revision_number,
            "Factor":      s.factor,
            "Sub-factor":  s.sub_factor or "—",
            "Raw value":   f"{s.raw_value:.3f}" if s.raw_value is not None else "—",
            "Band":        s.band_label,
            "Score":       fmt_score(s.normalized_score),
            "Contribution":fmt_score(s.weighted_contribution),
            "Clause":      s.cited_clause_id,
            "Fairness run":"✅" if s.is_fairness_run else "—",
        } for s in scores_all]
        st.dataframe(pd.DataFrame(score_rows), use_container_width=True)
    else:
        st.caption("No scoring data.")

# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------
with st.expander("📝 Recommendations — all revisions", expanded=False):
    for r in recs_all:
        gen_str = r.generated_at.strftime("%Y-%m-%d %H:%M UTC") if r.generated_at else "—"
        st.markdown(
            f'<div style="background:#F3EDF7;border-radius:14px;padding:0.875rem 1.125rem;margin-bottom:0.5rem;">'
            f'<p style="margin:0 0 4px;font-weight:500;font-size:0.88rem;color:#1C1B1F;">'
            f'Revision {r.revision_number} · {band_badge(r.band)} · {fmt_score(r.composite_score)} · {gen_str}</p>'
            + (f'<p style="margin:0;font-size:0.82rem;color:#49454F;">{r.explanation_text}</p>' if r.explanation_text else "")
            + f'</div>',
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------------------------
# Fairness
# ---------------------------------------------------------------------------
with st.expander("⚖️ Identity-Blind Consistency Check", expanded=False):
    if fairness:
        color = "#C3EFAB" if fairness.result == "PASS" else "#F9DEDC"
        on    = "#0A2000" if fairness.result == "PASS" else "#410E0B"
        st.markdown(
            f'<div style="background:{color};border-radius:14px;padding:0.875rem 1.125rem;">'
            f'<p style="margin:0 0 4px;font-weight:500;font-size:0.9rem;color:{on};">'
            f'Result: {fairness.result}</p>'
            f'<p style="margin:0;font-size:0.82rem;color:{on};">'
            f'Original: {fairness.original_band} · Blind: {fairness.blind_band}</p>'
            + (f'<p style="margin:4px 0 0;font-size:0.8rem;color:{on};">{fairness.disparity_detail}</p>'
               if fairness.disparity_detail else "")
            + f'</div>',
            unsafe_allow_html=True,
        )
    else:
        st.caption("No fairness check data.")

# ---------------------------------------------------------------------------
# Guardrail
# ---------------------------------------------------------------------------
with st.expander("🚩 Guardrail Flags", expanded=False):
    if guardrail_flags:
        for gf in guardrail_flags:
            st.markdown(
                f'<div style="background:#F9DEDC;border-radius:12px;padding:0.75rem 1rem;margin-bottom:4px;">'
                f'<p style="margin:0 0 2px;font-weight:500;font-size:0.85rem;color:#410E0B;">{gf.field}</p>'
                f'<p style="margin:0;font-size:0.8rem;color:#6B2018;font-style:italic;">"{truncate(gf.excerpt,120)}"</p>'
                f'<p style="margin:2px 0 0;font-size:0.75rem;color:#410E0B;">{gf.reason}</p>'
                f'</div>',
                unsafe_allow_html=True,
            )
    else:
        st.caption("No guardrail flags.")

# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------
with st.expander("✍️ Decision History", expanded=True):
    if decisions:
        for d in decisions:
            decided_str = d.decided_at.strftime("%Y-%m-%d %H:%M UTC") if d.decided_at else "—"
            icon = "✅" if d.decision == "APPROVE" else ("❌" if d.decision == "DECLINE" else "🟣")
            term = "terminal" if d.is_terminal else "referral"
            match_lbl = "✅ Matched" if d.matches_recommendation else "⚠️ Override"
            st.markdown(
                f'<div style="background:#F3EDF7;border-radius:14px;padding:0.875rem 1.125rem;margin-bottom:4px;">'
                f'<p style="margin:0 0 2px;font-weight:500;font-size:0.9rem;color:#1C1B1F;">'
                f'#{d.sequence_number} {icon} {d.decision} <span style="font-weight:400;font-size:0.75rem;color:#49454F;">({term})</span></p>'
                f'<p style="margin:0;font-size:0.78rem;color:#49454F;">By {d.underwriter_id} · {decided_str} · {match_lbl}</p>'
                f'<p style="margin:2px 0 0;font-size:0.82rem;color:#1C1B1F;">{d.rationale}</p>'
                + (f'<p style="margin:2px 0 0;font-size:0.75rem;color:#6750A4;">{d.refer_reason.replace("_"," ").title()}</p>'
                   if d.refer_reason else "")
                + f'</div>',
                unsafe_allow_html=True,
            )
    else:
        st.caption("No decisions recorded yet.")

# ---------------------------------------------------------------------------
# Audit event timeline — vertical stepper
# ---------------------------------------------------------------------------
st.markdown(
    '<h2 style="font-size:1.1rem;font-weight:500;color:#1C1B1F;margin:1.5rem 0 0.75rem;">'
    '📋 Audit Event Timeline</h2>',
    unsafe_allow_html=True,
)

_EVENT_ICONS = {
    "INTAKE":                     ("📄", "#6750A4"),
    "VALIDATION_FAILED":          ("❌", "#B3261E"),
    "SCORED":                     ("📊", "#2563EB"),
    "FAIRNESS_CHECKED":           ("⚖️", "#625B71"),
    "RECOMMENDED":                ("📝", "#386A20"),
    "GUARDRAIL_FLAGGED":          ("🚩", "#B3261E"),
    "HUMAN_DECIDED":              ("✍️", "#7D5260"),
    "RESCORED_AFTER_VERIFICATION":("🔄", "#7D5700"),
}

if audit_events:
    for i, event in enumerate(audit_events):
        ts    = event.get("occurred_at", "—")
        etype = event.get("event_type", "—")
        payload = event.get("payload", {})
        icon, dot_color = _EVENT_ICONS.get(etype, ("⬜", "#79747E"))
        is_last = (i == len(audit_events) - 1)

        # Stepper row: dot + vertical line + content
        st.markdown(
            f'<div style="display:flex;gap:12px;margin-bottom:{"4px" if not is_last else "0"};">'
            # Left column: dot + line
            f'<div style="display:flex;flex-direction:column;align-items:center;min-width:28px;">'
            f'<div style="width:28px;height:28px;border-radius:50%;background:{dot_color}22;'
            f'display:flex;align-items:center;justify-content:center;font-size:0.85rem;'
            f'flex-shrink:0;">{icon}</div>'
            + (f'<div style="width:2px;flex:1;min-height:20px;background:#CAC4D0;margin:2px 0;"></div>'
               if not is_last else "")
            + f'</div>'
            # Right column: content
            f'<div style="background:#F3EDF7;border-radius:14px;padding:0.75rem 1rem;'
            f'margin-bottom:4px;flex:1;">'
            f'<p style="margin:0 0 2px;font-weight:500;font-size:0.85rem;color:{dot_color};">'
            f'{etype.replace("_"," ").title()}</p>'
            f'<p style="margin:0;font-size:0.72rem;color:#79747E;">{ts[:19] if ts != "—" else "—"}</p>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        # Expandable payload
        with st.expander(f"Payload — {etype}", expanded=False):
            st.json(payload)
else:
    st.caption("No audit events.")

st.divider()

# ---------------------------------------------------------------------------
# Audit package export
# ---------------------------------------------------------------------------
st.markdown(
    '<h2 style="font-size:1.05rem;font-weight:500;color:#1C1B1F;margin-bottom:4px;">📦 Audit Package</h2>'
    '<p style="font-size:0.82rem;color:#49454F;margin-bottom:0.75rem;">'
    'Self-contained HTML document for regulatory hand-off — no database access required to read it.</p>',
    unsafe_allow_html=True,
)

if st.button("Generate Audit Package (HTML) →", type="primary"):
    sections = []
    sections.append(f"<h1>Audit Package — Application {application_id}</h1>")
    sections.append(f"<p><strong>Applicant:</strong> {app.applicant_name}</p>")
    sections.append(f"<p><strong>Address:</strong> {app.applicant_address}</p>")
    sections.append(f"<p><strong>Submitted:</strong> {submitted_str}</p>")
    sections.append(f"<p><strong>Final Status:</strong> {app.status}</p>")
    sections.append(f"<p><em>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}</em></p>")

    sections.append("<hr><h2>Extracted Fields</h2><table border='1' cellpadding='4'>")
    sections.append("<tr><th>Field</th><th>Ver.</th><th>Value</th><th>Confidence</th><th>Evidence</th><th>Verified</th><th>Effective</th></tr>")
    for ef in extracted_all:
        sections.append(
            f"<tr><td>{ef.field_name}</td><td>{ef.field_version}</td>"
            f"<td>{ef.field_value or ''}</td><td>{ef.confidence or ''}</td>"
            f"<td>{ef.evidence_span or ''}</td>"
            f"<td>{'Yes' if ef.manually_verified else 'No'}</td>"
            f"<td>{'✓' if ef.is_effective else ''}</td></tr>"
        )
    sections.append("</table>")

    sections.append("<hr><h2>Score Breakdown</h2><table border='1' cellpadding='4'>")
    sections.append("<tr><th>Rev.</th><th>Factor</th><th>Sub-factor</th><th>Raw</th><th>Band</th><th>Score</th><th>Clause</th><th>Fairness run</th></tr>")
    for s in scores_all:
        sections.append(
            f"<tr><td>{s.revision_number}</td><td>{s.factor}</td><td>{s.sub_factor or ''}</td>"
            f"<td>{f'{s.raw_value:.3f}' if s.raw_value is not None else ''}</td>"
            f"<td>{s.band_label}</td><td>{s.normalized_score:.3f}</td>"
            f"<td>{s.cited_clause_id}</td><td>{'Yes' if s.is_fairness_run else 'No'}</td></tr>"
        )
    sections.append("</table>")

    sections.append("<hr><h2>Recommendations</h2>")
    for r in recs_all:
        gen_s = r.generated_at.strftime("%Y-%m-%d %H:%M UTC") if r.generated_at else "—"
        sections.append(f"<h3>Revision {r.revision_number} — {r.band} (score: {r.composite_score:.3f}) — {gen_s}</h3>")
        if r.explanation_text:
            sections.append(f"<p>{r.explanation_text}</p>")

    if fairness:
        sections.append("<hr><h2>Identity-Blind Consistency Check</h2>")
        sections.append(f"<p>Result: <strong>{fairness.result}</strong></p>")
        sections.append(f"<p>Original: {fairness.original_band} · Blind: {fairness.blind_band}</p>")
        if fairness.disparity_detail:
            sections.append(f"<p style='color:red;'>{fairness.disparity_detail}</p>")

    if guardrail_flags:
        sections.append("<hr><h2>Guardrail Flags</h2><ul>")
        for gf in guardrail_flags:
            sections.append(f"<li><strong>{gf.field}:</strong> {gf.excerpt} — {gf.reason}</li>")
        sections.append("</ul>")

    sections.append("<hr><h2>Decision History</h2><table border='1' cellpadding='4'>")
    sections.append("<tr><th>#</th><th>Decision</th><th>Terminal</th><th>By</th><th>At</th><th>Refer reason</th><th>Rationale</th><th>Matched rec</th></tr>")
    for d in decisions:
        ds = d.decided_at.strftime("%Y-%m-%d %H:%M UTC") if d.decided_at else "—"
        sections.append(
            f"<tr><td>{d.sequence_number}</td><td>{d.decision}</td>"
            f"<td>{'Yes' if d.is_terminal else 'No'}</td>"
            f"<td>{d.underwriter_id}</td><td>{ds}</td>"
            f"<td>{d.refer_reason or ''}</td><td>{d.rationale}</td>"
            f"<td>{'Yes' if d.matches_recommendation else 'No'}</td></tr>"
        )
    sections.append("</table>")

    sections.append("<hr><h2>Audit Event Timeline</h2>")
    for event in audit_events:
        ts2 = event.get("occurred_at", "—")
        et2 = event.get("event_type", "—")
        sections.append(f"<h3>{et2} — {ts2}</h3>")
        sections.append(f"<pre>{json.dumps(event.get('payload', {}), indent=2)}</pre>")

    html_body = "\n".join(sections)
    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Audit Package — {application_id}</title>
<style>
  body {{font-family:Roboto,Arial,sans-serif;margin:40px;color:#1C1B1F;background:#FFFBFE;}}
  h1 {{color:#6750A4;}} h2 {{color:#1C1B1F;border-bottom:1px solid #CAC4D0;padding-bottom:4px;}}
  table {{border-collapse:collapse;width:100%;margin-bottom:16px;}}
  th {{background:#F3EDF7;font-weight:500;}} td,th {{padding:6px 10px;text-align:left;}}
  pre {{background:#F3EDF7;padding:12px;border-radius:8px;overflow-x:auto;font-size:0.82rem;}}
</style>
</head>
<body>{html_body}</body>
</html>"""

    st.download_button(
        label="⬇️ Download Audit Package (HTML)",
        data=html_doc,
        file_name=f"audit_{application_id[:8]}_{datetime.now().strftime('%Y%m%d')}.html",
        mime="text/html",
    )

st.divider()
if st.button("← Back to Audit Explorer"):
    st.switch_page("pages/audit.py")

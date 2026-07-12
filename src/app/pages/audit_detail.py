"""
src/app/pages/audit_detail.py

Read-only application detail view for Audit Explorer.
Shows the full audit event timeline + Generate Audit Package button.
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

    extracted_all = uow.extracted_fields.get_all_versions(application_id)
    scores_all = uow.score_breakdowns.get_latest_revision(application_id, is_fairness_run=False)
    recs_all = uow.recommendations.get_all(application_id)
    fairness = uow.fairness_checks.get_latest(application_id)
    guardrail_flags = uow.guardrail_flags.get_all(application_id)
    decisions = uow.human_decisions.get_all(application_id)
    validation_results = uow.validation_results.get_all(application_id)
    audit_events = uow.audit_logs.get_all_for_export(application_id)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown(f"## 🔎 Audit Detail — {application_id[:16]}…")
col1, col2 = st.columns(2)
with col1:
    st.markdown(f"**Applicant:** {app.applicant_name}")
    st.markdown(f"**Address:** {app.applicant_address}")
    submitted_str = app.submitted_at.strftime("%Y-%m-%d %H:%M UTC") if app.submitted_at else "—"
    st.markdown(f"**Submitted:** {submitted_str}")
with col2:
    st.markdown(f"**Status:** {status_badge(app.status)}")
    if recs_all:
        latest_rec = recs_all[-1]
        st.markdown(f"**Recommendation:** {band_badge(latest_rec.band)} (score: {fmt_score(latest_rec.composite_score)})")

st.divider()

# ---------------------------------------------------------------------------
# Extracted fields — all versions
# ---------------------------------------------------------------------------
with st.expander("📄 Extracted Fields (all versions)", expanded=False):
    if extracted_all:
        import pandas as pd
        ef_rows = []
        for ef in extracted_all:
            ef_rows.append({
                "Field": ef.field_name.replace("_", " ").title(),
                "Version": ef.field_version,
                "Value": ef.field_value or "—",
                "Confidence": confidence_badge(ef.confidence),
                "Evidence span": truncate(ef.evidence_span, 60),
                "Source doc": ef.source_document or "—",
                "Verified": "✅ Yes" if ef.manually_verified else "No",
                "Effective": "✅" if ef.is_effective else "—",
            })
        st.dataframe(pd.DataFrame(ef_rows), use_container_width=True)
    else:
        st.caption("No extracted fields.")

# ---------------------------------------------------------------------------
# Score breakdowns — all revisions
# ---------------------------------------------------------------------------
with st.expander("📊 Score Breakdowns", expanded=True):
    if scores_all:
        import pandas as pd
        score_rows = [
            {
                "Revision": s.revision_number,
                "Factor": s.factor,
                "Sub-factor": s.sub_factor or "—",
                "Raw value": f"{s.raw_value:.3f}" if s.raw_value is not None else "—",
                "Band": s.band_label,
                "Score": fmt_score(s.normalized_score),
                "Contribution": fmt_score(s.weighted_contribution),
                "Clause": s.cited_clause_id,
                "Fairness run": "✅" if s.is_fairness_run else "No",
            }
            for s in scores_all
        ]
        st.dataframe(pd.DataFrame(score_rows), use_container_width=True)
    else:
        st.caption("No scoring data.")

# ---------------------------------------------------------------------------
# Recommendations — all revisions
# ---------------------------------------------------------------------------
with st.expander("📝 Recommendations (all revisions)", expanded=False):
    for r in recs_all:
        gen_str = r.generated_at.strftime("%Y-%m-%d %H:%M UTC") if r.generated_at else "—"
        st.markdown(f"**Revision {r.revision_number}** — {band_badge(r.band)} · score {fmt_score(r.composite_score)} · {gen_str}")
        if r.explanation_text:
            st.caption(r.explanation_text)

# ---------------------------------------------------------------------------
# Fairness check
# ---------------------------------------------------------------------------
with st.expander("⚖️ Identity-Blind Consistency Check", expanded=False):
    if fairness:
        st.markdown(f"Result: **{fairness.result}**")
        st.markdown(f"Original band: **{fairness.original_band}** · Blind band: **{fairness.blind_band}**")
        if fairness.disparity_detail:
            st.warning(fairness.disparity_detail)
    else:
        st.caption("No fairness check data.")

# ---------------------------------------------------------------------------
# Guardrail flags
# ---------------------------------------------------------------------------
with st.expander("🚩 Guardrail Flags", expanded=False):
    if guardrail_flags:
        for gf in guardrail_flags:
            st.markdown(f"- **{gf.field}:** {truncate(gf.excerpt, 100)} — *{gf.reason}*")
    else:
        st.caption("No guardrail flags.")

# ---------------------------------------------------------------------------
# Decision history
# ---------------------------------------------------------------------------
with st.expander("✍️ Decision History", expanded=True):
    if decisions:
        for d in decisions:
            decided_str = d.decided_at.strftime("%Y-%m-%d %H:%M UTC") if d.decided_at else "—"
            icon = "✅" if d.decision == "APPROVE" else ("🔴" if d.decision == "DECLINE" else "🟣")
            terminal_label = " *(terminal)*" if d.is_terminal else " *(non-terminal referral)*"
            st.markdown(f"**#{d.sequence_number}** {icon} **{d.decision}**{terminal_label}")
            cols = st.columns([1, 1, 2])
            with cols[0]:
                st.caption(f"By: {d.underwriter_id}")
            with cols[1]:
                st.caption(f"At: {decided_str}")
            with cols[2]:
                st.caption(f"Rationale: {d.rationale}")
            if d.refer_reason:
                st.caption(f"Refer reason: {d.refer_reason.replace('_', ' ').title()}")
            match_label = "✅ Matched recommendation" if d.matches_recommendation else "⚠️ Overrode recommendation"
            st.caption(match_label)
    else:
        st.caption("No decisions recorded yet.")

# ---------------------------------------------------------------------------
# Full audit event timeline
# ---------------------------------------------------------------------------
st.subheader("📋 Audit Event Timeline")
if audit_events:
    for event in audit_events:
        ts = event.get("occurred_at", "—")
        etype = event.get("event_type", "—")
        payload = event.get("payload", {})
        with st.expander(f"`{etype}` — {ts}", expanded=False):
            st.json(payload)
else:
    st.caption("No audit events.")

st.divider()

# ---------------------------------------------------------------------------
# Generate Audit Package (PDF/HTML self-contained export)
# ---------------------------------------------------------------------------
st.subheader("📦 Generate Audit Package")
st.caption(
    "Exports everything about this application as a standalone document "
    "suitable for handing to a regulator — no database access required to read it."
)

if st.button("📄 Generate Audit Package (HTML)", type="primary"):
    # Build the self-contained HTML audit package
    sections = []

    sections.append(f"<h1>Audit Package — Application {application_id}</h1>")
    sections.append(f"<p><strong>Applicant:</strong> {app.applicant_name}</p>")
    sections.append(f"<p><strong>Address:</strong> {app.applicant_address}</p>")
    submitted_str2 = app.submitted_at.strftime("%Y-%m-%d %H:%M UTC") if app.submitted_at else "—"
    sections.append(f"<p><strong>Submitted:</strong> {submitted_str2}</p>")
    sections.append(f"<p><strong>Final Status:</strong> {app.status}</p>")
    sections.append(f"<p><em>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}</em></p>")

    sections.append("<hr><h2>Extracted Fields (all versions)</h2><table border='1' cellpadding='4'>")
    sections.append("<tr><th>Field</th><th>Version</th><th>Value</th><th>Confidence</th><th>Evidence</th><th>Verified</th><th>Effective</th></tr>")
    for ef in extracted_all:
        verified = "Yes" if ef.manually_verified else "No"
        effective = "✓" if ef.is_effective else ""
        sections.append(
            f"<tr><td>{ef.field_name}</td><td>{ef.field_version}</td>"
            f"<td>{ef.field_value or ''}</td><td>{ef.confidence or ''}</td>"
            f"<td>{ef.evidence_span or ''}</td><td>{verified}</td><td>{effective}</td></tr>"
        )
    sections.append("</table>")

    sections.append("<hr><h2>Score Breakdown</h2><table border='1' cellpadding='4'>")
    sections.append("<tr><th>Revision</th><th>Factor</th><th>Sub-factor</th><th>Raw</th><th>Band</th><th>Score</th><th>Clause</th><th>Fairness run</th></tr>")
    for s in scores_all:
        sections.append(
            f"<tr><td>{s.revision_number}</td><td>{s.factor}</td><td>{s.sub_factor or ''}</td>"
            f"<td>{s.raw_value:.3f if s.raw_value is not None else ''}</td>"
            f"<td>{s.band_label}</td><td>{s.normalized_score:.3f}</td>"
            f"<td>{s.cited_clause_id}</td><td>{'Yes' if s.is_fairness_run else 'No'}</td></tr>"
        )
    sections.append("</table>")

    sections.append("<hr><h2>Recommendations</h2>")
    for r in recs_all:
        gen_str2 = r.generated_at.strftime("%Y-%m-%d %H:%M UTC") if r.generated_at else "—"
        sections.append(f"<h3>Revision {r.revision_number} — {r.band} (score: {r.composite_score:.3f}) — {gen_str2}</h3>")
        if r.explanation_text:
            sections.append(f"<p>{r.explanation_text}</p>")

    if fairness:
        sections.append("<hr><h2>Identity-Blind Consistency Check</h2>")
        sections.append(f"<p>Result: <strong>{fairness.result}</strong></p>")
        sections.append(f"<p>Original band: {fairness.original_band} · Blind band: {fairness.blind_band}</p>")
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
        decided_str3 = d.decided_at.strftime("%Y-%m-%d %H:%M UTC") if d.decided_at else "—"
        sections.append(
            f"<tr><td>{d.sequence_number}</td><td>{d.decision}</td>"
            f"<td>{'Yes' if d.is_terminal else 'No'}</td>"
            f"<td>{d.underwriter_id}</td><td>{decided_str3}</td>"
            f"<td>{d.refer_reason or ''}</td><td>{d.rationale}</td>"
            f"<td>{'Yes' if d.matches_recommendation else 'No'}</td></tr>"
        )
    sections.append("</table>")

    sections.append("<hr><h2>Audit Event Timeline</h2>")
    for event in audit_events:
        ts = event.get("occurred_at", "—")
        etype = event.get("event_type", "—")
        payload = event.get("payload", {})
        sections.append(f"<h3>{etype} — {ts}</h3>")
        sections.append(f"<pre>{json.dumps(payload, indent=2)}</pre>")

    html_body = "\n".join(sections)
    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Audit Package — {application_id}</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 40px; color: #111; }}
  h1 {{ color: #1e3a5f; }}
  h2 {{ color: #2563eb; border-bottom: 2px solid #e5e7eb; padding-bottom: 4px; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 16px; }}
  th {{ background: #f3f4f6; }}
  td, th {{ padding: 6px 10px; text-align: left; }}
  pre {{ background: #f9fafb; padding: 12px; border-radius: 4px; overflow-x: auto; }}
</style>
</head>
<body>
{html_body}
</body>
</html>"""

    st.download_button(
        label="⬇️ Download Audit Package (HTML)",
        data=html_doc,
        file_name=f"audit_package_{application_id[:8]}_{datetime.now().strftime('%Y%m%d')}.html",
        mime="text/html",
    )

st.divider()
if st.button("← Back to Audit Explorer"):
    st.switch_page("src/app/pages/audit.py")

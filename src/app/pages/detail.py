"""
src/app/pages/detail.py

Screen 3 — Application Detail & Decision
MD3: recommendation hero card with band accent, tonal score table,
glass-morphism fairness panel, extracted fields list, MD3 decision form.
"""
from __future__ import annotations

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
    page_title="Loan Processing — Application Detail",
    page_icon="📋",
    layout="wide",
)

underwriter_id, role = render_sidebar()
st.markdown(md3_blur_shapes(), unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Application ID from session state
# ---------------------------------------------------------------------------
application_id = st.session_state.get("review_application_id")
if not application_id:
    st.markdown(
        '<div style="background:#F3EDF7;border-radius:24px;padding:2rem;text-align:center;color:#49454F;">'
        'No application selected. Go to the Review Queue.</div>',
        unsafe_allow_html=True,
    )
    if st.button("← Review Queue"):
        st.switch_page("pages/queue.py")
    st.stop()

factory = get_uow_factory()

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
with UnitOfWork(factory) as uow:
    app = uow.applications.get(application_id)
    if not app:
        st.error(f"Application {application_id} not found.")
        st.stop()
    extracted_all      = uow.extracted_fields.get_all_versions(application_id)
    extracted_effective= uow.extracted_fields.get_effective_fields(application_id)
    validation_results = uow.validation_results.get_all(application_id)
    scores             = uow.score_breakdowns.get_latest_revision(application_id, is_fairness_run=False)
    rec                = uow.recommendations.get_latest(application_id)
    fairness           = uow.fairness_checks.get_latest(application_id)
    guardrail_flags    = uow.guardrail_flags.get_all(application_id)
    decisions          = uow.human_decisions.get_all(application_id)
    terminal_decision  = uow.human_decisions.get_terminal_decision(application_id)
    all_recs           = uow.recommendations.get_all(application_id)

# ---------------------------------------------------------------------------
# 1. Page header
# ---------------------------------------------------------------------------
submitted_str = app.submitted_at.strftime("%Y-%m-%d %H:%M UTC") if app.submitted_at else "—"

st.markdown(
    f'<div style="background:#F3EDF7;border-radius:28px;padding:1.75rem 2rem 1.5rem;'
    f'margin-bottom:1.5rem;box-shadow:0 1px 4px rgba(0,0,0,0.06);">'
    f'<div style="font-size:0.72rem;font-weight:500;letter-spacing:0.08em;'
    f'text-transform:uppercase;color:#6750A4;margin-bottom:6px;">Application Detail</div>'
    f'<div style="display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:1rem;">'
    f'<div>'
    f'<h1 style="margin:0 0 4px;font-size:1.35rem;font-weight:500;color:#1C1B1F;'
    f'font-family:Roboto,sans-serif;">{app.applicant_name}</h1>'
    f'<p style="margin:0;font-size:0.85rem;color:#49454F;">{app.applicant_address}</p>'
    f'<p style="margin:4px 0 0;font-size:0.78rem;color:#79747E;">Submitted {submitted_str} · '
    f'<code style="background:#E7E0EC;padding:1px 6px;border-radius:6px;font-size:0.75rem;">'
    f'{application_id[:16]}…</code></p>'
    f'</div>'
    f'<div style="display:flex;align-items:center;gap:8px;">'
    f'{status_badge(app.status)}'
    f'</div>'
    f'</div>'
    f'</div>',
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# 2. Guardrail banner
# ---------------------------------------------------------------------------
if guardrail_flags:
    flag = guardrail_flags[0]
    st.markdown(
        f'<div style="background:#F9DEDC;border-left:4px solid #B3261E;border-radius:0 16px 16px 0;'
        f'padding:1rem 1.25rem;margin-bottom:1rem;">'
        f'<p style="margin:0 0 4px;font-weight:500;color:#410E0B;font-size:0.9rem;">'
        f'🚩 Guardrail alert — field: <code>{flag.field}</code></p>'
        f'<p style="margin:0;font-size:0.82rem;color:#410E0B;font-style:italic;">'
        f'"{truncate(flag.excerpt, 120)}"</p>'
        f'<p style="margin:4px 0 0;font-size:0.78rem;color:#6B2018;">'
        f'This content was ignored. The recommendation below is based solely on policy scoring.</p>'
        f'</div>',
        unsafe_allow_html=True,
    )
    if len(guardrail_flags) > 1:
        with st.expander(f"View all {len(guardrail_flags)} guardrail flags"):
            for gf in guardrail_flags:
                st.markdown(f"- **{gf.field}:** {truncate(gf.excerpt, 100)} — *{gf.reason}*")

# ---------------------------------------------------------------------------
# 3. Recommendation hero card
# ---------------------------------------------------------------------------
_BAND_HERO = {
    "APPROVE":  {"bg": "#C3EFAB", "on": "#0A2000", "accent": "#386A20", "icon": "✅"},
    "REFER":    {"bg": "#FFDDB3", "on": "#271900", "accent": "#7D5700", "icon": "⚠️"},
    "DECLINE":  {"bg": "#F9DEDC", "on": "#410E0B", "accent": "#B3261E", "icon": "❌"},
}

if rec:
    bc = _BAND_HERO.get(rec.band, {"bg": "#E7E0EC", "on": "#1C1B1F", "accent": "#79747E", "icon": "—"})
    rev_note = (
        f'<p style="font-size:0.75rem;color:{bc["accent"]};margin:8px 0 0;opacity:0.8;">'
        f'Revision {rec.revision_number} of {len(all_recs)} — re-scored after field correction</p>'
        if len(all_recs) > 1 else ""
    )
    st.markdown(
        f'<div style="background:{bc["bg"]};border-radius:24px;padding:1.75rem 2rem;'
        f'margin-bottom:1.25rem;border-left:5px solid {bc["accent"]};">'
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">'
        f'<span style="font-size:1.5rem;">{bc["icon"]}</span>'
        f'<span style="font-size:1.4rem;font-weight:500;color:{bc["on"]};font-family:Roboto,sans-serif;">'
        f'{rec.band}</span>'
        f'<span style="font-size:0.85rem;color:{bc["accent"]};margin-left:4px;">'
        f'Composite score: <strong>{fmt_score(rec.composite_score)}</strong></span>'
        f'</div>'
        f'<p style="margin:0;font-size:0.92rem;color:{bc["on"]};line-height:1.6;">'
        f'{rec.explanation_text or "No explanation generated."}</p>'
        f'{rev_note}'
        f'</div>',
        unsafe_allow_html=True,
    )
elif app.status in ("AWAITING_DOCUMENTS", "INCONSISTENT_DOCUMENTS", "NEEDS_MANUAL_VERIFICATION"):
    st.info(f"No recommendation yet — application is in status **{app.status.replace('_',' ').title()}**.")
else:
    st.info("No recommendation available.")

# ---------------------------------------------------------------------------
# 4. Score breakdown table
# ---------------------------------------------------------------------------
if scores:
    st.markdown(
        '<h2 style="font-size:1.1rem;font-weight:500;color:#1C1B1F;margin:1.5rem 0 0.75rem;">'
        '📊 Policy Score Breakdown</h2>',
        unsafe_allow_html=True,
    )

    factor_rows = [s for s in scores if s.sub_factor is None]
    subfactor_rows = [s for s in scores if s.sub_factor is not None]

    import pandas as pd
    display_rows = []
    for s in factor_rows:
        factor_label = s.factor.replace("_", " ").title()
        raw_display = f"{s.raw_value:.2f}" if s.raw_value is not None else "—"
        if s.factor == "income_stability":
            tf = next((x for x in subfactor_rows if x.sub_factor == "tenure"), None)
            vf = next((x for x in subfactor_rows if x.sub_factor == "variability"), None)
            if tf and vf:
                raw_display = f"{int(tf.raw_value)}mo / {vf.raw_value:.0f}% var"
        display_rows.append({
            "Factor":       factor_label,
            "Weight":       f"{s.weight*100:.0f}%",
            "Raw value":    raw_display,
            "Band":         s.band_label.replace("_", " ").title(),
            "Score":        fmt_score(s.normalized_score),
            "Contribution": fmt_score(s.weighted_contribution),
            "Policy clause":s.cited_clause_id,
        })
    if rec:
        display_rows.append({
            "Factor":       "Composite",
            "Weight":       "",
            "Raw value":    "",
            "Band":         "",
            "Score":        "",
            "Contribution": fmt_score(rec.composite_score),
            "Policy clause":f"→ {rec.band}",
        })

    st.table(pd.DataFrame(display_rows))

# ---------------------------------------------------------------------------
# 5. Fairness panel — glass-morphism card on tonal background
# ---------------------------------------------------------------------------
if fairness:
    st.markdown(
        '<h2 style="font-size:1.1rem;font-weight:500;color:#1C1B1F;margin:1.5rem 0 0.75rem;">'
        '⚖️ Identity-Blind Consistency Check</h2>',
        unsafe_allow_html=True,
    )
    if fairness.result == "PASS":
        inner = (
            '<div style="display:flex;align-items:center;gap:8px;">'
            '<span style="font-size:1.1rem;">✅</span>'
            '<span style="font-weight:500;color:#0A2000;">No disparity detected</span>'
            '</div>'
            '<p style="margin:6px 0 0;font-size:0.85rem;color:#1C1B1F;opacity:0.8;">'
            'Recommendation unchanged after removing identity fields from re-extraction.</p>'
        )
        bg, border = "#C3EFAB", "#386A20"
    else:
        inner = (
            f'<div style="display:flex;align-items:center;gap:8px;">'
            f'<span style="font-size:1.1rem;">⚠️</span>'
            f'<span style="font-weight:500;color:#410E0B;">Disparity detected</span>'
            f'</div>'
            f'<p style="margin:4px 0;font-size:0.85rem;color:#410E0B;">'
            f'Original: <strong>{fairness.original_band}</strong> → '
            f'Identity-blind: <strong>{fairness.blind_band}</strong></p>'
            f'<p style="margin:0;font-size:0.82rem;color:#6B2018;">{fairness.disparity_detail or ""}</p>'
        )
        bg, border = "#F9DEDC", "#B3261E"

    scope_note = (
        '<p style="margin:8px 0 0;font-size:0.72rem;color:#49454F;font-style:italic;">'
        'Scope: single-application extraction consistency check only — not a population-level '
        'disparate-impact audit. See Known Limitations (L2).</p>'
    )
    st.markdown(
        f'<div style="background:{bg};border-radius:20px;padding:1.25rem 1.5rem;'
        f'border-left:4px solid {border};margin-bottom:1rem;">'
        f'{inner}{scope_note}</div>',
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# 6. Document validation
# ---------------------------------------------------------------------------
if validation_results:
    with st.expander("📄 Document Validation Checks", expanded=False):
        for vr in validation_results:
            icon = "✅" if vr.passed else "❌"
            st.markdown(f"{icon} **{vr.check_name.replace('_',' ').title()}**")
            if vr.evidence:
                st.caption(f"  {vr.evidence}")

# ---------------------------------------------------------------------------
# 6a. Extracted fields
# ---------------------------------------------------------------------------
st.markdown(
    '<h2 style="font-size:1.1rem;font-weight:500;color:#1C1B1F;margin:1.5rem 0 4px;">'
    '🔍 Extracted Fields</h2>'
    '<p style="font-size:0.82rem;color:#49454F;margin-bottom:0.75rem;">'
    'Fields extracted from your documents with source, evidence, and confidence. '
    'Low-confidence scoring fields can be corrected below.</p>',
    unsafe_allow_html=True,
)

SCORING_RELEVANT = {
    "stated_monthly_income", "total_monthly_obligations", "bureau_score",
    "employment_tenure_months", "income_variability_pct", "average_monthly_deposits",
}

if extracted_effective:
    # Table header
    hcols = st.columns([1.5, 1.2, 1.0, 2.2, 0.8, 1.4])
    for col, lbl in zip(hcols, ["Field", "Value", "Source", "Evidence", "Confidence", "Action"]):
        col.markdown(
            f'<p style="font-size:0.72rem;font-weight:500;text-transform:uppercase;'
            f'letter-spacing:0.06em;color:#79747E;margin:0 0 6px;">{lbl}</p>',
            unsafe_allow_html=True,
        )

    for field_name, field_row in sorted(extracted_effective.items()):
        needs_correction = (
            field_row.confidence == "low"
            and field_name in SCORING_RELEVANT
            and app.status == "NEEDS_MANUAL_VERIFICATION"
        )
        all_versions_for_field = [
            r for r in extracted_all
            if r.field_name == field_name and r.field_version < field_row.field_version
        ]

        row_bg = "background:#FFDDB3;border-radius:12px;padding:6px 8px;" if needs_correction else ""

        col_fn, col_val, col_src, col_ev, col_conf, col_act = st.columns([1.5, 1.2, 1.0, 2.2, 0.8, 1.4])

        with col_fn:
            label = field_name.replace("_", " ").title()
            prefix = "⚠️ " if needs_correction else ""
            weight = "font-weight:600;" if needs_correction else ""
            st.markdown(
                f'<p style="margin:0;font-size:0.85rem;{weight}color:#1C1B1F;">{prefix}{label}</p>',
                unsafe_allow_html=True,
            )
        with col_val:
            st.markdown(
                f'<p style="margin:0;font-size:0.85rem;font-family:monospace;color:#1C1B1F;">'
                f'{field_row.field_value or "—"}</p>',
                unsafe_allow_html=True,
            )
        with col_src:
            st.markdown(
                f'<p style="margin:0;font-size:0.78rem;color:#49454F;">{field_row.source_document or "—"}</p>',
                unsafe_allow_html=True,
            )
        with col_ev:
            ev = truncate(field_row.evidence_span, 55)
            st.markdown(
                f'<p style="margin:0;font-size:0.78rem;color:#49454F;font-style:italic;">"{ev}"</p>',
                unsafe_allow_html=True,
            )
        with col_conf:
            st.markdown(confidence_badge(field_row.confidence), unsafe_allow_html=True)
        with col_act:
            if all_versions_for_field:
                st.markdown(
                    f'<p style="font-size:0.72rem;color:#79747E;margin:0;">{len(all_versions_for_field)} prior</p>',
                    unsafe_allow_html=True,
                )
            if needs_correction:
                if st.button("✏️ Correct", key=f"correct_{field_name}"):
                    st.session_state[f"correcting_{field_name}"] = True

        # Inline correction form
        if st.session_state.get(f"correcting_{field_name}"):
            with st.form(key=f"correction_form_{field_name}"):
                st.markdown(
                    f'<p style="font-weight:500;margin-bottom:4px;color:#1C1B1F;">'
                    f'Correct: {field_name.replace("_"," ").title()}</p>'
                    f'<p style="font-size:0.8rem;color:#49454F;">Original: '
                    f'<code>{field_row.field_value}</code> · Evidence: <em>{field_row.evidence_span}</em></p>',
                    unsafe_allow_html=True,
                )
                corrected_value  = st.text_input("Corrected value", value=field_row.field_value or "")
                correction_reason= st.text_input("Reason / source reference")
                col_s, col_c = st.columns(2)
                save_correction = col_s.form_submit_button("Save & Re-score", type="primary")
                cancel          = col_c.form_submit_button("Cancel")

            if cancel:
                del st.session_state[f"correcting_{field_name}"]
                st.rerun()

            if save_correction and corrected_value:
                with UnitOfWork(factory) as uow:
                    uow.extracted_fields.upsert_field(
                        application_id=application_id,
                        field_name=field_name,
                        field_value=corrected_value,
                        source_document=field_row.source_document,
                        confidence=None,
                        evidence_span=correction_reason or "Manually corrected by underwriter",
                        manually_verified=True,
                    )
                    uow.audit_logs.append(application_id, "RESCORED_AFTER_VERIFICATION", {
                        "corrected_field_name": field_name,
                        "previous_value": field_row.field_value,
                        "new_value": corrected_value,
                        "triggering_underwriter_id": underwriter_id,
                    })
                    uow.commit()
                del st.session_state[f"correcting_{field_name}"]
                with st.spinner("Re-scoring with confirmed values…"):
                    try:
                        from src.agent.graph import resume_from_scoring
                        resume_from_scoring(application_id, underwriter_id)
                        st.success("Re-scoring complete.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Re-scoring failed: {e}")
else:
    st.info("No extracted fields available yet.")

st.divider()

# ---------------------------------------------------------------------------
# 7. Decision history
# ---------------------------------------------------------------------------
if decisions:
    st.markdown(
        '<h2 style="font-size:1.1rem;font-weight:500;color:#1C1B1F;margin-bottom:0.75rem;">'
        '📜 Decision History</h2>',
        unsafe_allow_html=True,
    )
    for d in decisions:
        decided_str = d.decided_at.strftime("%Y-%m-%d %H:%M UTC") if d.decided_at else "—"
        icon = "✅" if d.decision == "APPROVE" else ("❌" if d.decision == "DECLINE" else "🟣")
        term = " · terminal" if d.is_terminal else " · referral"
        st.markdown(
            f'<div style="background:#F3EDF7;border-radius:16px;padding:0.875rem 1.25rem;'
            f'margin-bottom:0.5rem;">'
            f'<p style="margin:0 0 4px;font-weight:500;font-size:0.9rem;color:#1C1B1F;">'
            f'{icon} {d.decision}<span style="font-weight:400;color:#49454F;font-size:0.78rem;">{term}</span></p>'
            f'<p style="margin:0;font-size:0.78rem;color:#49454F;">'
            f'By {d.underwriter_id} · {decided_str}</p>'
            f'<p style="margin:2px 0 0;font-size:0.82rem;color:#1C1B1F;">{d.rationale}</p>'
            + (f'<p style="margin:2px 0 0;font-size:0.78rem;color:#6750A4;">'
               f'Refer reason: {d.refer_reason.replace("_"," ").title()}</p>' if d.refer_reason else "")
            + f'</div>',
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------------------------
# 8. Decision form
# ---------------------------------------------------------------------------
_can_decide = app.status in ("PENDING_HUMAN_REVIEW", "REFERRED_FOR_ESCALATION")

if _can_decide:
    st.markdown(
        '<h2 style="font-size:1.1rem;font-weight:500;color:#1C1B1F;margin-bottom:4px;">'
        '✍️ Record Decision</h2>'
        f'<p style="font-size:0.78rem;color:#49454F;margin-bottom:1rem;">'
        f'Deciding as: <strong>{underwriter_id}</strong> · Demo mode — identity not verified</p>',
        unsafe_allow_html=True,
    )

    with st.form("decision_form"):
        decision_choice = st.radio(
            "Decision *",
            options=["— Select —", "APPROVE", "REFER", "DECLINE"],
            horizontal=True,
        )
        refer_reason = None
        if decision_choice == "REFER":
            refer_reason = st.selectbox(
                "Refer reason * (required)",
                ["REQUEST_MORE_INFO", "ESCALATE_TO_SENIOR_UNDERWRITER", "ESCALATE_TO_COMMITTEE"],
            )
            st.markdown(
                '<div style="background:#E8DEF8;border-radius:12px;padding:8px 14px;'
                'font-size:0.82rem;color:#1D192B;margin-top:4px;">'
                'ℹ️ This does not close the application — it will return to the queue.</div>',
                unsafe_allow_html=True,
            )

        rationale = st.text_area(
            "Rationale * (required)",
            placeholder="Explain the basis for this decision.",
            height=100,
        )

        if rec and decision_choice not in ("— Select —", None) and decision_choice != rec.band:
            st.markdown(
                f'<div style="background:#FFDDB3;border-radius:12px;padding:8px 14px;'
                f'font-size:0.82rem;color:#5C3C00;margin-top:4px;">'
                f'⚠️ This differs from the system recommendation ({rec.band}). '
                f'Rationale is required and will be recorded in the audit log.</div>',
                unsafe_allow_html=True,
            )

        submit_decision = st.form_submit_button("Record Decision →", type="primary")

    if submit_decision:
        if not rationale or not rationale.strip():
            st.error("Rationale is required.")
        elif decision_choice == "— Select —":
            st.error("Please select a decision.")
        else:
            try:
                from src.agent.human_gate import HumanDecisionError, record_human_decision
                result = record_human_decision(
                    application_id=application_id,
                    underwriter_id=underwriter_id,
                    decision=decision_choice,
                    rationale=rationale,
                    refer_reason=refer_reason if decision_choice == "REFER" else None,
                )
                if result["is_terminal"]:
                    st.success(
                        f"✅ **{decision_choice}** recorded "
                        f"(Decision ID: {result['decision_id'][:8]}…). Application is now DECIDED."
                    )
                else:
                    st.success(
                        f"🟣 Referral recorded: **{decision_choice}** — {refer_reason}. "
                        f"Application returned to queue."
                    )
                st.rerun()
            except Exception as e:
                st.error(f"Decision error: {e}")

elif terminal_decision:
    decided_str = terminal_decision.decided_at.strftime("%Y-%m-%d %H:%M UTC") if terminal_decision.decided_at else "—"
    st.markdown(
        f'<div style="background:#C3EFAB;border-radius:20px;padding:1.25rem 1.5rem;">'
        f'<p style="margin:0 0 4px;font-weight:500;font-size:1rem;color:#0A2000;">'
        f'✅ Final Decision: {terminal_decision.decision}</p>'
        f'<p style="margin:0;font-size:0.82rem;color:#0A2000;">'
        f'By {terminal_decision.underwriter_id} · {decided_str}</p>'
        f'<p style="margin:4px 0 0;font-size:0.85rem;color:#1C1B1F;">{terminal_decision.rationale}</p>'
        f'</div>',
        unsafe_allow_html=True,
    )
else:
    st.info(f"Application is in status **{app.status.replace('_',' ').title()}** — no decision action available.")

st.divider()
if st.button("← Back to Queue"):
    st.switch_page("pages/queue.py")

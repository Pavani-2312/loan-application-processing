"""
src/app/pages/detail.py

Screen 3 — Application Detail & Decision (core screen)
Recommendation, evidence, fairness check, extracted fields, decision capture.
"""
from __future__ import annotations

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
    page_title="Loan Processing — Application Detail",
    page_icon="📋",
    layout="wide",
)

underwriter_id, role = render_sidebar()

# ---------------------------------------------------------------------------
# Application ID from session state or query param
# ---------------------------------------------------------------------------
application_id = st.session_state.get("review_application_id")
if not application_id:
    st.warning("No application selected. Go to the Review Queue.")
    if st.button("← Review Queue"):
        st.switch_page("pages/queue.py")
    st.stop()

factory = get_uow_factory()

# ---------------------------------------------------------------------------
# Load all data for this application
# ---------------------------------------------------------------------------
with UnitOfWork(factory) as uow:
    app = uow.applications.get(application_id)
    if not app:
        st.error(f"Application {application_id} not found.")
        st.stop()

    extracted_all = uow.extracted_fields.get_all_versions(application_id)
    extracted_effective = uow.extracted_fields.get_effective_fields(application_id)
    validation_results = uow.validation_results.get_all(application_id)
    scores = uow.score_breakdowns.get_latest_revision(application_id, is_fairness_run=False)
    rec = uow.recommendations.get_latest(application_id)
    fairness = uow.fairness_checks.get_latest(application_id)
    guardrail_flags = uow.guardrail_flags.get_all(application_id)
    decisions = uow.human_decisions.get_all(application_id)
    terminal_decision = uow.human_decisions.get_terminal_decision(application_id)
    all_recs = uow.recommendations.get_all(application_id)

# ---------------------------------------------------------------------------
# 1. Header band
# ---------------------------------------------------------------------------
st.markdown(f"## Application {application_id[:12]}…")
col_h1, col_h2, col_h3 = st.columns([2, 2, 1.5])
with col_h1:
    st.markdown(f"**Applicant:** {app.applicant_name}")
    st.markdown(f"**Address:** {app.applicant_address}")
with col_h2:
    submitted_str = app.submitted_at.strftime("%Y-%m-%d %H:%M UTC") if app.submitted_at else "—"
    st.markdown(f"**Submitted:** {submitted_str}")
with col_h3:
    st.markdown(f"**Status:** {status_badge(app.status)}")

st.divider()

# ---------------------------------------------------------------------------
# 2. Guardrail banner (only if flags present)
# ---------------------------------------------------------------------------
if guardrail_flags:
    flag = guardrail_flags[0]
    st.error(
        f"🚩 **Guardrail alert:** This application contains content that appears to instruct "
        f"the system to bypass policy in field **{flag.field}**: "
        f"*\"{truncate(flag.excerpt, 120)}\"*\n\n"
        f"**This has been ignored.** The recommendation below is based solely on policy scoring."
    )
    if len(guardrail_flags) > 1:
        with st.expander(f"View all {len(guardrail_flags)} guardrail flags"):
            for gf in guardrail_flags:
                st.markdown(f"- **{gf.field}:** {truncate(gf.excerpt, 100)} — *{gf.reason}*")

# ---------------------------------------------------------------------------
# 3. Recommendation card
# ---------------------------------------------------------------------------
if rec:
    band_color = {"APPROVE": "#16a34a", "REFER": "#d97706", "DECLINE": "#dc2626"}.get(rec.band, "#6b7280")
    st.markdown(
        f"""
        <div style="background:{band_color}15; border-left:5px solid {band_color};
                    padding:16px 20px; border-radius:6px; margin-bottom:12px;">
            <h2 style="color:{band_color}; margin:0;">{band_badge(rec.band)}</h2>
            <p style="font-size:1.1rem; margin:4px 0;">
                Composite policy score: <strong>{fmt_score(rec.composite_score)}</strong>
            </p>
            <p style="color:#374151; margin:0;">{rec.explanation_text or "No explanation generated."}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if len(all_recs) > 1:
        st.caption(f"Revision {rec.revision_number} of {len(all_recs)} (application was re-scored after manual field correction)")
elif app.status in ("AWAITING_DOCUMENTS", "INCONSISTENT_DOCUMENTS", "NEEDS_MANUAL_VERIFICATION"):
    st.info(f"No recommendation yet — application is in status **{status_badge(app.status)}**.")
else:
    st.info("No recommendation available.")

# ---------------------------------------------------------------------------
# 4. Score breakdown table
# ---------------------------------------------------------------------------
if scores:
    st.subheader("📊 Policy Score Breakdown")
    # Separate main factor rows from sub-factor rows
    factor_rows = [s for s in scores if s.sub_factor is None]
    subfactor_rows = [s for s in scores if s.sub_factor is not None]

    # Build display rows
    display_rows = []
    for s in factor_rows:
        factor_label = s.factor.replace("_", " ").title()
        raw_display = f"{s.raw_value:.2f}" if s.raw_value is not None else "—"
        if s.factor == "income_stability":
            tenure_sf = next((x for x in subfactor_rows if x.sub_factor == "tenure"), None)
            variability_sf = next((x for x in subfactor_rows if x.sub_factor == "variability"), None)
            raw_display = (
                f"{int(tenure_sf.raw_value)}mo / {variability_sf.raw_value:.0f}% var"
                if tenure_sf and variability_sf else raw_display
            )
        display_rows.append({
            "Factor": factor_label,
            "Weight": f"{s.weight*100:.0f}%",
            "Raw value": raw_display,
            "Band": s.band_label.replace("_", " ").title(),
            "Score": fmt_score(s.normalized_score),
            "Contribution": fmt_score(s.weighted_contribution),
            "Policy clause": s.cited_clause_id,
        })

    if rec:
        display_rows.append({
            "Factor": "**Composite**",
            "Weight": "",
            "Raw value": "",
            "Band": "",
            "Score": "",
            "Contribution": f"**{fmt_score(rec.composite_score)}**",
            "Policy clause": f"→ {rec.band} (Clause 7.1/7.2/7.3)",
        })

    import pandas as pd
    st.table(pd.DataFrame(display_rows))

# ---------------------------------------------------------------------------
# 5. Identity-Blind Consistency Check panel
# ---------------------------------------------------------------------------
if fairness:
    st.subheader("⚖️ Identity-Blind Consistency Check")
    col_f1, col_f2, col_f3 = st.columns([0.05, 2, 1])
    with col_f2:
        if fairness.result == "PASS":
            st.success("✅ No disparity detected — recommendation unchanged after removing identity fields.")
        else:
            st.error(
                f"⚠️ **Disparity detected:** Original = **{fairness.original_band}** · "
                f"Identity-blind = **{fairness.blind_band}**\n\n"
                f"{fairness.disparity_detail or ''}"
            )
    with col_f3:
        with st.expander("ℹ️ Scope note"):
            st.caption(
                "This checks whether identity information (name, address) leaked into the "
                "automated scoring for this one application. It is **not** a population-level "
                "fairness or disparate-impact audit — see Known Limitations (L2)."
            )

# ---------------------------------------------------------------------------
# 6. Document validation panel
# ---------------------------------------------------------------------------
if validation_results:
    with st.expander("📄 Document Validation Checks", expanded=False):
        for vr in validation_results:
            icon = "✅" if vr.passed else "❌"
            st.markdown(f"{icon} **{vr.check_name.replace('_', ' ').title()}**")
            if vr.evidence:
                st.caption(f"  {vr.evidence}")

# ---------------------------------------------------------------------------
# 6a. Extracted Fields panel
# ---------------------------------------------------------------------------
st.subheader("🔍 Extracted Fields")
st.caption(
    "Every field IntakeNode extracted from your documents, "
    "with its source, evidence span, and confidence. "
    "Any low-confidence scoring-relevant field can be corrected here."
)

if extracted_effective:
    SCORING_RELEVANT = {
        "stated_monthly_income", "total_monthly_obligations", "bureau_score",
        "employment_tenure_months", "income_variability_pct", "average_monthly_deposits",
    }

    for field_name, field_row in sorted(extracted_effective.items()):
        highlight = (
            field_row.confidence == "low"
            and field_name in SCORING_RELEVANT
            and app.status == "NEEDS_MANUAL_VERIFICATION"
        )
        bg_style = "background-color: #fffbeb; border-radius:4px; padding:8px;" if highlight else ""

        # Count prior versions for the "N prior value" link
        all_versions_for_field = [
            r for r in extracted_all
            if r.field_name == field_name and r.field_version < field_row.field_version
        ]

        with st.container():
            col_fn, col_val, col_src, col_ev, col_conf, col_act = st.columns([1.5, 1.2, 1, 2, 0.8, 1.5])
            with col_fn:
                label = field_name.replace("_", " ").title()
                if highlight:
                    st.markdown(f"⚠️ **{label}**")
                else:
                    st.markdown(f"**{label}**")
            with col_val:
                st.text(field_row.field_value or "—")
            with col_src:
                st.caption(field_row.source_document or "—")
            with col_ev:
                st.caption(truncate(field_row.evidence_span, 60))
            with col_conf:
                st.markdown(confidence_badge(field_row.confidence))
            with col_act:
                if all_versions_for_field:
                    st.caption(f"{len(all_versions_for_field)} prior value(s)")
                if highlight:
                    if st.button("✏️ Correct", key=f"correct_{field_name}"):
                        st.session_state[f"correcting_{field_name}"] = True

        # Inline correction form
        if st.session_state.get(f"correcting_{field_name}"):
            with st.form(key=f"correction_form_{field_name}"):
                st.markdown(f"**Correct value for: {field_name.replace('_', ' ').title()}**")
                st.caption(f"Original extracted: **{field_row.field_value}** (evidence: *{field_row.evidence_span}*)")
                corrected_value = st.text_input("Corrected value", value=field_row.field_value or "")
                correction_reason = st.text_input("Reason / source reference")
                col_s, col_c = st.columns(2)
                save_correction = col_s.form_submit_button("✅ Save & Re-score", type="primary")
                cancel = col_c.form_submit_button("Cancel")

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

                # Re-run agent from ScoringNode onward
                with st.spinner("Re-scoring with confirmed values…"):
                    try:
                        from src.agent.graph import resume_from_scoring
                        resume_from_scoring(application_id, underwriter_id)
                        st.success("Re-scoring complete. Refreshing…")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Re-scoring failed: {e}")
else:
    st.info("No extracted fields available yet.")

st.divider()

# ---------------------------------------------------------------------------
# 7. Decision capture form (human gate)
# ---------------------------------------------------------------------------
_can_decide = app.status in ("PENDING_HUMAN_REVIEW", "REFERRED_FOR_ESCALATION")

# Decision History strip (shown if prior decisions exist)
if decisions:
    st.subheader("📜 Decision History")
    for d in decisions:
        decided_str = d.decided_at.strftime("%Y-%m-%d %H:%M UTC") if d.decided_at else "—"
        icon = "✅" if d.decision == "APPROVE" else ("🔴" if d.decision == "DECLINE" else "🟣")
        terminal_label = " (terminal)" if d.is_terminal else " (non-terminal referral)"
        st.markdown(
            f"{icon} **{d.decision}**{terminal_label} — "
            f"by {d.underwriter_id} · {decided_str}"
        )
        if d.refer_reason:
            st.caption(f"  Refer reason: {d.refer_reason.replace('_', ' ').title()}")
        st.caption(f"  Rationale: {d.rationale}")

if _can_decide:
    st.subheader("✍️ Record Decision")
    st.caption(f"Deciding as: **{underwriter_id}**  *(Demo mode — identity not verified)*")

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
                options=[
                    "REQUEST_MORE_INFO",
                    "ESCALATE_TO_SENIOR_UNDERWRITER",
                    "ESCALATE_TO_COMMITTEE",
                ],
            )
            st.info(
                "ℹ️ **This does not close the application** — it will return to the queue "
                "for further action."
            )

        rationale = st.text_area(
            "Rationale * (required)",
            placeholder="Explain the basis for this decision.",
            height=100,
        )

        if rec and decision_choice not in ("— Select —", None):
            if decision_choice != rec.band:
                st.warning(
                    f"⚠️ This **differs from the system recommendation** ({rec.band}). "
                    "Rationale is required and will be recorded."
                )

        btn_label = "📋 Record Referral" if decision_choice == "REFER" else "✅ Record Final Decision"
        submit_decision = st.form_submit_button(
            btn_label,
            type="primary",
            disabled=(decision_choice == "— Select —"),
        )

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
                        f"✅ Decision recorded: **{decision_choice}** (Decision ID: {result['decision_id'][:8]}…). "
                        f"Application is now **DECIDED**."
                    )
                else:
                    st.success(
                        f"🟣 Referral recorded: **{decision_choice}** — {refer_reason}. "
                        f"Application returned to queue."
                    )
                st.rerun()
            except HumanDecisionError as e:
                st.error(f"Decision error: {e}")
            except Exception as e:
                st.error(f"Unexpected error: {e}")

elif terminal_decision:
    st.subheader("✅ Final Decision")
    decided_str = terminal_decision.decided_at.strftime("%Y-%m-%d %H:%M UTC") if terminal_decision.decided_at else "—"
    st.success(
        f"**{terminal_decision.decision}** — by {terminal_decision.underwriter_id} · {decided_str}\n\n"
        f"Rationale: {terminal_decision.rationale}"
    )
else:
    st.info(f"Application is in status **{status_badge(app.status)}** — no decision action available.")

st.divider()
if st.button("← Back to Queue"):
    st.switch_page("pages/queue.py")

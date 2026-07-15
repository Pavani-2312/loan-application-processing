"""
src/app/pages/queue.py

Screen 2 — Review Queue
MD3: hoverable surface cards with elevation transition, tonal status chips,
left-accent border per priority, filter bar.
"""
from __future__ import annotations

import streamlit as st

from src.app.ui_helpers import (
    band_badge,
    get_uow_factory,
    md3_blur_shapes,
    render_sidebar,
    status_badge,
)
from src.repository import UnitOfWork

st.set_page_config(
    page_title="Loan Processing — Review Queue",
    page_icon="📋",
    layout="wide",
)

underwriter_id, role = render_sidebar()
st.markdown(md3_blur_shapes(), unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Page header
# ---------------------------------------------------------------------------
st.markdown("""
<div style="margin-bottom:1.5rem;">
  <div style="font-size:0.75rem;font-weight:500;letter-spacing:0.08em;
    text-transform:uppercase;color:#6750A4;margin-bottom:6px;">Underwriting</div>
  <h1 style="margin:0;font-size:1.75rem;font-weight:500;color:#1C1B1F;">Review Queue</h1>
</div>
""", unsafe_allow_html=True)

factory = get_uow_factory()

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
with UnitOfWork(factory) as uow:
    all_apps = uow.applications.list_all()
    rows = []
    for app in all_apps:
        if app.status == "POLICY_CONFIG_ERROR" and role != "credit_ops_lead":
            continue
        rec     = uow.recommendations.get_latest(app.application_id)
        fairness= uow.fairness_checks.get_latest(app.application_id)
        flags   = uow.guardrail_flags.get_all(app.application_id)
        decisions = uow.human_decisions.get_all(app.application_id)

        latest_refer_reason = None
        if app.status == "REFERRED_FOR_ESCALATION" and decisions:
            last_refer = [d for d in decisions if d.decision == "REFER"]
            if last_refer:
                latest_refer_reason = last_refer[-1].refer_reason

        rows.append({
            "app":        app,
            "full_id":    app.application_id,
            "short_id":   app.application_id[:8] + "…",
            "applicant":  app.applicant_name,
            "submitted":  app.submitted_at.strftime("%Y-%m-%d %H:%M") if app.submitted_at else "—",
            "status":     app.status,
            "band":       rec.band if rec else None,
            "score":      rec.composite_score if rec else None,
            "fairness":   fairness.result if fairness else None,
            "flagged":    len(flags) > 0,
            "refer_reason": latest_refer_reason,
        })

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
with st.container():
    col1, col2, col3 = st.columns(3)
    with col1:
        status_filter = st.multiselect(
            "Status", sorted(set(r["status"] for r in rows)),
            placeholder="All statuses",
        )
    with col2:
        band_filter = st.multiselect(
            "Recommendation", ["APPROVE", "REFER", "DECLINE"],
            placeholder="All bands",
        )
    with col3:
        fairness_filter = st.selectbox(
            "Fairness check", ["All", "PASS", "FAIL", "Not yet checked"], index=0,
        )

filtered = rows
if status_filter:
    filtered = [r for r in filtered if r["status"] in status_filter]
if band_filter:
    filtered = [r for r in filtered if r["band"] in band_filter]
if fairness_filter == "Not yet checked":
    filtered = [r for r in filtered if r["fairness"] is None]
elif fairness_filter in ("PASS", "FAIL"):
    filtered = [r for r in filtered if r["fairness"] == fairness_filter]

def _sort_key(r):
    p = {"PENDING_HUMAN_REVIEW": 0, "NEEDS_MANUAL_VERIFICATION": 1,
         "REFERRED_FOR_ESCALATION": 2}.get(r["status"], 3)
    return (p, r["submitted"])

filtered.sort(key=_sort_key)

# ---------------------------------------------------------------------------
# Status → left-border accent color
# ---------------------------------------------------------------------------
_ACCENT: dict[str, str] = {
    "AWAITING_DOCUMENTS":        "#79747E",
    "INCONSISTENT_DOCUMENTS":    "#7D5700",
    "NEEDS_MANUAL_VERIFICATION": "#7D5700",
    "PROCESSING_ERROR":          "#B3261E",
    "POLICY_CONFIG_ERROR":       "#B3261E",
    "PENDING_HUMAN_REVIEW":      "#2563EB",
    "REFERRED_FOR_ESCALATION":   "#6750A4",
    "DECIDED":                   "#386A20",
}

# ---------------------------------------------------------------------------
# Column headers
# ---------------------------------------------------------------------------
st.divider()
st.markdown(
    f'<p style="font-size:0.78rem;font-weight:500;color:#79747E;">Showing {len(filtered)} of {len(rows)} applications</p>',
    unsafe_allow_html=True,
)

hcol = st.columns([2.8, 2.2, 1.4, 1.0, 0.6, 1.4])
for col, label in zip(hcol, ["Application", "Status", "Recommendation", "Fairness", "🚩", "Action"]):
    col.markdown(
        f'<p style="font-size:0.72rem;font-weight:500;text-transform:uppercase;'
        f'letter-spacing:0.06em;color:#79747E;margin:0;">{label}</p>',
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Application rows
# ---------------------------------------------------------------------------
if not filtered:
    st.markdown(
        '<div style="background:#F3EDF7;border-radius:24px;padding:2rem;text-align:center;'
        'color:#49454F;font-size:0.9rem;margin-top:0.5rem;">'
        'No applications match the current filters.</div>',
        unsafe_allow_html=True,
    )
else:
    for r in filtered:
        accent = _ACCENT.get(r["status"], "#79747E")
        # Card wrapper with left accent bar
        st.markdown(
            f'<div style="border-left:4px solid {accent};border-radius:0 20px 20px 0;'
            f'margin-bottom:2px;"></div>',
            unsafe_allow_html=True,
        )
        with st.container(border=True):
            col_id, col_st, col_rec, col_fair, col_flag, col_act = st.columns([2.8, 2.2, 1.4, 1.0, 0.6, 1.4])

            with col_id:
                st.markdown(
                    f'<p style="font-weight:500;font-size:0.9rem;margin:0;color:#1C1B1F;">{r["short_id"]}</p>'
                    f'<p style="font-size:0.78rem;color:#49454F;margin:2px 0 0;">{r["applicant"]} · {r["submitted"]}</p>',
                    unsafe_allow_html=True,
                )

            with col_st:
                st.markdown(status_badge(r["status"]), unsafe_allow_html=True)
                if r["refer_reason"]:
                    st.markdown(
                        f'<p style="font-size:0.72rem;color:#6750A4;margin:3px 0 0;">'
                        f'{r["refer_reason"].replace("_"," ").title()}</p>',
                        unsafe_allow_html=True,
                    )

            with col_rec:
                st.markdown(band_badge(r["band"]), unsafe_allow_html=True)
                if r["score"] is not None:
                    st.markdown(
                        f'<p style="font-size:0.72rem;color:#79747E;margin:3px 0 0;">{r["score"]:.3f}</p>',
                        unsafe_allow_html=True,
                    )

            with col_fair:
                if r["fairness"] == "PASS":
                    st.markdown('<span style="color:#386A20;font-size:0.85rem;">✅ Pass</span>', unsafe_allow_html=True)
                elif r["fairness"] == "FAIL":
                    st.markdown('<span style="color:#B3261E;font-size:0.85rem;">⚠️ Fail</span>', unsafe_allow_html=True)
                else:
                    st.markdown('<span style="color:#79747E;font-size:0.85rem;">—</span>', unsafe_allow_html=True)

            with col_flag:
                if r["flagged"]:
                    st.markdown('<span style="font-size:1rem;">🚩</span>', unsafe_allow_html=True)

            with col_act:
                btn_label = {
                    "AWAITING_DOCUMENTS":        "Request docs →",
                    "NEEDS_MANUAL_VERIFICATION": "Verify fields →",
                    "REFERRED_FOR_ESCALATION":   "Continue →",
                }.get(r["status"], "Review →")

                if st.button(btn_label, key=f"q_{r['full_id']}"):
                    st.session_state["review_application_id"] = r["full_id"]
                    st.switch_page("pages/detail.py")

"""
src/app/pages/audit.py

Screen 4 — Audit Explorer
Searchable history, KPI strip, single-application audit package export.
"""
from __future__ import annotations

import json
from datetime import datetime

import streamlit as st

from src.app.ui_helpers import (
    band_badge,
    fmt_score,
    get_uow_factory,
    render_sidebar,
    status_badge,
    truncate,
)
from src.repository import UnitOfWork

st.set_page_config(
    page_title="Loan Processing — Audit Explorer",
    page_icon="🔎",
    layout="wide",
)

underwriter_id, role = render_sidebar()

st.title("🔎 Audit Explorer")

factory = get_uow_factory()

# ---------------------------------------------------------------------------
# Load all decided + referred applications (full history)
# ---------------------------------------------------------------------------
with UnitOfWork(factory) as uow:
    all_apps = uow.applications.list_all()
    rows = []
    for app in all_apps:
        rec = uow.recommendations.get_latest(app.application_id)
        fairness = uow.fairness_checks.get_latest(app.application_id)
        decisions = uow.human_decisions.get_all(app.application_id)
        terminal = uow.human_decisions.get_terminal_decision(app.application_id)
        flags = uow.guardrail_flags.get_all(app.application_id)

        # KPI: matches_recommendation is true if all terminal decisions matched
        matches_rec = terminal.matches_recommendation if terminal else None
        decided_by = terminal.underwriter_id if terminal else None
        decided_at_str = (
            terminal.decided_at.strftime("%Y-%m-%d %H:%M")
            if terminal and terminal.decided_at else "—"
        )

        rows.append({
            "full_id": app.application_id,
            "application_id": app.application_id[:12] + "…",
            "submitted": app.submitted_at.strftime("%Y-%m-%d") if app.submitted_at else "—",
            "submitted_dt": app.submitted_at,
            "status": app.status,
            "recommendation": rec.band if rec else None,
            "human_decision": terminal.decision if terminal else None,
            "matches_rec": matches_rec,
            "fairness": fairness.result if fairness else None,
            "guardrail_flagged": len(flags) > 0,
            "decided_by": decided_by,
            "decided_at": decided_at_str,
            "composite_score": rec.composite_score if rec else None,
        })

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
st.subheader("Filters")
col1, col2, col3, col4 = st.columns(4)
with col1:
    status_filter = st.multiselect("Status", sorted(set(r["status"] for r in rows)), placeholder="All")
with col2:
    band_filter = st.multiselect("Recommendation", ["APPROVE", "REFER", "DECLINE"], placeholder="All")
with col3:
    fairness_filter = st.selectbox("Fairness", ["All", "PASS", "FAIL", "Pending"], index=0)
with col4:
    guardrail_filter = st.selectbox("Guardrail flags", ["All", "Flagged only", "No flags"], index=0)

filtered = rows
if status_filter:
    filtered = [r for r in filtered if r["status"] in status_filter]
if band_filter:
    filtered = [r for r in filtered if r["recommendation"] in band_filter]
if fairness_filter == "PASS":
    filtered = [r for r in filtered if r["fairness"] == "PASS"]
elif fairness_filter == "FAIL":
    filtered = [r for r in filtered if r["fairness"] == "FAIL"]
elif fairness_filter == "Pending":
    filtered = [r for r in filtered if r["fairness"] is None]
if guardrail_filter == "Flagged only":
    filtered = [r for r in filtered if r["guardrail_flagged"]]
elif guardrail_filter == "No flags":
    filtered = [r for r in filtered if not r["guardrail_flagged"]]

# ---------------------------------------------------------------------------
# KPI strip
# ---------------------------------------------------------------------------
st.divider()
kpi1, kpi2, kpi3, kpi4 = st.columns(4)

decided = [r for r in filtered if r["human_decision"] is not None]
straight_through = [r for r in decided if r["matches_rec"] is True]
fairness_pass = [r for r in filtered if r["fairness"] == "PASS"]
fairness_checked = [r for r in filtered if r["fairness"] is not None]

with kpi1:
    st.metric("Total applications", len(filtered))
with kpi2:
    sth_rate = len(straight_through) / len(decided) * 100 if decided else 0
    st.metric("Straight-through rate", f"{sth_rate:.0f}%", help="% where human decision matched agent recommendation")
with kpi3:
    fairness_rate = len(fairness_pass) / len(fairness_checked) * 100 if fairness_checked else 0
    st.metric(
        "Identity-blind consistency pass rate",
        f"{fairness_rate:.0f}%",
        help="% where identity-blind re-score matched original band. Measures LLM extraction consistency, not population fairness — see L2.",
    )
with kpi4:
    decided_count = len(decided)
    st.metric("Decided", decided_count)

st.divider()

# ---------------------------------------------------------------------------
# Results table
# ---------------------------------------------------------------------------
st.caption(f"Showing {len(filtered)} applications")

if not filtered:
    st.info("No applications match the current filters.")
else:
    for r in filtered:
        with st.container(border=True):
            col_id, col_rec, col_dec, col_match, col_fair, col_flag, col_by, col_action = \
                st.columns([2, 1.2, 1.2, 1, 1, 0.7, 1.5, 1.5])

            with col_id:
                st.markdown(f"**{r['application_id']}**")
                st.caption(r["submitted"])
            with col_rec:
                st.markdown(band_badge(r["recommendation"]))
            with col_dec:
                if r["human_decision"]:
                    st.markdown(band_badge(r["human_decision"]))
                else:
                    st.caption("—")
            with col_match:
                if r["matches_rec"] is True:
                    st.markdown("✅")
                elif r["matches_rec"] is False:
                    st.markdown("⚠️ Override")
                else:
                    st.caption("—")
            with col_fair:
                if r["fairness"] == "PASS":
                    st.markdown("✅")
                elif r["fairness"] == "FAIL":
                    st.markdown("⚠️")
                else:
                    st.caption("—")
            with col_flag:
                if r["guardrail_flagged"]:
                    st.markdown("🚩")
            with col_by:
                st.caption(r["decided_by"] or "—")
                st.caption(r["decided_at"])
            with col_action:
                if st.button("🔍 View", key=f"audit_view_{r['full_id']}"):
                    st.session_state["review_application_id"] = r["full_id"]
                    st.session_state["audit_mode"] = True
                    st.switch_page("pages/audit_detail.py")

# ---------------------------------------------------------------------------
# Bulk export (Credit Ops Lead only)
# ---------------------------------------------------------------------------
if role == "credit_ops_lead":
    st.divider()
    st.subheader("📦 Bulk Export")
    if st.button("⬇️ Export filtered set as JSON"):
        export_data = []
        with UnitOfWork(factory) as uow:
            for r in filtered:
                export_data.append({
                    "application_id": r["full_id"],
                    "status": r["status"],
                    "recommendation": r["recommendation"],
                    "human_decision": r["human_decision"],
                    "matches_recommendation": r["matches_rec"],
                    "fairness_result": r["fairness"],
                    "guardrail_flagged": r["guardrail_flagged"],
                    "composite_score": r["composite_score"],
                    "decided_by": r["decided_by"],
                    "decided_at": r["decided_at"],
                    "audit_events": uow.audit_logs.get_all_for_export(r["full_id"]),
                })
        st.download_button(
            label="📥 Download JSON",
            data=json.dumps(export_data, indent=2, default=str),
            file_name=f"audit_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
        )

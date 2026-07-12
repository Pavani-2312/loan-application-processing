"""
src/app/pages/queue.py

Screen 2 — Review Queue
Filterable table of applications needing attention.
"""
from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from src.app.ui_helpers import (
    band_badge,
    get_uow_factory,
    render_sidebar,
    status_badge,
    truncate,
)
from src.repository import UnitOfWork

st.set_page_config(
    page_title="Loan Processing — Review Queue",
    page_icon="📋",
    layout="wide",
)

underwriter_id, role = render_sidebar()

st.title("📋 Review Queue")

factory = get_uow_factory()

# ---------------------------------------------------------------------------
# Load applications
# ---------------------------------------------------------------------------
with UnitOfWork(factory) as uow:
    all_apps = uow.applications.list_all()

    # Build a display row per application
    rows = []
    for app in all_apps:
        # Skip POLICY_CONFIG_ERROR for non-credit-ops users
        if app.status == "POLICY_CONFIG_ERROR" and role != "credit_ops_lead":
            continue

        rec = uow.recommendations.get_latest(app.application_id)
        fairness = uow.fairness_checks.get_latest(app.application_id)
        flags = uow.guardrail_flags.get_all(app.application_id)
        decisions = uow.human_decisions.get_all(app.application_id)

        latest_refer_reason = None
        if app.status == "REFERRED_FOR_ESCALATION" and decisions:
            last_refer = [d for d in decisions if d.decision == "REFER"]
            if last_refer:
                latest_refer_reason = last_refer[-1].refer_reason

        rows.append({
            "app": app,
            "application_id": app.application_id[:8] + "…",
            "full_id": app.application_id,
            "applicant": app.applicant_name,
            "submitted": app.submitted_at.strftime("%Y-%m-%d %H:%M") if app.submitted_at else "—",
            "status": app.status,
            "recommendation": rec.band if rec else None,
            "fairness": fairness.result if fairness else None,
            "guardrail": len(flags) > 0,
            "refer_reason": latest_refer_reason,
        })

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
col1, col2, col3 = st.columns(3)
with col1:
    status_filter = st.multiselect(
        "Status",
        options=sorted(set(r["status"] for r in rows)),
        default=[],
        placeholder="All statuses",
    )
with col2:
    band_filter = st.multiselect(
        "Recommendation",
        options=["APPROVE", "REFER", "DECLINE"],
        default=[],
        placeholder="All bands",
    )
with col3:
    fairness_filter = st.selectbox(
        "Fairness",
        options=["All", "PASS", "FAIL", "Not yet checked"],
        index=0,
    )

# Apply filters
filtered = rows
if status_filter:
    filtered = [r for r in filtered if r["status"] in status_filter]
if band_filter:
    filtered = [r for r in filtered if r["recommendation"] in band_filter]
if fairness_filter != "All":
    if fairness_filter == "Not yet checked":
        filtered = [r for r in filtered if r["fairness"] is None]
    else:
        filtered = [r for r in filtered if r["fairness"] == fairness_filter]

# Sort: PENDING_HUMAN_REVIEW oldest first, then everything else
def _sort_key(r):
    priority = {"PENDING_HUMAN_REVIEW": 0, "NEEDS_MANUAL_VERIFICATION": 1, "REFERRED_FOR_ESCALATION": 2}.get(r["status"], 3)
    return (priority, r["submitted"])

filtered.sort(key=_sort_key)

st.caption(f"Showing {len(filtered)} of {len(rows)} applications")

# ---------------------------------------------------------------------------
# Table
# ---------------------------------------------------------------------------
if not filtered:
    st.info("No applications match the current filters.")
else:
    for r in filtered:
        status = r["status"]

        # Row background colour
        if status in ("AWAITING_DOCUMENTS", "INCONSISTENT_DOCUMENTS", "NEEDS_MANUAL_VERIFICATION"):
            bg = "#fffbeb"  # amber
        elif status == "REFERRED_FOR_ESCALATION":
            bg = "#f5f3ff"  # indigo
        elif status == "PENDING_HUMAN_REVIEW":
            bg = "#eff6ff"  # blue
        elif status == "DECIDED":
            bg = "#f0fdf4"  # green
        else:
            bg = "#fef2f2"  # red/error

        with st.container(border=True):
            col_id, col_status, col_rec, col_fair, col_flag, col_action = st.columns([2, 2, 1.5, 1.2, 0.8, 1.5])

            with col_id:
                st.markdown(f"**{r['application_id']}**")
                st.caption(f"{r['applicant']} · {r['submitted']}")

            with col_status:
                st.markdown(status_badge(status))
                if r["refer_reason"]:
                    st.caption(r["refer_reason"].replace("_", " ").title())

            with col_rec:
                st.markdown(band_badge(r["recommendation"]))

            with col_fair:
                if r["fairness"] == "PASS":
                    st.markdown("✅ Pass")
                elif r["fairness"] == "FAIL":
                    st.markdown("⚠️ Fail")
                else:
                    st.markdown("—")

            with col_flag:
                if r["guardrail"]:
                    st.markdown("🚩")

            with col_action:
                if status == "AWAITING_DOCUMENTS":
                    btn_label = "📄 Request Docs"
                elif status == "NEEDS_MANUAL_VERIFICATION":
                    btn_label = "🔍 Verify Fields"
                elif status in ("REFERRED_FOR_ESCALATION",):
                    btn_label = "▶️ Continue Review"
                else:
                    btn_label = "📋 Review →"

                if st.button(btn_label, key=f"review_{r['full_id']}"):
                    st.session_state["review_application_id"] = r["full_id"]
                    st.switch_page("src/app/pages/detail.py")

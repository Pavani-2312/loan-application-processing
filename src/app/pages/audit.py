"""
src/app/pages/audit.py

Screen 4 — Audit Explorer
MD3: display-scale KPI metric cards, tonal table rows, filter bar, bulk export.
"""
from __future__ import annotations

import json
from datetime import datetime

import streamlit as st

from src.app.ui_helpers import (
    band_badge,
    fmt_score,
    get_uow_factory,
    md3_blur_shapes,
    md3_metric_html,
    render_sidebar,
    status_badge,
)
from src.repository import UnitOfWork

st.set_page_config(
    page_title="Loan Processing — Audit Explorer",
    page_icon="🔎",
    layout="wide",
)

underwriter_id, role = render_sidebar()
st.markdown(md3_blur_shapes(), unsafe_allow_html=True)

st.markdown("""
<div style="margin-bottom:1.5rem;">
  <div style="font-size:0.75rem;font-weight:500;letter-spacing:0.08em;
    text-transform:uppercase;color:#6750A4;margin-bottom:6px;">Compliance</div>
  <h1 style="margin:0;font-size:1.75rem;font-weight:500;color:#1C1B1F;">Audit Explorer</h1>
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
        rec      = uow.recommendations.get_latest(app.application_id)
        fairness = uow.fairness_checks.get_latest(app.application_id)
        decisions= uow.human_decisions.get_all(app.application_id)
        terminal = uow.human_decisions.get_terminal_decision(app.application_id)
        flags    = uow.guardrail_flags.get_all(app.application_id)
        rows.append({
            "full_id":     app.application_id,
            "short_id":    app.application_id[:12] + "…",
            "submitted":   app.submitted_at.strftime("%Y-%m-%d") if app.submitted_at else "—",
            "submitted_dt":app.submitted_at,
            "status":      app.status,
            "band":        rec.band if rec else None,
            "score":       rec.composite_score if rec else None,
            "human_decision": terminal.decision if terminal else None,
            "matches_rec": terminal.matches_recommendation if terminal else None,
            "fairness":    fairness.result if fairness else None,
            "flagged":     len(flags) > 0,
            "decided_by":  terminal.underwriter_id if terminal else None,
            "decided_at":  terminal.decided_at.strftime("%Y-%m-%d %H:%M") if terminal and terminal.decided_at else "—",
        })

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
with st.container():
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        sf = st.multiselect("Status", sorted(set(r["status"] for r in rows)), placeholder="All")
    with c2:
        bf = st.multiselect("Recommendation", ["APPROVE","REFER","DECLINE"], placeholder="All")
    with c3:
        ff = st.selectbox("Fairness", ["All","PASS","FAIL","Pending"], index=0)
    with c4:
        gf = st.selectbox("Guardrail", ["All","Flagged only","No flags"], index=0)

filtered = rows
if sf:
    filtered = [r for r in filtered if r["status"] in sf]
if bf:
    filtered = [r for r in filtered if r["band"] in bf]
if ff == "PASS":    filtered = [r for r in filtered if r["fairness"] == "PASS"]
elif ff == "FAIL":  filtered = [r for r in filtered if r["fairness"] == "FAIL"]
elif ff == "Pending": filtered = [r for r in filtered if r["fairness"] is None]
if gf == "Flagged only": filtered = [r for r in filtered if r["flagged"]]
elif gf == "No flags":   filtered = [r for r in filtered if not r["flagged"]]

# ---------------------------------------------------------------------------
# KPI strip
# ---------------------------------------------------------------------------
st.divider()

decided    = [r for r in filtered if r["human_decision"] is not None]
straight   = [r for r in decided  if r["matches_rec"] is True]
f_pass     = [r for r in filtered if r["fairness"] == "PASS"]
f_checked  = [r for r in filtered if r["fairness"] is not None]

sth_rate   = len(straight) / len(decided) * 100 if decided else 0
fair_rate  = len(f_pass) / len(f_checked) * 100 if f_checked else 0

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(md3_metric_html("Total applications", str(len(filtered))), unsafe_allow_html=True)
with k2:
    st.markdown(
        md3_metric_html("Straight-through rate", f"{sth_rate:.0f}%",
                        sub="Human matched agent recommendation",
                        accent_color="#386A20" if sth_rate >= 80 else "#7D5700"),
        unsafe_allow_html=True,
    )
with k3:
    st.markdown(
        md3_metric_html("Fairness pass rate", f"{fair_rate:.0f}%",
                        sub="Identity-blind consistency (single-app check, not population audit)",
                        accent_color="#386A20" if fair_rate >= 90 else "#B3261E"),
        unsafe_allow_html=True,
    )
with k4:
    st.markdown(md3_metric_html("Decided", str(len(decided)), accent_color="#6750A4"), unsafe_allow_html=True)

st.divider()

# ---------------------------------------------------------------------------
# Column headers
# ---------------------------------------------------------------------------
st.markdown(
    f'<p style="font-size:0.78rem;color:#79747E;margin-bottom:6px;">Showing {len(filtered)} applications</p>',
    unsafe_allow_html=True,
)

hcols = st.columns([2, 1.2, 1.2, 0.8, 0.8, 0.5, 1.8, 1.2])
for col, lbl in zip(hcols, ["Application", "Rec.", "Decision", "Match", "Fairness", "🚩", "Decided by", "Action"]):
    col.markdown(
        f'<p style="font-size:0.72rem;font-weight:500;text-transform:uppercase;'
        f'letter-spacing:0.06em;color:#79747E;margin:0;">{lbl}</p>',
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Rows
# ---------------------------------------------------------------------------
if not filtered:
    st.markdown(
        '<div style="background:#F3EDF7;border-radius:24px;padding:2rem;text-align:center;'
        'color:#49454F;font-size:0.9rem;">No applications match the current filters.</div>',
        unsafe_allow_html=True,
    )
else:
    for r in filtered:
        with st.container(border=True):
            ca, cb, cc, cd, ce, cf, cg, ch = st.columns([2, 1.2, 1.2, 0.8, 0.8, 0.5, 1.8, 1.2])
            with ca:
                st.markdown(
                    f'<p style="font-weight:500;font-size:0.88rem;margin:0;color:#1C1B1F;">{r["short_id"]}</p>'
                    f'<p style="font-size:0.75rem;color:#49454F;margin:2px 0 0;">{r["submitted"]}</p>',
                    unsafe_allow_html=True,
                )
            with cb:
                st.markdown(band_badge(r["band"]), unsafe_allow_html=True)
            with cc:
                st.markdown(band_badge(r["human_decision"]) if r["human_decision"] else
                            '<span style="color:#79747E;font-size:0.82rem;">—</span>', unsafe_allow_html=True)
            with cd:
                if r["matches_rec"] is True:
                    st.markdown('<span style="color:#386A20;font-size:0.85rem;">✅</span>', unsafe_allow_html=True)
                elif r["matches_rec"] is False:
                    st.markdown('<span style="color:#B3261E;font-size:0.75rem;">⚠️ Override</span>', unsafe_allow_html=True)
                else:
                    st.markdown('<span style="color:#79747E;font-size:0.82rem;">—</span>', unsafe_allow_html=True)
            with ce:
                if r["fairness"] == "PASS":
                    st.markdown('<span style="color:#386A20;">✅</span>', unsafe_allow_html=True)
                elif r["fairness"] == "FAIL":
                    st.markdown('<span style="color:#B3261E;">⚠️</span>', unsafe_allow_html=True)
                else:
                    st.markdown('<span style="color:#79747E;font-size:0.82rem;">—</span>', unsafe_allow_html=True)
            with cf:
                if r["flagged"]:
                    st.markdown("🚩")
            with cg:
                st.markdown(
                    f'<p style="font-size:0.78rem;color:#49454F;margin:0;">{r["decided_by"] or "—"}</p>'
                    f'<p style="font-size:0.72rem;color:#79747E;margin:2px 0 0;">{r["decided_at"]}</p>',
                    unsafe_allow_html=True,
                )
            with ch:
                if st.button("🔍 View audit", key=f"av_{r['full_id']}"):
                    st.session_state["review_application_id"] = r["full_id"]
                    st.session_state["audit_mode"] = True
                    st.switch_page("pages/audit_detail.py")

# ---------------------------------------------------------------------------
# Bulk export (Credit Ops Lead)
# ---------------------------------------------------------------------------
if role == "credit_ops_lead":
    st.divider()
    st.markdown(
        '<h2 style="font-size:1.05rem;font-weight:500;color:#1C1B1F;margin-bottom:0.5rem;">'
        '📦 Bulk Export</h2>',
        unsafe_allow_html=True,
    )
    if st.button("Export filtered set as JSON →"):
        export_data = []
        with UnitOfWork(factory) as uow:
            for r in filtered:
                export_data.append({
                    "application_id":      r["full_id"],
                    "status":              r["status"],
                    "recommendation":      r["band"],
                    "human_decision":      r["human_decision"],
                    "matches_recommendation": r["matches_rec"],
                    "fairness_result":     r["fairness"],
                    "guardrail_flagged":   r["flagged"],
                    "composite_score":     r["score"],
                    "decided_by":          r["decided_by"],
                    "decided_at":          r["decided_at"],
                    "audit_events":        uow.audit_logs.get_all_for_export(r["full_id"]),
                })
        st.download_button(
            label="⬇️ Download JSON",
            data=json.dumps(export_data, indent=2, default=str),
            file_name=f"audit_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
        )

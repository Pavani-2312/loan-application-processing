"""
src/app/ui_helpers.py

Shared utilities for all Streamlit pages:
- DB session factory (singleton)
- Status badge rendering
- Role/underwriter sidebar
- Common formatting helpers
"""
from __future__ import annotations

import uuid
from typing import Any

import streamlit as st

from src.config import get_db_path
from src.repository import UnitOfWork, create_db_engine, get_session_factory, init_db

# ---------------------------------------------------------------------------
# DB session factory — shared across all pages via st.cache_resource
# ---------------------------------------------------------------------------

@st.cache_resource
def get_uow_factory():
    engine = create_db_engine(get_db_path())
    init_db(engine)
    return get_session_factory(engine)


# ---------------------------------------------------------------------------
# Status badge colours and labels
# ---------------------------------------------------------------------------

STATUS_STYLES: dict[str, tuple[str, str]] = {
    "AWAITING_DOCUMENTS":        ("🔘", "#888888"),
    "INCONSISTENT_DOCUMENTS":    ("⚠️",  "#d97706"),
    "NEEDS_MANUAL_VERIFICATION": ("🔍", "#b45309"),
    "PROCESSING_ERROR":          ("❌", "#dc2626"),
    "POLICY_CONFIG_ERROR":       ("🔧", "#7c2d12"),
    "PENDING_HUMAN_REVIEW":      ("🔵", "#2563eb"),
    "REFERRED_FOR_ESCALATION":   ("🟣", "#7c3aed"),
    "DECIDED":                   ("✅", "#16a34a"),
}


def status_badge(status: str) -> str:
    icon, _ = STATUS_STYLES.get(status, ("⬜", "#888888"))
    return f"{icon} {status.replace('_', ' ').title()}"


def band_badge(band: str | None) -> str:
    if band == "APPROVE":
        return "🟢 APPROVE"
    elif band == "REFER":
        return "🟡 REFER"
    elif band == "DECLINE":
        return "🔴 DECLINE"
    return "—"


def confidence_badge(confidence: str | None) -> str:
    if confidence == "high":
        return "🟢 High"
    elif confidence == "medium":
        return "🟡 Medium"
    elif confidence == "low":
        return "🔴 Low"
    return "—"


# ---------------------------------------------------------------------------
# Sidebar: role selector + demo-mode notice
# ---------------------------------------------------------------------------

UNDERWRITERS = [
    "Alice Chen (Underwriter)",
    "Bob Patel (Underwriter)",
    "Carol Okafor (Underwriter)",
    "David Kim (Credit Ops Lead)",
    "Eve Nakamura (Credit Ops Lead)",
]


def render_sidebar() -> tuple[str, str]:
    """
    Render sidebar role selector.
    Returns (underwriter_id, role) where role is 'underwriter' or 'credit_ops_lead'.
    """
    with st.sidebar:
        st.title("🏦 Loan Processing")
        st.divider()

        selected = st.selectbox(
            "Acting as",
            UNDERWRITERS,
            key="sidebar_underwriter",
        )
        role = "credit_ops_lead" if "Credit Ops Lead" in selected else "underwriter"
        underwriter_id = selected.split(" (")[0]

        st.caption(
            "⚠️ **Demo mode** — underwriter identity is self-selected, not verified. "
            "See [Known Limitations (L1)](# 'Authentication is out of scope for this build')."
        )
        st.divider()

        st.page_link("src/app/main.py", label="📝 New Application", icon="📝")
        st.page_link("src/app/pages/queue.py", label="📋 Review Queue", icon="📋")
        st.page_link("src/app/pages/audit.py", label="🔎 Audit Explorer", icon="🔎")

    return underwriter_id, role


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------

def new_idempotency_key() -> str:
    return str(uuid.uuid4())


def truncate(text: str | None, n: int = 80) -> str:
    if not text:
        return "—"
    return text if len(text) <= n else text[:n] + "…"


def fmt_score(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:.3f}"


def fmt_pct(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v * 100:.1f}%"

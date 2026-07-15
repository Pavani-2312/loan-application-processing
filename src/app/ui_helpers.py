"""
src/app/ui_helpers.py

Shared utilities for all Streamlit pages:
- DB session factory (singleton)
- inject_theme()  — injects MD3 stylesheet + Roboto (called inside render_sidebar)
- MD3 badge/chip helpers: status_badge, band_badge, confidence_badge
- MD3 component helpers: md3_card, md3_metric_html, md3_section_header, md3_blur_shapes
- Role/underwriter sidebar
- Common formatting helpers
"""
from __future__ import annotations

import uuid

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
# Theme injection — call once per page after set_page_config()
# ---------------------------------------------------------------------------

def inject_theme() -> None:
    """Delegate to theme.py inject_theme — kept here so callers only import ui_helpers."""
    from src.app.theme import inject_theme as _inject
    _inject()


# ---------------------------------------------------------------------------
# MD3 Status chip colors
# ---------------------------------------------------------------------------

_STATUS_CHIP: dict[str, dict] = {
    "AWAITING_DOCUMENTS":        {"bg": "#E7E0EC", "on": "#49454F",  "dot": "#79747E"},
    "INCONSISTENT_DOCUMENTS":    {"bg": "#FFDDB3", "on": "#5C3C00",  "dot": "#7D5700"},
    "NEEDS_MANUAL_VERIFICATION": {"bg": "#FFDDB3", "on": "#5C3C00",  "dot": "#7D5700"},
    "PROCESSING_ERROR":          {"bg": "#F9DEDC", "on": "#410E0B",  "dot": "#B3261E"},
    "POLICY_CONFIG_ERROR":       {"bg": "#F9DEDC", "on": "#410E0B",  "dot": "#B3261E"},
    "PENDING_HUMAN_REVIEW":      {"bg": "#D0E4FF", "on": "#001D36",  "dot": "#2563EB"},
    "REFERRED_FOR_ESCALATION":   {"bg": "#E8DEF8", "on": "#1D192B",  "dot": "#6750A4"},
    "DECIDED":                   {"bg": "#C3EFAB", "on": "#0A2000",  "dot": "#386A20"},
}

_BAND_CHIP: dict[str, dict] = {
    "APPROVE":  {"bg": "#C3EFAB", "on": "#0A2000", "dot": "#386A20"},
    "REFER":    {"bg": "#FFDDB3", "on": "#271900", "dot": "#7D5700"},
    "DECLINE":  {"bg": "#F9DEDC", "on": "#410E0B", "dot": "#B3261E"},
}

_CONFIDENCE_CHIP: dict[str, dict] = {
    "high":   {"bg": "#C3EFAB", "on": "#0A2000"},
    "medium": {"bg": "#FFDDB3", "on": "#271900"},
    "low":    {"bg": "#F9DEDC", "on": "#410E0B"},
}

_CHIP_CSS = (
    "display:inline-flex;align-items:center;gap:6px;"
    "padding:4px 12px;border-radius:9999px;"
    "font-family:'Roboto',sans-serif;font-size:0.78rem;font-weight:500;"
    "line-height:1.4;white-space:nowrap;"
)


def _dot(color: str) -> str:
    return (
        f'<span style="width:7px;height:7px;border-radius:50%;'
        f'background:{color};display:inline-block;flex-shrink:0;"></span>'
    )


def status_badge(status: str) -> str:
    """Return an MD3 tonal pill chip for an application status."""
    c = _STATUS_CHIP.get(status, {"bg": "#E7E0EC", "on": "#49454F", "dot": "#79747E"})
    label = status.replace("_", " ").title()
    return (
        f'<span style="{_CHIP_CSS}background:{c["bg"]};color:{c["on"]};">'
        f'{_dot(c["dot"])}{label}</span>'
    )


def band_badge(band: str | None) -> str:
    """Return an MD3 tonal pill chip for a recommendation band."""
    if not band:
        return '<span style="color:#79747E;font-size:0.85rem;">—</span>'
    c = _BAND_CHIP.get(band, {"bg": "#E7E0EC", "on": "#49454F", "dot": "#79747E"})
    return (
        f'<span style="{_CHIP_CSS}background:{c["bg"]};color:{c["on"]};">'
        f'{_dot(c["dot"])}{band}</span>'
    )


def confidence_badge(confidence: str | None) -> str:
    """Return an MD3 tonal pill chip for extraction confidence."""
    if not confidence:
        return '<span style="color:#79747E;font-size:0.85rem;">—</span>'
    c = _CONFIDENCE_CHIP.get(confidence, {"bg": "#E7E0EC", "on": "#49454F"})
    label = confidence.title()
    return (
        f'<span style="{_CHIP_CSS}background:{c["bg"]};color:{c["on"]};">'
        f'{label}</span>'
    )


# ---------------------------------------------------------------------------
# MD3 HTML component helpers
# ---------------------------------------------------------------------------

def md3_section_header(title: str, subtitle: str = "") -> str:
    """Render a section header with MD3 typography — call via st.markdown(..., unsafe_allow_html=True)."""
    sub_html = (
        f'<p style="margin:4px 0 0;font-size:0.9rem;color:#49454F;font-weight:400;">{subtitle}</p>'
        if subtitle else ""
    )
    return (
        f'<div style="margin-bottom:1rem;">'
        f'<h2 style="margin:0;font-size:1.35rem;font-weight:500;'
        f'color:#1C1B1F;font-family:Roboto,sans-serif;">{title}</h2>'
        f'{sub_html}'
        f'</div>'
    )


def md3_card(content_html: str, *, padding: str = "1.5rem", radius: str = "24px",
             bg: str = "#F3EDF7", shadow: bool = True) -> str:
    """Wrap content_html in an MD3 surface card."""
    shadow_css = "box-shadow:0 1px 3px rgba(0,0,0,0.07),0 1px 2px rgba(0,0,0,0.04);" if shadow else ""
    return (
        f'<div style="background:{bg};border-radius:{radius};'
        f'padding:{padding};{shadow_css}margin-bottom:1rem;">'
        f'{content_html}'
        f'</div>'
    )


def md3_metric_html(label: str, value: str, sub: str = "",
                    accent_color: str = "#6750A4") -> str:
    """Render a single KPI metric card as HTML."""
    sub_html = (
        f'<div style="font-size:0.78rem;color:#49454F;margin-top:4px;">{sub}</div>'
        if sub else ""
    )
    return (
        f'<div style="background:#F3EDF7;border-radius:20px;padding:1.25rem 1.5rem;'
        f'box-shadow:0 1px 3px rgba(0,0,0,0.06);">'
        f'<div style="font-size:0.72rem;font-weight:500;text-transform:uppercase;'
        f'letter-spacing:0.06em;color:#49454F;margin-bottom:6px;">{label}</div>'
        f'<div style="font-size:2rem;font-weight:500;color:{accent_color};'
        f'line-height:1.15;font-family:Roboto,sans-serif;">{value}</div>'
        f'{sub_html}'
        f'</div>'
    )


def md3_blur_shapes(
    color1: str = "#6750A4",
    color2: str = "#E8DEF8",
    color3: str = "#7D5260",
) -> str:
    """
    Inject atmospheric MD3 blur shapes — the signature background effect.
    Render once near the top of a hero section.
    """
    return f"""
<div aria-hidden="true" style="position:fixed;inset:0;pointer-events:none;z-index:0;overflow:hidden;">
  <!-- primary blob top-right -->
  <div style="position:absolute;top:-120px;right:-80px;width:420px;height:420px;
    border-radius:50%;background:{color1};opacity:0.07;filter:blur(80px);"></div>
  <!-- secondary blob bottom-left -->
  <div style="position:absolute;bottom:-60px;left:-100px;width:380px;height:380px;
    border-radius:50%;background:{color2};opacity:0.12;filter:blur(64px);"></div>
  <!-- tertiary blob center-right -->
  <div style="position:absolute;top:40%;right:5%;width:260px;height:260px;
    border-radius:50%;background:{color3};opacity:0.06;filter:blur(72px);"></div>
</div>
"""


# ---------------------------------------------------------------------------
# Sidebar: role selector + demo-mode notice + navigation
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
    Render MD3-styled sidebar with role selector and navigation.
    Also calls inject_theme() so every page gets the stylesheet automatically.
    Returns (underwriter_id, role).
    """
    inject_theme()

    with st.sidebar:
        st.markdown(
            '<h1 style="font-size:1.2rem;font-weight:500;margin:0 0 4px;'
            'color:#1C1B1F;font-family:Roboto,sans-serif;">🏦 Loan Processing</h1>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<p style="font-size:0.75rem;color:#49454F;margin:0 0 12px;">'
            'AI-assisted underwriting platform</p>',
            unsafe_allow_html=True,
        )
        st.divider()

        selected = st.selectbox(
            "Acting as",
            UNDERWRITERS,
            key="sidebar_underwriter",
        )
        role = "credit_ops_lead" if "Credit Ops Lead" in selected else "underwriter"
        underwriter_id = selected.split(" (")[0]

        st.markdown(
            '<div style="margin-top:8px;padding:10px 12px;background:#FFDDB3;'
            'border-radius:12px;font-size:0.75rem;color:#5C3C00;line-height:1.5;">'
            '⚠️ <strong>Demo mode</strong> — identity is self-selected, not verified.'
            '</div>',
            unsafe_allow_html=True,
        )
        st.divider()

        st.page_link("main.py",         label="New Application",  icon="📝")
        st.page_link("pages/queue.py",  label="Review Queue",     icon="📋")
        st.page_link("pages/audit.py",  label="Audit Explorer",   icon="🔎")

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

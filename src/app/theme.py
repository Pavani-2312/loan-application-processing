"""
src/app/theme.py

Material You (MD3) design token definitions and theme injection.
Single source of truth — all colors, radii, shadows, and typography
are defined here as Python constants and rendered into CSS custom properties.

Call inject_theme() once at the top of every page (done inside render_sidebar()).
"""
from __future__ import annotations

import streamlit as st

# ---------------------------------------------------------------------------
# MD3 Color tokens (Purple/Violet seed — #6750A4)
# ---------------------------------------------------------------------------

MD3 = {
    # Core surfaces
    "background":            "#FFFBFE",
    "on_background":         "#1C1B1F",
    "surface_container":     "#F3EDF7",
    "surface_container_low": "#E7E0EC",
    "surface_container_high":"#ECE6F0",

    # Primary
    "primary":               "#6750A4",
    "on_primary":            "#FFFFFF",
    "primary_container":     "#EADDFF",
    "on_primary_container":  "#21005D",

    # Secondary
    "secondary":             "#625B71",
    "on_secondary":          "#FFFFFF",
    "secondary_container":   "#E8DEF8",
    "on_secondary_container":"#1D192B",

    # Tertiary (mauve accent)
    "tertiary":              "#7D5260",
    "on_tertiary":           "#FFFFFF",
    "tertiary_container":    "#FFD8E4",
    "on_tertiary_container": "#31111D",

    # Semantic
    "error":                 "#B3261E",
    "on_error":              "#FFFFFF",
    "error_container":       "#F9DEDC",
    "on_error_container":    "#410E0B",

    "success":               "#386A20",
    "success_container":     "#C3EFAB",
    "on_success_container":  "#0A2000",

    "warning":               "#7D5700",
    "warning_container":     "#FFDDB3",
    "on_warning_container":  "#271900",

    # Outline / border
    "outline":               "#79747E",
    "outline_variant":       "#CAC4D0",

    # Text
    "on_surface":            "#1C1B1F",
    "on_surface_variant":    "#49454F",
}

# Recommendation band colors
BAND_COLORS = {
    "APPROVE":  {"bg": "#C3EFAB", "on": "#0A2000", "accent": "#386A20"},
    "REFER":    {"bg": "#FFDDB3", "on": "#271900", "accent": "#7D5700"},
    "DECLINE":  {"bg": "#F9DEDC", "on": "#410E0B", "accent": "#B3261E"},
}

# Status chip colors
STATUS_COLORS = {
    "AWAITING_DOCUMENTS":        {"bg": "#E7E0EC", "on": "#49454F",  "dot": "#79747E"},
    "INCONSISTENT_DOCUMENTS":    {"bg": "#FFDDB3", "on": "#271900",  "dot": "#7D5700"},
    "NEEDS_MANUAL_VERIFICATION": {"bg": "#FFDDB3", "on": "#271900",  "dot": "#7D5700"},
    "PROCESSING_ERROR":          {"bg": "#F9DEDC", "on": "#410E0B",  "dot": "#B3261E"},
    "POLICY_CONFIG_ERROR":       {"bg": "#F9DEDC", "on": "#410E0B",  "dot": "#B3261E"},
    "PENDING_HUMAN_REVIEW":      {"bg": "#D0E4FF", "on": "#001D36",  "dot": "#2563EB"},
    "REFERRED_FOR_ESCALATION":   {"bg": "#E8DEF8", "on": "#1D192B",  "dot": "#6750A4"},
    "DECIDED":                   {"bg": "#C3EFAB", "on": "#0A2000",  "dot": "#386A20"},
}


def _css_vars() -> str:
    """Render MD3 tokens as CSS custom properties on :root."""
    lines = ["  /* MD3 color tokens */"]
    for key, value in MD3.items():
        lines.append(f"  --md-{key.replace('_', '-')}: {value};")
    return "\n".join(lines)


def inject_theme() -> None:
    """
    Inject the full MD3 stylesheet into the current Streamlit page.
    Must be called after st.set_page_config() on every page.
    Idempotent — Streamlit deduplicates identical markdown blocks.
    """
    # Read the compiled CSS from disk; fall back to inline if missing
    import pathlib
    css_path = pathlib.Path(__file__).parent / "styles" / "md3.css"
    if css_path.exists():
        css_body = css_path.read_text()
    else:
        css_body = ""

    st.markdown(
        f"""
<style>
:root {{
{_css_vars()}
}}

/* Google Fonts — Roboto */
@import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap');

{css_body}
</style>
""",
        unsafe_allow_html=True,
    )

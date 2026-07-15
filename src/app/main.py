"""
src/app/main.py

Screen 1 — New Application
MD3-styled: hero container, atmospheric blur shapes, filled text inputs,
tonal file-upload cards, pill submit button.
"""
from __future__ import annotations

import time

import streamlit as st

from src.app.ui_helpers import (
    get_uow_factory,
    md3_blur_shapes,
    new_idempotency_key,
    render_sidebar,
)
from src.repository import UnitOfWork

st.set_page_config(
    page_title="Loan Processing — New Application",
    page_icon="🏦",
    layout="wide",
)

underwriter_id, role = render_sidebar()

# Atmospheric background
st.markdown(md3_blur_shapes(), unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Hero
# ---------------------------------------------------------------------------
st.markdown("""
<div style="background:#F3EDF7;border-radius:32px;padding:2.5rem 2.5rem 2rem;
  margin-bottom:1.75rem;box-shadow:0 1px 4px rgba(0,0,0,0.06);overflow:hidden;">
  <div style="font-size:0.75rem;font-weight:500;letter-spacing:0.08em;
    text-transform:uppercase;color:#6750A4;margin-bottom:8px;">New Loan Application</div>
  <h1 style="margin:0 0 8px;font-size:1.75rem;font-weight:500;color:#1C1B1F;
    line-height:1.2;font-family:Roboto,sans-serif;">Submit for automated assessment</h1>
  <p style="margin:0;font-size:0.95rem;color:#49454F;max-width:560px;line-height:1.6;">
    Upload all three documents. The agent extracts income, bureau score, tenure, and
    every scoring field — no manual data entry required.
  </p>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Applicant details
# ---------------------------------------------------------------------------
st.markdown('<p style="font-size:0.9rem;font-weight:500;color:#49454F;margin-bottom:0.5rem;">Applicant details</p>', unsafe_allow_html=True)

col_name, col_address = st.columns([1, 2])
with col_name:
    applicant_name = st.text_input("Full name *", placeholder="Jane Smith")
with col_address:
    applicant_address = st.text_input("Residential address *", placeholder="12 Main St, Springfield")

st.divider()

# ---------------------------------------------------------------------------
# Document upload
# ---------------------------------------------------------------------------
st.markdown(
    '<p style="font-size:0.9rem;font-weight:500;color:#49454F;margin-bottom:4px;">Required documents</p>'
    '<p style="font-size:0.82rem;color:#79747E;margin-bottom:1rem;">All three are required. PDF or TXT.</p>',
    unsafe_allow_html=True,
)

col_id, col_pay, col_bank = st.columns(3)

def _upload_label(icon: str, title: str) -> None:
    st.markdown(
        f'<p style="font-size:0.78rem;font-weight:500;color:#6750A4;'
        f'text-transform:uppercase;letter-spacing:0.06em;margin-bottom:6px;">{icon} {title}</p>',
        unsafe_allow_html=True,
    )

def _attached_pill(filename: str) -> None:
    st.markdown(
        f'<div style="background:#C3EFAB;color:#0A2000;border-radius:9999px;'
        f'padding:4px 12px;font-size:0.78rem;font-weight:500;margin-top:6px;display:inline-block;">'
        f'✓ {filename}</div>',
        unsafe_allow_html=True,
    )

with col_id:
    _upload_label("🪪", "Government ID")
    id_file = st.file_uploader("Government ID", type=["pdf","txt"], key="id_doc", label_visibility="collapsed")
    if id_file:
        _attached_pill(id_file.name)

with col_pay:
    _upload_label("💼", "Income proof")
    payslip_file = st.file_uploader("Income proof", type=["pdf","txt"], key="payslip_doc", label_visibility="collapsed")
    if payslip_file:
        _attached_pill(payslip_file.name)

with col_bank:
    _upload_label("🏦", "Bank statement")
    bank_file = st.file_uploader("Bank statement", type=["pdf","txt"], key="bank_doc", label_visibility="collapsed")
    if bank_file:
        _attached_pill(bank_file.name)

docs_complete = all([id_file, payslip_file, bank_file])

st.markdown("<div style='height:0.25rem'></div>", unsafe_allow_html=True)

if docs_complete:
    st.markdown(
        '<div style="background:#C3EFAB;color:#0A2000;border-radius:9999px;'
        'padding:6px 16px;font-size:0.82rem;font-weight:500;display:inline-block;">✅ All three documents attached</div>',
        unsafe_allow_html=True,
    )
else:
    missing = [n for n, f in [("Government ID", id_file), ("Income proof", payslip_file), ("Bank statement", bank_file)] if not f]
    st.markdown(
        f'<div style="background:#FFDDB3;color:#5C3C00;border-radius:9999px;'
        f'padding:6px 16px;font-size:0.82rem;font-weight:500;display:inline-block;">'
        f'Missing: {", ".join(missing)}</div>',
        unsafe_allow_html=True,
    )

st.divider()

submit_disabled = not (applicant_name and applicant_address and docs_complete)
submitted = st.button("Submit for processing →", disabled=submit_disabled, type="primary")

# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------
if submitted:
    if not applicant_name or not applicant_address:
        st.error("Applicant name and address are required.")
        st.stop()

    def _read_file(f) -> str:
        try:
            raw = f.read()
            ext = "." + f.name.rsplit(".", 1)[-1].lower() if "." in f.name else ""
            if ext == ".pdf":
                try:
                    from io import BytesIO
                    from pypdf import PdfReader
                    pages = [p.extract_text() for p in PdfReader(BytesIO(raw)).pages]
                    text = "\n\n".join(t for t in pages if t)
                    return text if text.strip() else f"[PDF extraction returned no content for {f.name}]"
                except Exception as e:
                    return f"[PDF parsing failed for {f.name}: {e}]"
            try:
                return raw.decode("utf-8")
            except Exception:
                return f"[Could not decode {f.name} as text.]"
        except Exception as e:
            return f"[File read error for {f.name}: {e}]"

    raw_documents = {
        "id":             _read_file(id_file),
        "payslip":        _read_file(payslip_file),
        "bank_statement": _read_file(bank_file),
    }

    idempotency_key = new_idempotency_key()
    factory = get_uow_factory()

    with UnitOfWork(factory) as uow:
        app = uow.applications.create(
            applicant_name=applicant_name,
            applicant_address=applicant_address,
            idempotency_key=idempotency_key,
            raw_payload_ref=f"upload:{idempotency_key}",
        )
        uow.commit()
        application_id = app.application_id

    status_placeholder = st.empty()
    progress_bar = st.progress(0)

    steps = [
        (15, "📄 Extracting document fields…"),
        (35, "✅ Validating document consistency…"),
        (55, "📊 Scoring policy factors…"),
        (70, "⚖️ Running identity-blind consistency check…"),
        (85, "📝 Composing recommendation…"),
        (95, "🔒 Finalising audit record…"),
    ]

    import threading
    result_container: dict = {"result": None, "error": None}

    def _run_agent():
        try:
            from src.agent import run_agent
            result_container["result"] = run_agent(
                application_id=application_id,
                applicant_name=applicant_name,
                applicant_address=applicant_address,
                raw_documents=raw_documents,
                idempotency_key=idempotency_key,
            )
        except Exception as e:
            result_container["error"] = str(e)

    agent_thread = threading.Thread(target=_run_agent)
    agent_thread.start()

    start_time = time.time()
    step_idx = 0
    soft_shown = False

    while agent_thread.is_alive():
        elapsed = time.time() - start_time
        if step_idx < len(steps):
            prog, msg = steps[step_idx]
            if elapsed > (step_idx + 1) * 4:
                step_idx += 1
            status_placeholder.info(msg)
            progress_bar.progress(prog)
        if elapsed > 20 and not soft_shown:
            status_placeholder.info(f"⏳ This can take up to a minute — progress is saved.\n\nElapsed: {int(elapsed)}s")
            soft_shown = True
        time.sleep(0.5)

    agent_thread.join()
    progress_bar.progress(100)

    if result_container["error"]:
        status_placeholder.error(f"Agent error: {result_container['error']}")
        st.stop()

    result = result_container["result"]
    final_status = result.get("final_status") if result else "PROCESSING_ERROR"
    status_placeholder.empty()
    progress_bar.empty()

    if final_status == "PENDING_HUMAN_REVIEW":
        st.success(f"✅ Processing complete. Application **{application_id[:8]}…** is ready for review.")
        st.session_state["review_application_id"] = application_id
        st.switch_page("pages/detail.py")
    elif final_status == "AWAITING_DOCUMENTS":
        st.warning("⚠️ Some documents were not detected. Please re-upload the complete set.")
    elif final_status == "NEEDS_MANUAL_VERIFICATION":
        st.warning("🔍 One or more fields have low confidence — application added to queue for verification.")
        st.session_state["review_application_id"] = application_id
        st.switch_page("pages/detail.py")
    elif final_status == "INCONSISTENT_DOCUMENTS":
        st.error("❌ Document consistency checks failed. Review the application in the queue.")
        st.session_state["review_application_id"] = application_id
        st.switch_page("pages/detail.py")
    else:
        st.error(f"Processing ended with status: {final_status}. Check the Review Queue.")

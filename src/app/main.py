"""
src/app/main.py

Screen 1 — New Application
Intake form + document upload → runs LangGraph agent → navigates to detail view.

All scoring-relevant fields (income, DTI, bureau score, tenure, etc.) are extracted
by the agent from the uploaded documents. Only identity fields (name, address) and
the requested loan amount are collected here — everything else comes from the docs.
"""
from __future__ import annotations

import time

import streamlit as st

from src.app.ui_helpers import get_uow_factory, new_idempotency_key, render_sidebar
from src.repository import UnitOfWork

st.set_page_config(
    page_title="Loan Processing — New Application",
    page_icon="🏦",
    layout="wide",
)

underwriter_id, role = render_sidebar()

st.title("📝 New Application")
st.caption("Submit a new loan application for automated policy assessment.")

# ---------------------------------------------------------------------------
# Intake form — all widgets are intentionally outside st.form().
#
# st.form() batches widget state and only commits it on submit, which means
# every widget inside a form reads as its default value (empty / None) on
# every render pass *before* the submit button is clicked.  That makes it
# impossible to reactively enable/disable the submit button based on widget
# values, because those values are never available until after you've already
# clicked submit.  Using plain widgets + st.button() avoids this entirely.
# ---------------------------------------------------------------------------
st.subheader("Applicant Details")
col_name, col_address = st.columns([1, 2])
with col_name:
    applicant_name = st.text_input("Full name *", placeholder="Jane Smith")
with col_address:
    applicant_address = st.text_input("Address *", placeholder="12 Main St, Springfield")

st.divider()
st.subheader("Required Documents")
st.caption(
    "All three documents are required. The agent will extract income, bureau score, "
    "employment tenure, and all other scoring fields directly from these files."
)

col_id, col_pay, col_bank = st.columns(3)
with col_id:
    id_file = st.file_uploader(
        "🪪 Government ID *",
        type=["pdf", "txt"],
        key="id_doc",
    )
with col_pay:
    payslip_file = st.file_uploader(
        "💼 Income proof (payslip / employer letter) *",
        type=["pdf", "txt"],
        key="payslip_doc",
    )
with col_bank:
    bank_file = st.file_uploader(
        "🏦 Bank statement (most recent period) *",
        type=["pdf", "txt"],
        key="bank_doc",
    )

docs_complete = all([id_file, payslip_file, bank_file])
if docs_complete:
    st.success("✅ All three documents attached.")
else:
    missing = []
    if not id_file:
        missing.append("Government ID")
    if not payslip_file:
        missing.append("Income proof")
    if not bank_file:
        missing.append("Bank statement")
    st.warning(f"Missing: {', '.join(missing)}")

st.divider()
submit_disabled = not (applicant_name and applicant_address and docs_complete)
submitted = st.button(
    "🚀 Submit for Processing",
    disabled=submit_disabled,
    type="primary",
    use_container_width=False,
)

# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------
if submitted:
    if not applicant_name or not applicant_address:
        st.error("Applicant name and address are required.")
        st.stop()

    # Read document text (supports PDF and plain text)
    def _read_file(f) -> str:
        try:
            raw = f.read()
            ext = "." + f.name.rsplit(".", 1)[-1].lower() if "." in f.name else ""

            # PDF: extract text with pypdf
            if ext == ".pdf":
                try:
                    from io import BytesIO
                    from pypdf import PdfReader
                    pdf_reader = PdfReader(BytesIO(raw))
                    text_parts = [page.extract_text() for page in pdf_reader.pages]
                    extracted = "\n\n".join(t for t in text_parts if t)
                    return extracted if extracted.strip() else f"[PDF text extraction returned no content for {f.name}]"
                except Exception as pdf_err:
                    return f"[PDF parsing failed for {f.name}: {pdf_err}]"

            # Plain text
            try:
                return raw.decode("utf-8")
            except Exception:
                return f"[Could not decode {f.name} as text. Please upload a PDF or .txt file.]"
        except Exception as e:
            return f"[File read error for {f.name}: {e}]"

    raw_documents = {
        "id": _read_file(id_file),
        "payslip": _read_file(payslip_file),
        "bank_statement": _read_file(bank_file),
    }

    # Create the application record first
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

    # Run the agent with a progress display
    status_placeholder = st.empty()
    progress_bar = st.progress(0)

    steps = [
        (15, "📄 Running intake → extracting document fields…"),
        (35, "✅ Validating document consistency…"),
        (55, "📊 Scoring policy factors…"),
        (70, "⚖️ Running identity-blind consistency check…"),
        (85, "📝 Composing recommendation…"),
        (95, "🔒 Finalising audit record…"),
    ]

    import threading
    result_container = {"result": None, "error": None}

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
    soft_threshold_shown = False

    while agent_thread.is_alive():
        elapsed = time.time() - start_time
        if step_idx < len(steps):
            prog, msg = steps[step_idx]
            # Advance step display roughly every few seconds
            if elapsed > (step_idx + 1) * 4:
                step_idx += 1
            status_placeholder.info(msg)
            progress_bar.progress(prog)
        if elapsed > 20 and not soft_threshold_shown:
            status_placeholder.info(
                f"⏳ This can take up to a minute — you can navigate away and come back; progress is saved.\n\n"
                f"Elapsed: {int(elapsed)}s"
            )
            soft_threshold_shown = True
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
        st.warning("⚠️ Some documents were not detected. Please re-upload the complete document set.")
    elif final_status == "NEEDS_MANUAL_VERIFICATION":
        st.warning(
            "🔍 One or more extracted fields have low confidence and need manual verification. "
            "The application has been added to the queue."
        )
        st.session_state["review_application_id"] = application_id
        st.switch_page("pages/detail.py")
    elif final_status == "INCONSISTENT_DOCUMENTS":
        st.error("❌ Document consistency checks failed. Please review the application in the queue.")
        st.session_state["review_application_id"] = application_id
        st.switch_page("pages/detail.py")
    else:
        st.error(f"Processing ended with status: {final_status}. Check the Review Queue.")

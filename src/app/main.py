"""
src/app/main.py

Screen 1 — New Application
Intake form + document upload → runs LangGraph agent → navigates to detail view.
"""
from __future__ import annotations

import time
import uuid

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
# Form
# ---------------------------------------------------------------------------
with st.form("intake_form"):
    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.subheader("Applicant Details")
        applicant_name = st.text_input("Full name *", placeholder="Jane Smith")
        applicant_address = st.text_input("Address *", placeholder="12 Main St, Springfield")
        requested_amount = st.number_input("Requested loan amount ($)", min_value=0, value=25000, step=1000)
        st.caption("The fields below are collected for form completeness — the agent will extract and verify them from your uploaded documents.")
        stated_income = st.number_input("Stated monthly income ($)", min_value=0, value=5000, step=100)
        stated_debt = st.number_input("Stated monthly debt obligations ($)", min_value=0, value=800, step=50)
        employer = st.text_input("Employer name", placeholder="Acme Corp")
        notes = st.text_area(
            "Application notes (optional)",
            placeholder="Any additional context for the underwriter.",
            height=80,
        )

    with col_right:
        st.subheader("Required Documents")
        st.caption("All three documents must be uploaded before submission.")

        id_file = st.file_uploader(
            "🪪 Government ID *",
            type=["pdf", "txt", "png", "jpg"],
            key="id_doc",
        )
        payslip_file = st.file_uploader(
            "💼 Income proof (payslip / employer letter) *",
            type=["pdf", "txt", "png", "jpg"],
            key="payslip_doc",
        )
        bank_file = st.file_uploader(
            "🏦 Bank statement (most recent period) *",
            type=["pdf", "txt", "png", "jpg"],
            key="bank_doc",
        )

        docs_complete = all([id_file, payslip_file, bank_file])
        if docs_complete:
            st.success("✅ All three documents attached.")
        else:
            missing = []
            if not id_file: missing.append("Government ID")
            if not payslip_file: missing.append("Income proof")
            if not bank_file: missing.append("Bank statement")
            st.warning(f"Missing: {', '.join(missing)}")

    st.divider()
    submit_disabled = not (applicant_name and applicant_address and docs_complete)
    submitted = st.form_submit_button(
        "🚀 Submit for Processing",
        disabled=submit_disabled,
        type="primary",
    )

# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------
if submitted:
    if not applicant_name or not applicant_address:
        st.error("Applicant name and address are required.")
        st.stop()

    # Read document text (for demo, treat uploaded files as text content)
    def _read_file(f) -> str:
        try:
            raw = f.read()
            try:
                return raw.decode("utf-8")
            except Exception:
                return f"[Binary file: {f.name}]"
        except Exception:
            return ""

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

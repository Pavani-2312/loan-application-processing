# Actionable Issues - Code Locations & Fixes

**Generated:** July 14, 2026  
**Review of:** Loan Application Processing Agent  

This document provides specific file locations and code fixes for all identified issues.

---

## CRITICAL ISSUE #1: Fairness Check Not Working

### Location
**File:** `src/agent/nodes.py`  
**Function:** `fairness_node()` starting at line ~527  

### Current Code (BROKEN)
```python
def fairness_node(state: AgentState) -> dict[str, Any]:
    """
    Identity-blind extraction consistency check.
    Strips name + address from effective fields, re-runs scoring.
    Compares bands. PASS if identical; FAIL if different.
    """
    application_id = state.get("application_id")
    original_band = state.get("recommendation_band")
    rev = state.get("scoring_revision_number", 1)

    with UnitOfWork(_get_session_factory()) as uow:
        effective_fields = uow.extracted_fields.get_effective_fields(application_id)

    # ❌ PROBLEM: No actual identity redaction happens here
    # Re-scores with SAME numeric fields, bands always match
    blind_result = scoring_node_fairness(application_id, effective_fields, rev)
    
    blind_band = blind_result["band"] if blind_result else original_band
    passed = original_band == blind_band  # Will always be True
```

### Problem
The function claims to "strip name + address" but actually just re-runs scoring with the exact same numeric fields. Since the deterministic scorer only reads numeric inputs (DTI, bureau score, tenure, variability), the bands will ALWAYS match by construction.

### Impact
- Test `test_scenario_4_identity_blind_consistency` passes but is vacuous
- System claims fairness check but doesn't actually detect identity leakage
- Misleading for compliance purposes

### Fix Option A: Implement Correctly

**Add identity redaction before re-extraction:**

```python
def fairness_node(state: AgentState) -> dict[str, Any]:
    """
    Identity-blind extraction consistency check.
    Re-extracts fields from documents with identity redacted.
    """
    application_id = state.get("application_id")
    original_band = state.get("recommendation_band")
    rev = state.get("scoring_revision_number", 1)
    
    # Get original documents
    raw_documents = state.get("raw_documents", {})
    
    # Redact identity from documents
    redacted_docs = {}
    for doc_type, content in raw_documents.items():
        redacted = content.replace(state.get("applicant_name"), "[REDACTED NAME]")
        redacted = redacted.replace(state.get("applicant_address"), "[REDACTED ADDRESS]")
        redacted_docs[doc_type] = redacted
    
    # Re-run extraction with redacted documents
    redacted_extraction_state = {
        "application_id": application_id,
        "applicant_name": "[REDACTED]",
        "applicant_address": "[REDACTED]",
        "raw_documents": redacted_docs,
        "scoring_revision_number": rev,
    }
    
    # Re-extract and re-score
    extraction_result = intake_node(redacted_extraction_state)
    validation_result = validation_node({**redacted_extraction_state, **extraction_result})
    
    if validation_result.get("validation_passed"):
        scoring_result = scoring_node_fairness(
            application_id, 
            extraction_result.get("extracted_fields"),
            rev
        )
        blind_band = scoring_result["band"] if scoring_result else original_band
    else:
        # If validation fails on redacted docs, that itself is a fairness issue
        blind_band = "FAIL_VALIDATION"
    
    passed = original_band == blind_band
    disparity = None if passed else (
        f"Band changed from {original_band} to {blind_band} after identity redaction. "
        "Indicates identity information influenced extraction."
    )
    
    # ... rest of function (persist fairness_check row)
```

**Effort:** 1 day (includes updating test to be non-vacuous)

### Fix Option B: Remove Fairness Node

**If deterministic scorer + structured extraction means identity can't leak:**

1. Delete `fairness_node()` from `src/agent/nodes.py`
2. Remove from graph in `src/agent/graph.py`
3. Update documentation to explain:

```markdown
## Why No Fairness Check?

The system's architecture makes identity leakage structurally impossible:

1. The deterministic scorer accepts only numeric fields (DTI, bureau score, etc.)
2. These fields are extracted via structured Pydantic schemas
3. Name/address are never passed to the scoring function
4. Therefore, identity cannot mathematically influence the score

A fairness check that re-scores with identity removed would always pass
by construction, providing no additional assurance. Instead, we rely on:
- Architectural separation (scorer signature enforces numeric-only inputs)
- Test coverage (test_scoring_deterministic verifies reproducibility)
- Audit trail (every extraction value has evidence span pointing to source text)
```

4. Remove test `test_scenario_4_identity_blind_consistency`
5. Update `01_Requirements.md` to remove FR-09, FR-10

**Effort:** 2-4 hours

### Recommendation
**Choose Option B** (remove) unless you need to demo fairness checking for stakeholders. The current implementation provides no value and Option A is complex to test properly.

---

## CRITICAL ISSUE #2: Audit Package Export Missing

### Location
**File:** `src/app/pages/audit_detail.py`  
**Line:** 194 (button exists, backend incomplete)

### Current Code (INCOMPLETE)
```python
st.subheader("📦 Generate Audit Package")
st.caption("Export a standalone document containing all audit data for this application.")

# Button exists but doesn't do anything
if st.button("📄 Generate PDF Package"):
    st.info("PDF generation not yet implemented - see full data above")
```

### Fix: Implement PDF Export

**Add PDF generation using ReportLab:**

```python
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
import json

def generate_audit_package_pdf(application_id: str, factory) -> BytesIO:
    """Generate comprehensive audit package as PDF."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    with UnitOfWork(factory) as uow:
        app = uow.applications.get(application_id)
        extracted_all = uow.extracted_fields.get_all_versions(application_id)
        scores = uow.score_breakdowns.get_all(application_id)
        recs = uow.recommendations.get_all(application_id)
        fairness = uow.fairness_checks.get_all(application_id)
        guardrails = uow.guardrail_flags.get_all(application_id)
        decisions = uow.human_decisions.get_all(application_id)
        audit_events = uow.audit_logs.get_all(application_id)
    
    # Title
    story.append(Paragraph(f"Audit Package: {application_id}", styles['Title']))
    story.append(Spacer(1, 0.3*inch))
    
    # Application Info
    story.append(Paragraph("Application Information", styles['Heading1']))
    app_data = [
        ["Applicant", app.applicant_name],
        ["Address", app.applicant_address],
        ["Submitted", app.submitted_at.strftime("%Y-%m-%d %H:%M UTC")],
        ["Status", app.status],
    ]
    story.append(Table(app_data, colWidths=[2*inch, 4*inch]))
    story.append(Spacer(1, 0.3*inch))
    
    # Extracted Fields (All Versions)
    story.append(Paragraph("Extracted Fields (All Versions)", styles['Heading1']))
    by_field = {}
    for field in extracted_all:
        by_field.setdefault(field.field_name, []).append(field)
    
    for field_name, versions in by_field.items():
        story.append(Paragraph(f"<b>{field_name}</b>", styles['Heading2']))
        field_data = [["Version", "Value", "Confidence", "Verified", "Evidence"]]
        for v in sorted(versions, key=lambda x: x.field_version):
            field_data.append([
                str(v.field_version),
                str(v.field_value)[:30],
                v.confidence or "—",
                "✓" if v.manually_verified else "✗",
                (v.evidence_span or "")[:50],
            ])
        story.append(Table(field_data, colWidths=[0.6*inch, 1.5*inch, 0.8*inch, 0.6*inch, 2*inch]))
        story.append(Spacer(1, 0.2*inch))
    
    # Score Breakdowns (All Revisions)
    story.append(Paragraph("Score Breakdowns (All Revisions)", styles['Heading1']))
    revisions = {}
    for score in scores:
        revisions.setdefault(score.revision_number, []).append(score)
    
    for rev_num in sorted(revisions.keys()):
        story.append(Paragraph(f"Revision {rev_num}", styles['Heading2']))
        score_data = [["Factor", "Raw Value", "Score", "Band", "Clause"]]
        for s in revisions[rev_num]:
            if not s.is_fairness_run and s.sub_factor is None:  # Show factor-level only
                score_data.append([
                    s.factor,
                    f"{s.raw_value:.3f}",
                    f"{s.normalized_score:.3f}",
                    s.band_label,
                    s.cited_clause_id,
                ])
        story.append(Table(score_data, colWidths=[1.5*inch, 1*inch, 0.8*inch, 1*inch, 1.2*inch]))
        story.append(Spacer(1, 0.2*inch))
    
    # Recommendations (All Revisions)
    story.append(Paragraph("Recommendations", styles['Heading1']))
    for rec in recs:
        story.append(Paragraph(
            f"<b>Revision {rec.revision_number}:</b> {rec.band} "
            f"(score: {rec.composite_score:.3f})",
            styles['Heading2']
        ))
        story.append(Paragraph(rec.explanation_text, styles['Normal']))
        story.append(Spacer(1, 0.2*inch))
    
    # Fairness Checks
    if fairness:
        story.append(Paragraph("Fairness Checks", styles['Heading1']))
        for fc in fairness:
            fc_text = (
                f"Revision {fc.revision_number}: {fc.result} - "
                f"Original={fc.original_band}, Blind={fc.blind_band}"
            )
            if fc.disparity_detail:
                fc_text += f"<br/>{fc.disparity_detail}"
            story.append(Paragraph(fc_text, styles['Normal']))
        story.append(Spacer(1, 0.2*inch))
    
    # Guardrail Flags
    if guardrails:
        story.append(Paragraph("Guardrail Flags", styles['Heading1']))
        for g in guardrails:
            story.append(Paragraph(
                f"<b>{g.field}:</b> {g.excerpt[:100]}... - <i>{g.reason}</i>",
                styles['Normal']
            ))
        story.append(Spacer(1, 0.2*inch))
    
    # Human Decisions
    story.append(Paragraph("Human Decision History", styles['Heading1']))
    for d in decisions:
        decision_text = (
            f"<b>{d.sequence_number}. {d.decision}</b> by {d.underwriter_id} "
            f"at {d.decided_at.strftime('%Y-%m-%d %H:%M')}<br/>"
            f"Recommendation at time: {d.recommendation_at_time}<br/>"
            f"Rationale: {d.rationale}"
        )
        if d.refer_reason:
            decision_text += f"<br/>Refer reason: {d.refer_reason}"
        if d.is_terminal:
            decision_text += "<br/><b>TERMINAL DECISION</b>"
        story.append(Paragraph(decision_text, styles['Normal']))
        story.append(Spacer(1, 0.2*inch))
    
    # Audit Event Timeline
    story.append(Paragraph("Audit Event Timeline", styles['Heading1']))
    for event in audit_events:
        event_text = (
            f"<b>{event.event_type}</b> at {event.occurred_at.strftime('%Y-%m-%d %H:%M')}<br/>"
            f"<i>{json.dumps(json.loads(event.event_payload), indent=2)[:200]}...</i>"
        )
        story.append(Paragraph(event_text, styles['Normal']))
        story.append(Spacer(1, 0.1*inch))
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    return buffer

# In the Streamlit UI:
if st.button("📄 Generate PDF Package"):
    pdf_buffer = generate_audit_package_pdf(application_id, factory)
    st.download_button(
        label="⬇️ Download Audit Package (PDF)",
        data=pdf_buffer,
        file_name=f"audit_package_{application_id[:12]}.pdf",
        mime="application/pdf",
    )
```

**Effort:** 1-2 days (including formatting polish)

**Alternative:** Use HTML export instead of PDF (easier):
```python
def generate_audit_package_html(application_id: str, factory) -> str:
    """Generate audit package as standalone HTML."""
    # Same data queries as PDF version
    # Render using Jinja2 template or f-strings
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Audit Package {application_id}</title>
        <style>
            body {{ font-family: sans-serif; max-width: 800px; margin: 0 auto; }}
            h1 {{ color: #1e3a8a; }}
            table {{ border-collapse: collapse; width: 100%; margin: 1em 0; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background-color: #f3f4f6; }}
        </style>
    </head>
    <body>
        <!-- Same content as PDF version -->
    </body>
    </html>
    """
    return html
```

---

## MAJOR ISSUE #3: No Authentication

### Location
**Multiple files:**
- `src/app/ui_helpers.py` - Role selector (line 73)
- `src/agent/human_gate.py` - Accepts unverified identity (line 39)
- All Streamlit pages - No auth checks

### Current Code (INSECURE)
```python
# src/app/ui_helpers.py
def render_sidebar():
    """Render role selector - NO VERIFICATION"""
    role = st.sidebar.selectbox("Role", ["Underwriter", "Credit Ops Lead"])
    if role == "Underwriter":
        underwriter_id = st.sidebar.text_input("Name", value="Jane Smith")
    # ... anyone can type any name
    return underwriter_id, role
```

### Fix: Add Real Authentication

**Option A: Streamlit-Authenticator (Quick)**

```python
# pip install streamlit-authenticator

import streamlit_authenticator as stauth

# config.yaml
credentials:
  usernames:
    jsmith:
      name: Jane Smith
      password: $2b$12$...  # bcrypt hash
      role: underwriter
    rjones:
      name: Robert Jones  
      password: $2b$12$...
      role: credit_ops_lead

# src/app/ui_helpers.py
def render_sidebar():
    """Render authentication and role check."""
    authenticator = stauth.Authenticate(
        credentials,
        cookie_name='loan_app_auth',
        key='loan_app_secret_key',
        cookie_expiry_days=1,
    )
    
    name, authentication_status, username = authenticator.login('Login', 'sidebar')
    
    if authentication_status == False:
        st.sidebar.error('Username/password incorrect')
        st.stop()
    elif authentication_status == None:
        st.sidebar.warning('Please enter username and password')
        st.stop()
    
    # Authenticated - show user info
    role = credentials['usernames'][username]['role']
    st.sidebar.success(f'Logged in as {name} ({role})')
    authenticator.logout('Logout', 'sidebar')
    
    return username, role
```

**Option B: OAuth/SAML SSO (Production)**

```python
# Use organization's existing SSO
# Example with Okta/Auth0:

from authlib.integrations.requests_client import OAuth2Session

def render_sidebar():
    """SSO authentication."""
    if 'access_token' not in st.session_state:
        # Redirect to SSO login
        auth_url = oauth.authorization_url(AUTHORIZATION_URL)
        st.markdown(f'[Login via SSO]({auth_url})')
        st.stop()
    
    # Validate token, extract claims
    user_info = validate_token(st.session_state.access_token)
    username = user_info['email']
    role = user_info['app_role']  # from SAML assertion
    
    return username, role
```

**Then in human_gate.py, add cryptographic signature:**

```python
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
import json

def record_human_decision(
    application_id: str,
    underwriter_id: str,
    session_token: str,  # From authenticated session
    decision: str,
    rationale: str,
    refer_reason: str | None = None,
) -> dict:
    """Record decision with cryptographic proof of identity."""
    
    # Verify session token
    user_info = validate_session_token(session_token)
    if user_info['username'] != underwriter_id:
        raise HumanDecisionError("Token does not match underwriter_id")
    
    # Create signature
    decision_data = {
        "application_id": application_id,
        "underwriter_id": underwriter_id,
        "decision": decision,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    signature = sign_data(json.dumps(decision_data), user_info['private_key'])
    
    # Store signature with decision
    decision_row = uow.human_decisions.add(
        # ... existing fields ...
        digital_signature=signature,
        signer_public_key=user_info['public_key'],
    )
```

**Effort:** 
- Option A (Quick): 1 day
- Option B (Production): 5-10 days

---

## Minor Issues (Optional Fixes)

### Issue #4: Chroma Semantic Search Not Exposed

**Location:** `src/app/pages/detail.py` (add to policy clause section)

**Quick Fix:**
```python
# Add after score breakdown table
st.subheader("📚 Policy Search")
search_query = st.text_input("Search policy clauses", placeholder="e.g., 'income stability requirements'")

if search_query:
    import chromadb
    client = chromadb.PersistentClient(path=str(get_chroma_dir()))
    collection = client.get_collection("credit_policy_clauses")
    results = collection.query(query_texts=[search_query], n_results=5)
    
    for i, doc in enumerate(results['documents'][0]):
        clause_id = results['ids'][0][i]
        st.markdown(f"**{clause_id}:** {doc}")
```

**Effort:** 2 hours

### Issue #5: No Real-Time Timeout Feedback

**Location:** `src/app/main.py` (progress display)

**Quick Fix:**
```python
import time

start_time = time.time()
while agent_running:
    elapsed = time.time() - start_time
    if elapsed > 25:
        status_placeholder.warning(
            f"⏱️ Processing taking longer than usual ({elapsed:.0f}s). "
            "This can happen with API rate limits. Progress is saved; "
            "you can navigate away and return later."
        )
```

**Effort:** 30 minutes

---

## Testing the Fixes

### Test Fairness Check Fix (if implementing Option A)

```python
def test_fairness_check_detects_identity_leakage():
    """Adversarial test - name should NOT influence numeric extraction."""
    # Create two applications with different names but identical documents
    app1 = _make_app(factory, name="John Smith", address="123 Main St")
    app2 = _make_app(factory, name="Ahmed Hassan", address="456 Oak Ave")
    
    # Use documents where name might influence LLM judgment
    # E.g., employer name extraction could be biased
    docs = {
        "id": "Government ID",
        "payslip": "Payslip from [employer name handwritten, ambiguous]",
        "bank_statement": "Bank statement"
    }
    
    state1 = _base_state(app1, "John Smith", "123 Main St")
    state1["raw_documents"] = docs
    
    state2 = _base_state(app2, "Ahmed Hassan", "456 Oak Ave") 
    state2["raw_documents"] = docs
    
    # Run both through full pipeline
    final1 = run_agent(**state1)
    final2 = run_agent(**state2)
    
    # Assert same recommendation despite different names
    assert final1["recommendation_band"] == final2["recommendation_band"]
    
    # Now test the fairness check catches actual leakage
    # (Would need to inject a bug that makes name influence score)
```

### Test Audit Package Export

```python
def test_audit_package_contains_all_revisions():
    """Verify export includes corrected fields and re-scored revisions."""
    app_id = _make_app(factory)
    
    # Submit with low-confidence field
    state = _base_state(app_id)
    state["low_confidence_field"] = "bureau_score"
    final_state = run_agent(**state)
    
    # Correct the field (triggers re-score)
    with UnitOfWork(factory) as uow:
        uow.extracted_fields.upsert_field(
            app_id, "bureau_score", "720", 
            field_version=2, manually_verified=True
        )
    
    resume_from_scoring(app_id, "test_underwriter")
    
    # Generate audit package
    pdf_buffer = generate_audit_package_pdf(app_id, factory)
    pdf_text = extract_text_from_pdf(pdf_buffer)  # Helper function
    
    # Verify it contains both revisions
    assert "Revision 1" in pdf_text
    assert "Revision 2" in pdf_text
    assert "bureau_score" in pdf_text
    assert "Version 1" in pdf_text  # Original extraction
    assert "Version 2" in pdf_text  # Correction
```

---

## Priority Order

**Week 1:**
1. Fix or remove fairness check (1 day)
2. Implement audit package export (2 days)

**Week 2:**
3. Add authentication (5 days)

**Week 3:**
4. Add Chroma semantic search to UI (0.5 day)
5. Add timeout feedback (0.5 day)
6. Final testing and documentation updates (4 days)

**Total: 13 developer-days to production-ready**

---

*End of actionable issues document*

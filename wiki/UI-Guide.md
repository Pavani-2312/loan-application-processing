# UI Guide

The Streamlit dashboard has four screens. Open at `http://localhost:8501` after running `./run.sh`.

## Sidebar (all screens)

Select your underwriter identity from the dropdown before taking any action. **Note:** this is self-reported and not cryptographically verified in this build — see [[Known-Limitations]] (L1).

---

## Screen 1 — New Application (`/`)

Submit a new loan application for automated processing.

**Steps:**
1. Enter applicant full name and residential address.
2. Upload all three documents (PDF or TXT):
   - Government ID
   - Income proof (payslip / employer letter)
   - Bank statement
3. Click **Submit for processing →**

The button is disabled until all three documents are attached and name/address are filled.

A progress indicator shows each pipeline stage. Processing typically takes 20–60 seconds depending on API latency. If it takes longer, the status bar shows elapsed time — progress is saved and you can navigate away.

**On completion:**
- `PENDING_HUMAN_REVIEW` → redirects to Application Detail
- `NEEDS_MANUAL_VERIFICATION` → redirects to Application Detail (fields need correction)
- `INCONSISTENT_DOCUMENTS` → redirects to Application Detail (validation failed)
- Any error → message shown on screen

---

## Screen 2 — Review Queue (`/pages/queue`)

Lists all applications with status, recommendation band, fairness result, and guardrail flags.

**Filters:**
- Status (multi-select)
- Recommendation band (APPROVE / REFER / DECLINE)
- Fairness check (All / PASS / FAIL / Not yet checked)

Applications are sorted by priority: `PENDING_HUMAN_REVIEW` and `NEEDS_MANUAL_VERIFICATION` first, then `REFERRED_FOR_ESCALATION`, then all others.

**Status colours:**
- Blue border — `PENDING_HUMAN_REVIEW`
- Purple border — `REFERRED_FOR_ESCALATION`
- Amber border — `NEEDS_MANUAL_VERIFICATION`, `INCONSISTENT_DOCUMENTS`
- Red border — `PROCESSING_ERROR`, `POLICY_CONFIG_ERROR`
- Green border — `DECIDED`
- Grey border — `AWAITING_DOCUMENTS`

Click **Review →** (or the specific action button) to open the detail page for any application.

---

## Screen 3 — Application Detail (`/pages/detail`)

The main underwriting workspace.

**Sections:**

**Guardrail banner** (if present) — shown at the top if any free-text field triggered an adversarial content flag. The score is not affected; the flag is for underwriter awareness.

**Recommendation card** — colour-coded by band (green = APPROVE, amber = REFER, red = DECLINE). Shows composite score and the LLM-generated explanation citing specific policy clauses.

**Score breakdown table** — per-factor raw values, band labels, weighted contributions, and cited clause IDs. Includes a composite row.

**Fairness panel** — shows PASS or FAIL with original vs blind band. On FAIL, shows which factor changed and details of the disparity.

**Document validation** (expandable) — all four consistency check results with evidence text.

**Extracted fields table** — all fields extracted from documents with:
- Value (monospace)
- Source document
- Evidence span (the literal text it was read from)
- Confidence badge (green = high, amber = medium, red = low)
- **✏️ Correct** button on low-confidence scoring-relevant fields (only shown when status = `NEEDS_MANUAL_VERIFICATION`)

**Correction flow:** click Correct → enter corrected value and reason → Save & Re-score. The pipeline re-runs from ScoringNode forward with the corrected value.

**Decision history** — all prior REFER events with rationale and timestamp.

**Decision form** (shown when status = `PENDING_HUMAN_REVIEW` or `REFERRED_FOR_ESCALATION`):
- Choose APPROVE / REFER / DECLINE
- If REFER: select a refer reason (required)
- Enter rationale (required)
- A warning is shown if your decision differs from the system recommendation
- Click **Record Decision →**

---

## Screen 4 — Audit Explorer (`/pages/audit`)

KPI summary and application audit history.

**KPIs shown:**
- Total applications by status
- Straight-through approval rate (decisions matching agent recommendation)
- Fairness pass rate
- Average processing time

Click any application to open the **Audit Detail** page, which shows:
- Full audit event timeline
- All extracted field versions (original + any corrections)
- All score revisions
- All decision events

**Generate Audit Package** button — exports a standalone HTML file containing the complete application record, suitable for regulatory handoff without requiring database access.

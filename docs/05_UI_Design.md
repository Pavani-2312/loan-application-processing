# 05 · UI Design Document
## Project 05 — Loan / Credit Application Processing Agent (Streamlit)

> Scope note: This document defines screens, layout, and user flow only. It does not repeat what the agent computes (`03_Functional_Specification.md`) or what's stored (`04_Data_Policy_Model.md`) — it describes how those are surfaced and captured.

---

## 1. Information Architecture

Four screens, reachable via a Streamlit sidebar nav:

1. **New Application** — intake form + document upload.
2. **Review Queue** — list of applications `PENDING_HUMAN_REVIEW` / `AWAITING_DOCUMENTS` / `INCONSISTENT_DOCUMENTS`.
3. **Application Detail & Decision** — the core screen: recommendation, evidence, fairness result, decision capture.
4. **Audit Explorer** — searchable/filterable history of all decided applications, export.

A lightweight role selector (`Underwriter` / `Credit Ops Lead`) sits in the sidebar — no real auth in this build (per requirements NFR-07 / scope), but it tags `human_decisions.underwriter_id` and gates access to the Audit Explorer's export function to reflect a production-shaped permission boundary.

**⚠️ Explicit caveat, not hidden in a footnote:** this selector is a convenience dropdown, not identity verification — anyone using the app can select any underwriter name. It is called out in the UI itself (a persistent small sidebar notice: *"Demo mode — underwriter identity is self-selected, not verified. See Known Limitations (L1)."*) so no one mistakes the audit trail's `underwriter_id` for a verified signature. This is a named production blocker in `01_Requirements.md §10`, not a solved problem.

## 2. Screen 1 — New Application

**Purpose:** capture a new application and hand it to the agent.

**Layout:**
- Left column: applicant form (name, address, requested amount, stated monthly income, stated monthly debt, employer, employment start date, free-text "application notes" field).
- Right column: three file-uploader widgets, one per required document (ID, income proof, bank statement), each showing a green check once a file is attached.
- Bottom: primary button **"Submit for Processing."** Disabled until all three files are attached (client-side nudge; the real presence check still runs server-side per FR-02).
- On submit: spinner "Running intake → validation → scoring → fairness check…" while the LangGraph agent runs synchronously; on completion, auto-navigate to Application Detail for this application. Past ~20 seconds elapsed, the spinner adds: *"This can take up to a minute — you can navigate away and come back; progress is saved."* (per `02_Architecture.md`'s per-node durability/resumability design — a slow API call no longer risks losing prior steps.)

**Why this shape:** keeps intake friction low while making the three-document requirement visually explicit before the applicant/officer even hits submit.

## 3. Screen 2 — Review Queue

**Purpose:** triage — what needs a human right now, and what's blocked on documents.

**Layout:** a filterable table.

| Column | Source |
|---|---|
| Application ID | `applications.application_id` |
| Submitted | `applications.submitted_at` |
| Status | `applications.status` (color-coded badge) |
| Recommendation | `recommendations.band` (blank if not yet scored) |
| Fairness | ✅ / ⚠️ badge from `fairness_checks.result` |
| Guardrail flag | 🚩 icon if `guardrail_flags` non-empty for that application |
| Action | "Review →" button |

- Filters at top: Status, Recommendation band, Fairness result, date range.
- Default sort: oldest `PENDING_HUMAN_REVIEW` first (turnaround-time KPI is directly visible from this ordering).
- Rows with `AWAITING_DOCUMENTS` or `INCONSISTENT_DOCUMENTS` show a distinct row style (amber) and their action button reads "Request Documents" instead of "Review," reflecting that these are *not* recommendations awaiting decision — they never reached scoring (FR-04).
- Rows with `NEEDS_MANUAL_VERIFICATION` show an amber row with action "Verify Fields" — routes straight to the Extracted Fields panel (§4.6a) rather than the full recommendation view, since scoring hasn't run yet.
- Rows with `REFERRED_FOR_ESCALATION` show an indigo row with the `refer_reason` visible as a sub-label (e.g., "Escalate to Committee") and action "Continue Review" — these re-enter the same Application Detail screen with their Decision History strip populated.
- `POLICY_CONFIG_ERROR` rows are hidden from the standard Underwriter queue view and surfaced only under the Credit Ops Lead role, since they're an operational/config issue, not an underwriting task.

## 4. Screen 3 — Application Detail & Decision (core screen)

This is the screen that carries the evaluation-layer requirements (trace, output, governance, fairness) into something a human can actually act on.

**Layout — top to bottom:**

1. **Header band:** Application ID, applicant name/address, submitted date, current status badge.
2. **🚩 Guardrail banner** (only shown if flags exist): a highlighted callout — *"This application contains content that appears to instruct the system to bypass policy: '[excerpt]'. This has been ignored; the recommendation below is based solely on policy scoring."* Makes FR-12 visible, not just enforced silently.
3. **Recommendation card:** large band label (APPROVE/REFER/DECLINE) with composite score, and the composed explanation text. For REFER, an explicit line: *"Composite score falls in the referral band — human judgment required on [factor]."*
4. **Score breakdown table** (the transparency requirement, FR-06/FR-08):

   | Factor | Weight | Raw value | Band | Score | Contribution | Policy clause |
   |---|---|---|---|---|---|---|
   | DTI | 40% | 0.34 | Moderate | 0.7 | 0.28 | Clause 3.1(b) — *[expandable to full clause text]* |
   | Credit history | 35% | 705 | Moderate | 0.7 | 0.245 | Clause 4.1(b) |
   | Income stability | 25% | 18 mo / 12% var | Moderate | 0.7 | 0.175 | Clause 5.1(b) |
   | **Composite** | | | | | **0.70** | → REFER (Clause 7.2) |

5. **Identity-Blind Consistency Check panel** *(relabeled from "Fairness check" for scope accuracy — see review note below):*
   - Side-by-side: Original recommendation vs Identity-blind recommendation.
   - ✅ green "No disparity detected — recommendation unchanged" or ⚠️ red "Disparity detected: original=APPROVE, blind=REFER" with both breakdowns expandable underneath for direct comparison.
   - If disparity: a persistent warning stays on screen even after scrolling, since FR-10 requires this to be surfaced, not buried.
   - A small info icon next to the panel title expands to: *"This checks whether identity information leaked into the automated scoring for this one application. It is not a population-level fairness or disparate-impact audit — see Known Limitations (L2)."* This prevents the panel from being read as a broader fairness guarantee than it actually provides.
6. **Document validation panel:** collapsible, showing each of the four consistency checks with pass/fail and the LLM's evidence text — lets the underwriter verify *why* the agent trusted the documents.
6a. **Extracted Fields panel** *(new — closes the "no way to spot-check extraction" gap raised in review):* a table of every field IntakeNode extracted (income, debt, bureau score, tenure, deposits, etc.), each row showing the extracted value, its source document, its **evidence span** (the literal source text it was read from), and a confidence badge (High/Medium/Low). Any field that triggered `NEEDS_MANUAL_VERIFICATION` is shown with an amber highlight and an inline correction control. Confirming or correcting a value here writes a new versioned row (never overwrites the original — see `04_Data_Policy_Model.md §3`) and triggers the agent to resume from scoring onward per `03_Functional_Specification.md §1.2b`; the screen shows a brief "Re-scoring with confirmed values…" spinner and refreshes the recommendation card above once done. If a field was ever corrected, a small "1 prior value" link lets the underwriter see what the model originally extracted before confirmation — this panel is shown for every application, not only flagged ones, so spot-checking is a normal part of every review.
7. **Decision capture form** (the human gate, FR-11) — *revised: REFER is a non-terminal decision, per review*:
   - Radio buttons: Approve / Refer / Decline (defaults to none selected — underwriter must actively choose, never pre-checked to the agent's recommendation).
   - **If Refer is selected:** a required dropdown appears — "Request More Info" / "Escalate to Senior Underwriter" / "Escalate to Committee" (`refer_reason`). The primary button label changes to **"Record Referral"** instead of "Record Final Decision," and helper text clarifies: *"This does not close the application — it will return to the queue for further action."*
   - Required free-text "Rationale" field in all cases.
   - Underwriter identity shown (from sidebar role selector — see the demo-mode caveat in §1).
   - Primary button: **"Record Final Decision"** for Approve/Decline (writes to `human_decisions` with `is_terminal = true`, sets `applications.status = DECIDED`); **"Record Referral"** for Refer (writes to `human_decisions` with `is_terminal = false`, sets `applications.status = REFERRED_FOR_ESCALATION`, application returns to the Review Queue). Either way the form disables after submit and shows a confirmation banner with a permanent record ID.
   - If a prior referral exists for this application, a **Decision History** strip appears above the form showing each past decision event (decision, reason, underwriter, timestamp) in order — so the current reviewer sees the full chain before adding to it.
   - If the underwriter's choice differs from the agent's recommendation, a small inline note appears: *"This differs from the system recommendation — rationale is required and will be recorded."*

## 5. Screen 4 — Audit Explorer

**Purpose:** the screen Compliance/Audit actually uses.

**Layout:**
- Filter bar: date range, status, recommendation band, fairness result (pass/fail), "guardrail flag present" toggle, underwriter.
- Results table: Application ID, submitted date, recommendation, human decision, match/mismatch indicator (straight-through vs overridden), fairness result, decided-by, decided-at.
- Row click → read-only version of the Application Detail screen (same layout as Screen 3, minus the decision form, plus the full `audit_log` event timeline at the bottom as a simple chronological list: `INTAKE → VALIDATION → SCORED → FAIRNESS_CHECKED → RECOMMENDED → GUARDRAIL_FLAGGED (if any) → RESCORED_AFTER_VERIFICATION (if any) → HUMAN_DECIDED (one or more, if REFER chain occurred)`).
- **"Generate Audit Package" button** *(new — closes the review gap that only bulk CSV/JSON export existed, with no self-contained single-application artifact)*: on the detail view, renders everything about that one application — all extraction field versions, all scoring/recommendation/fairness revisions, guardrail flags, and the full decision history — into a standalone PDF/HTML document per `04_Data_Policy_Model.md §3` (`event_payload` schema). This is the artifact meant to actually go to a regulator or auditor, distinct from the bulk filtered export below.
- **Bulk export** button (role-gated to Credit Ops Lead in this build's lightweight role model): downloads the filtered set as CSV/JSON for portfolio-level audit sampling, distinct from the single-application package above.
- A small KPI strip pinned above the table: Decision turnaround (median), Straight-through rate, Fairness pass rate — computed live from the filtered set, giving Credit Ops a running view of the KPIs defined in `01_Requirements.md §5`.

## 6. Visual/Interaction Conventions

- Status badges: grey = `AWAITING_DOCUMENTS`, amber = `INCONSISTENT_DOCUMENTS`, amber (darker, with a magnifier icon) = `NEEDS_MANUAL_VERIFICATION`, dark red (with a wrench icon) = `POLICY_CONFIG_ERROR` (Credit Ops queue, not underwriter queue), blue = `PENDING_HUMAN_REVIEW`, indigo = `REFERRED_FOR_ESCALATION` (shows its `refer_reason` on hover), green = `DECIDED` (approve), red = `DECIDED` (decline).
- Every number shown to the underwriter that came from the scoring engine is shown with its source clause next to it — never a bare number, in service of NFR-01 (explainability).
- Nothing on the Application Detail screen is editable except the decision-capture form — the evidence above it is read-only, reinforcing that it's a record, not a draft.

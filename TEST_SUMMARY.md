# End-to-End Test Summary
**Date:** 2026-07-15  
**Environment:** Local — GitHub Models (gpt-4o), SQLite WAL, Streamlit 1.x  
**Test documents:** `test_docs/scenario_approve/`, `test_docs/scenario_refer/`, `test_docs/scenario_decline/`

---

## Results at a Glance

| Scenario | Applicant | Expected | Actual | Score | Fairness | Status |
|---|---|---|---|---|---|---|
| 1 — APPROVE | Priya Sharma | APPROVE (≥0.75) | ✅ **APPROVE** | **1.000** | ✅ PASS | PENDING_HUMAN_REVIEW |
| 2 — REFER | Arjun Mehta | REFER (0.65–0.75) | ✅ **REFER** | **0.700** | ✅ PASS | PENDING_HUMAN_REVIEW |
| 3 — DECLINE | Ravi Kumar | DECLINE (<0.65) | ⏳ Not yet run | — | — | — |

---

## Scenario 1 — Clear APPROVE (Priya Sharma)

**Documents:** `test_docs/scenario_approve/`  
**Submitted:** 2026-07-15 11:09 UTC  
**Final status:** `PENDING_HUMAN_REVIEW`

### Score Breakdown

| Factor | Raw Value | Band | Score | Weight | Contribution | Clause |
|---|---|---|---|---|---|---|
| DTI | 12,000 / 60,000 = **0.20** | low_risk | 1.00 | 40% | 0.4000 | 3.1(a) |
| Credit History | **750** | low_risk | 1.00 | 35% | 0.3500 | 4.1(a) |
| Income Stability — Tenure | **36 months** | low_risk | 1.00 | — | — | 5.1(a) |
| Income Stability — Variability | **5%** | low_risk | 1.00 | — | — | 5.2(a) |
| Income Stability (combined = min) | — | low_risk | 1.00 | 25% | 0.2500 | 5.1(a), 5.2(a) |
| **Composite** | | | | | **1.0000** | → **APPROVE** |

### Validation Checks
| Check | Result | Evidence |
|---|---|---|
| name_match | ✅ PASS | Names on ID, payslip, and bank statement all match as "Priya Sharma" |
| id_validity | ✅ PASS | ID expiry 14 March 2028 — in future |
| income_plausibility | ✅ PASS | Stated INR 60,000 within ±15% of average deposits INR 60,000 |
| statement_recency | ✅ PASS | Statement period end 30 June 2026 — within 60 days |

### Fairness Check
- **Result:** PASS  
- **Original band:** APPROVE | **Identity-blind band:** APPROVE  
- Identity redaction had no effect on extracted numeric values.

### Agent Explanation
> *"The applicant's DTI of 0.20 falls in the low-risk band per Clause 3.1(a), as it is ≤ 0.30. The credit history, with a simulated bureau score of 750 and no delinquencies in the last 24 months, also falls in the low-risk band per Clause 4.1(a). Additionally, the income stability, with 24+ months of employment and income variability under 10%, is classified as low risk per Clauses 5.1(a) and 5.2(a). These factors collectively support the APPROVE recommendation."*

### Guardrail Flags
None detected.

---

## Scenario 2 — Borderline REFER (Arjun Mehta)

**Documents:** `test_docs/scenario_refer/`  
**Submitted:** 2026-07-15 11:12 UTC  
**Final status:** `PENDING_HUMAN_REVIEW`

### Score Breakdown

| Factor | Raw Value | Band | Score | Weight | Contribution | Clause |
|---|---|---|---|---|---|---|
| DTI | 17,500 / 50,000 = **0.35** | moderate | 0.70 | 40% | 0.2800 | 3.1(b) |
| Credit History | **680** | moderate | 0.70 | 35% | 0.2450 | 4.1(b) |
| Income Stability — Tenure | **18 months** | moderate | 0.70 | — | — | 5.1(b) |
| Income Stability — Variability | **18%** | moderate | 0.70 | — | — | 5.2(b) |
| Income Stability (combined = min) | — | moderate | 0.70 | 25% | 0.1750 | 5.1(b), 5.2(b) |
| **Composite** | | | | | **0.7000** | → **REFER** |

### Validation Checks
| Check | Result | Evidence |
|---|---|---|
| name_match | ✅ PASS | Names on ID, payslip, and bank statement all match as "Arjun Mehta" |
| id_validity | ✅ PASS | ID expiry 01 September 2031 — in future |
| income_plausibility | ✅ PASS | Stated INR 50,000 within ±15% of average deposits INR 50,000 |
| statement_recency | ✅ PASS | Statement period end 30 June 2026 — within 60 days |

### Fairness Check
- **Result:** PASS  
- **Original band:** REFER | **Identity-blind band:** REFER  
- Identity redaction had no effect on extracted numeric values.

### Agent Explanation
> *"The recommendation is REFER due to multiple factors falling into the moderate-risk band. The applicant's DTI of 0.35 is classified as moderate risk per Clause 3.1(b). The credit history score of 680 is also in the moderate-risk band per Clause 4.1(b). Additionally, income stability with 18 months of tenure and variability of 18% is classified as moderate risk per Clauses 5.1(b) and 5.2(b)."*

### Guardrail Flags
None detected.

---

## Scenario 3 — DECLINE (Ravi Kumar)

**Documents:** `test_docs/scenario_decline/`  
**Status:** ⏳ Not yet submitted via UI.

**Expected outcome:**
| Factor | Raw Value | Expected Band | Expected Score | Expected Contribution |
|---|---|---|---|---|
| DTI | 30,000 / 50,000 = 0.60 | high_risk | 0.00 | 0.0000 |
| Credit History | 560 | high_risk | 0.00 | 0.0000 |
| Income Stability — Tenure | 4 months | high_risk | 0.00 | 0.0000 |
| Income Stability — Variability | 45% | high_risk | 0.00 | 0.0000 |
| **Composite** | | | | **0.0000 → DECLINE** |

---

## Observations & Issues Found

### ✅ What worked correctly
1. **Scoring arithmetic is exact** — both composite scores match the hand-calculated values (1.000 and 0.700) to 4 decimal places.
2. **Band boundaries** — APPROVE threshold (≥0.75) and REFER threshold (0.65–0.75) both resolved correctly.
3. **Weakest-link income stability** — combined score used `min(tenure, variability)` correctly; both sub-factors at 0.70 → combined 0.70.
4. **Deterministic citations** — clause IDs from `policy_config.yaml` appeared correctly in breakdowns (3.1(a), 4.1(b), etc.).
5. **Fairness check** — PASS on both; identity redaction did not change extracted numeric fields.
6. **All 4 validation checks passed** — name match, ID validity, income plausibility, statement recency all worked across both scenarios.
7. **Audit trail** — INTAKE, SCORED, FAIRNESS_CHECKED, RECOMMENDED events all present in audit_log for both applications.
8. **Pipeline reaches PENDING_HUMAN_REVIEW** — both applications are correctly awaiting underwriter decision.

### ⚠️ Issues encountered during testing
1. **Submit button permanently disabled** — `st.file_uploader` inside `st.form()` returns `None` until form submission, preventing reactive enable/disable. **Fixed** (commit `fcf262f`): removed `st.form()` entirely, switched to plain `st.button()`.
2. **Two PROCESSING_ERROR applications** — caused by wrong API key format (OpenRouter URL with no key, then wrong model name `openai/gpt-4o`). **Fixed** (commit `264c600`): switched to GitHub Models endpoint + correct plain model ID `gpt-4o`.
3. **Scenario 3 (DECLINE) not yet run** — requires manual UI submission after these fixes were applied.

---

## Requirements Coverage (FR mapping)

| Requirement | Scenario | Result |
|---|---|---|
| FR-01 Intake | 1, 2 | ✅ All 3 document types extracted |
| FR-02 Document presence check | 1, 2 | ✅ All documents present, pipeline continued |
| FR-03 Cross-document consistency | 1, 2 | ✅ All 4 checks passed |
| FR-04 Halt on missing/inconsistent | — | Not triggered (all docs present & consistent) |
| FR-05 Score against policy | 1, 2 | ✅ DTI, credit history, income stability scored |
| FR-06 Itemised score breakdown | 1, 2 | ✅ Per-factor breakdown with sub-factors stored |
| FR-07 One of APPROVE/REFER/DECLINE | 1, 2 | ✅ APPROVE and REFER produced |
| FR-08 Policy clause citations | 1, 2 | ✅ Clause IDs in every breakdown row |
| FR-09 Identity-blind re-score | 1, 2 | ✅ Fairness node ran, bands compared |
| FR-10 Fairness disparity surfaced | 1, 2 | ✅ PASS — no disparity |
| FR-11 Human gate | 1, 2 | ✅ Both in PENDING_HUMAN_REVIEW, not DECIDED |
| FR-12 Guardrail detection | 1, 2 | ✅ No flags (no adversarial content in test docs) |
| FR-13 Full audit record | 1, 2 | ✅ All event types logged |
| FR-14 Append-only corrections | — | Not triggered (no low-confidence fields) |
| FR-16 Confidence + evidence span | 1, 2 | ✅ All fields extracted with confidence=high |

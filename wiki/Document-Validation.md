# Document Validation

## Required documents

A complete application requires exactly three document types:

| Document | Required fields extracted |
|----------|--------------------------|
| Government ID | Applicant name, ID number, expiry date |
| Payslip / income proof | Employer name, stated monthly income, employment tenure |
| Bank statement | Account holder name, statement period, monthly deposits, total obligations |

If any document is absent, the pipeline halts at `AWAITING_DOCUMENTS`. No scoring occurs on partial data.

## Extraction confidence and evidence spans

Every numeric or date field extracted by IntakeNode must include:

- **confidence** — `high` / `medium` / `low` (the model's self-reported certainty)
- **evidence_span** — the literal source text the value was read from (e.g. `"Employment start date: March 2026"`)

This turns silent hallucinations into visible, reviewable failures. A schema-valid but wrong value (e.g., tenure read as `36` instead of `3`) is caught by the confidence mechanism, not by type checking.

**Scoring-relevant fields that trigger `NEEDS_MANUAL_VERIFICATION` on low confidence:**
- `stated_monthly_income`
- `total_monthly_obligations`
- `bureau_score`
- `employment_tenure_months`
- `average_monthly_deposits`
- `income_variability_pct`

## Consistency checks (ValidationNode)

Run only after all three documents are present. Each check returns a structured `{check_name, passed, evidence}` from the LLM. The halt decision is a Python boolean AND — not left to free-form LLM judgment.

| Check | Logic | Failure status |
|-------|-------|----------------|
| `name_match` | Names on ID, payslip, and bank statement refer to the same person (fuzzy — tolerates formatting, not different people) | `INCONSISTENT_DOCUMENTS` |
| `id_validity` | ID expiry date is in the future at time of submission | `INCONSISTENT_DOCUMENTS` |
| `income_plausibility` | Stated monthly income is within ±15% of average bank deposits (Python arithmetic) | `INCONSISTENT_DOCUMENTS` |
| `statement_recency` | Bank statement period end is within 60 days of submission | `INCONSISTENT_DOCUMENTS` |

Any single failed check halts the pipeline. All failed check names and evidence strings are persisted and shown in the UI.

## Low-confidence field correction and re-entry

When an underwriter corrects a low-confidence field via the Application Detail screen:

1. The correction is written as a **new row** in `extracted_fields` with `manually_verified=True` and `is_effective=True`. The original model-extracted row is flipped to `is_effective=False` — never deleted.
2. The pipeline **resumes from ScoringNode** (not IntakeNode — extraction and validation are already confirmed by the human).
3. ScoringNode, FairnessNode, RecommendationNode, GuardrailNode, and AuditNode re-run under the same `application_id`, producing a new `revision_number` on all downstream tables.
4. The UI always shows the latest `revision_number` as the current result. The Audit Explorer shows the full revision history.

This keeps the append-only audit guarantee intact through a correction: the original model-extracted value is always queryable alongside the corrected one.

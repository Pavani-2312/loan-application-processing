# 04 · Data Model & Policy Reference
## Project 05 — Loan / Credit Application Processing Agent

> Scope note: This document is the single source of truth for table/collection schemas and the placeholder credit policy values referenced throughout `03_Functional_Specification.md`. Logic that uses these shapes is described there, not repeated here.

---

## 1. Sample Credit Policy (placeholder — replace with the lender's published policy before real use)

Each clause has a stable `clause_id` so it can be cited precisely. This is the source text embedded into Chroma (`04.2`).

**Section 3 — Debt-to-Income**
- **Clause 3.1(a):** DTI ≤ 0.30 is classified low risk and scores in the top band.
- **Clause 3.1(b):** DTI between 0.30 and 0.40 is classified moderate risk.
- **Clause 3.1(c):** DTI between 0.40 and 0.50 is classified elevated risk and typically requires referral.
- **Clause 3.1(d):** DTI above 0.50 is classified high risk and typically does not meet policy for approval.

**Section 4 — Credit History**
- **Clause 4.1(a):** A simulated bureau score of 720+ with no delinquencies in the last 24 months scores in the top band.
- **Clause 4.1(b):** A score of 650–719, or one minor delinquency in 24 months, is moderate risk.
- **Clause 4.1(c):** A score of 580–649, or a history of repeated minor delinquencies, is elevated risk.
- **Clause 4.1(d):** A score below 580, or any major delinquency (default, charge-off) in 24 months, is high risk.

**Section 5 — Income Stability** *(split into two independently-scored sub-factors per review — see `03_Functional_Specification.md §2.2` for the combination rule)*

*Section 5.1 — Employment Tenure*
- **Clause 5.1(a):** 24+ months with current employer scores in the top band.
- **Clause 5.1(b):** 12–24 months tenure is moderate.
- **Clause 5.1(c):** 6–12 months tenure is elevated.
- **Clause 5.1(d):** Under 6 months tenure is high risk.

*Section 5.2 — Income Variability*
- **Clause 5.2(a):** Income variability under 10% across the reviewed statement period scores in the top band.
- **Clause 5.2(b):** Variability 10–25% is moderate.
- **Clause 5.2(c):** Variability 25–40% is elevated.
- **Clause 5.2(d):** Variability above 40%, or an unverifiable income pattern, is high risk.

*Clause 5.3:* The income-stability factor score is the lower (weaker) of the tenure sub-score and the variability sub-score — strong tenure does not offset volatile income, and vice versa.

**Section 6 — Document Requirements**
- **Clause 6.1:** A complete application requires valid government ID, income proof, and a bank statement no older than 60 days at submission.
- **Clause 6.2:** Stated income must be corroborated within ±15% by recurring deposits in the bank statement; unreconciled variance beyond this requires halting the application pending clarification.

**Section 7 — Recommendation Bands**
- **Clause 7.1:** A composite policy score of 0.75 or above supports an APPROVE recommendation.
- **Clause 7.2:** A composite policy score between 0.65 and 0.75 supports a REFER recommendation for human underwriting review.
- **Clause 7.3:** A composite policy score below 0.65 supports a DECLINE recommendation, subject to human confirmation.

**Section 8 — Fairness & Non-Discrimination**
- **Clause 8.1:** Recommendations must not vary based on applicant name, address, or any proxy for a protected characteristic. Any identity-blind re-score that changes the recommendation band must be treated as a policy exception requiring escalation, not an averaging exercise.

**Section 9 — Human Authority**
- **Clause 9.1:** No automated system may issue a final approval or adverse action. A licensed underwriter's recorded decision is required in all cases.

## 2. Chroma Collection Design

**Collection:** `credit_policy_clauses`

| Field | Type | Description |
|---|---|---|
| `id` | string | Clause ID, e.g. `"3.1(b)"` |
| `document` (embedded text) | string | Full clause text (the sentence(s) above) |
| `metadata.section` | string | e.g. `"Debt-to-Income"` |
| `metadata.factor` | string | One of `dti`, `credit_history`, `income_stability`, `documents`, `bands`, `fairness`, `authority` |
| `metadata.band_label` | string \| null | e.g. `"low_risk"`, `"moderate"`, `"elevated"`, `"high_risk"` — lets ScoringNode filter by factor + band before falling back to pure semantic search |

Loaded once at setup time from the policy text above (or the lender's real policy once substituted); read-only at runtime.

**Two distinct access patterns, per the review-driven fix in `03_Functional_Specification.md §2.4`:**
1. **Exact-ID lookup** (`collection.get(ids=[clause_id])`) — used by ScoringNode to fetch the full text of the clause already named deterministically in `policy_config.yaml`. No embedding/similarity math involved. This is the only path that feeds a decision's citation.
2. **Semantic search** (`collection.query(query_texts=[...])`) — used only by the UI's underwriter-facing policy search (a manual lookup convenience), never on a path that produces evidence attached to a recommendation.

## 3. SQLite Schema (system of record)

**`applications`**
| Column | Type | Notes |
|---|---|---|
| `application_id` | TEXT PK | UUID |
| `submitted_at` | TIMESTAMP | |
| `status` | TEXT | `AWAITING_DOCUMENTS` / `INCONSISTENT_DOCUMENTS` / `NEEDS_MANUAL_VERIFICATION` / `PROCESSING_ERROR` / `POLICY_CONFIG_ERROR` / `PENDING_HUMAN_REVIEW` / `REFERRED_FOR_ESCALATION` / `DECIDED` — see `03_Functional_Specification.md §3.2` for REFER's non-terminal routing and §8 for the error statuses |
| `status_version` | INTEGER | Optimistic-locking counter; incremented on every status write, required to match on write to prevent race conditions (see `02_Architecture.md §6`) |
| `intake_idempotency_key` | TEXT | Client-generated token; a duplicate key on intake is a no-op, not a new record |
| `applicant_name` | TEXT | Raw, identity-bearing |
| `applicant_address` | TEXT | Raw, identity-bearing |
| `raw_payload_ref` | TEXT | Pointer to stored document files |

**`extracted_fields`** *(revised — append-only/versioned, not update-in-place, per review: overwriting lost the original model-extracted value)*
| Column | Type | Notes |
|---|---|---|
| `application_id` | TEXT FK | |
| `field_name` | TEXT | e.g. `monthly_income`, `stated_debt`, `bureau_score`, `employment_tenure_months`, `deposit_variability_pct` |
| `field_version` | INTEGER | 1 = original model extraction; 2+ = a human correction/confirmation. Multiple versions of the same field coexist; nothing is overwritten. |
| `field_value` | TEXT | Stored as text, cast on read per field type |
| `source_document` | TEXT | Which uploaded doc it came from (version 1 only; corrections reference the same source) |
| `confidence` | TEXT | `high` / `medium` / `low`, as reported by the extraction model (version 1); NULL for human-entered versions |
| `evidence_span` | TEXT | Literal source text the value was read from (version 1); for a correction, the underwriter's stated reason instead |
| `manually_verified` | BOOLEAN | True on any version 2+ row |
| `is_effective` | BOOLEAN | True on exactly one version per `(application_id, field_name)` — the value scoring actually used. Set false on all prior versions when a new one is written. |

Scoring always reads the `is_effective = true` row per field. An auditor can still query all versions for any field to see whether the system "almost scored with a different number" — this directly closes the gap flagged in review.

**`validation_results`**
| Column | Type | Notes |
|---|---|---|
| `application_id` | TEXT FK | |
| `check_name` | TEXT | e.g. `name_match`, `id_validity`, `income_plausibility`, `statement_recency` |
| `passed` | BOOLEAN | |
| `evidence` | TEXT | LLM-generated rationale for the check |

**`score_breakdowns`**
| Column | Type | Notes |
|---|---|---|
| `application_id` | TEXT FK | |
| `revision_number` | INTEGER | 1 = first scoring run; increments each time `NEEDS_MANUAL_VERIFICATION` correction triggers a re-run (see `03_Functional_Specification.md §1.2b`). Nothing is overwritten — the "current" view reads the max `revision_number`, the Audit Explorer shows all of them. |
| `factor` | TEXT | `dti` / `credit_history` / `income_stability` |
| `sub_factor` | TEXT \| NULL | For `income_stability` only: `tenure` or `variability` — the row for `factor=income_stability` itself stores the *combined* (min of the two) score; two additional rows with `sub_factor` set store each sub-score for transparency. NULL for `dti`/`credit_history`. |
| `raw_value` | REAL | e.g. actual DTI ratio, tenure in months, or variability % |
| `normalized_score` | REAL | 0.0–1.0 |
| `weight` | REAL | Weight applies at the `factor` level only; sub-factor rows carry the factor's weight for display but are not separately weighted into the composite. |
| `weighted_contribution` | REAL | |
| `band_label` | TEXT | |
| `cited_clause_id` | TEXT | Looked up deterministically from `policy_config.yaml`, not via similarity search (see `03_Functional_Specification.md §2.4`) |
| `is_fairness_run` | BOOLEAN | Distinguishes the original run from the identity-blind run |

**`recommendations`**
| Column | Type | Notes |
|---|---|---|
| `application_id` | TEXT FK | |
| `revision_number` | INTEGER | See `score_breakdowns.revision_number` — same versioning applies here |
| `composite_score` | REAL | |
| `band` | TEXT | `APPROVE` / `REFER` / `DECLINE` |
| `explanation_text` | TEXT | LLM-composed, factor-and-clause grounded |
| `generated_at` | TIMESTAMP | |

**`fairness_checks`**
| Column | Type | Notes |
|---|---|---|
| `application_id` | TEXT FK | |
| `revision_number` | INTEGER | See `score_breakdowns.revision_number` |
| `original_band` | TEXT | |
| `blind_band` | TEXT | |
| `result` | TEXT | `PASS` / `FAIL` |
| `disparity_detail` | TEXT | Populated only on FAIL |

**`guardrail_flags`**
| Column | Type | Notes |
|---|---|---|
| `application_id` | TEXT FK | |
| `field` | TEXT | Which free-text field triggered it |
| `excerpt` | TEXT | The flagged text |
| `reason` | TEXT | Why it was flagged |

**`human_decisions`** (the only table the UI writes outcomes to; **supports multiple rows per application** — revised per review to model REFER as a non-terminal, repeatable event rather than a single final row)
| Column | Type | Notes |
|---|---|---|
| `decision_id` | TEXT PK | |
| `application_id` | TEXT FK | An application may have several decision rows over time (e.g., REFER → REFER → DECLINE) |
| `sequence_number` | INTEGER | Order of this decision event for the application, starting at 1 |
| `underwriter_id` | TEXT | Caveat: not cryptographically verified in this build — see `01_Requirements.md §10` (L1) |
| `decision` | TEXT | `APPROVE` / `REFER` / `DECLINE` |
| `refer_reason` | TEXT \| NULL | Required and non-null when `decision = REFER`: `REQUEST_MORE_INFO` / `ESCALATE_TO_SENIOR_UNDERWRITER` / `ESCALATE_TO_COMMITTEE`. NULL otherwise. |
| `is_terminal` | BOOLEAN | True only when `decision ∈ {APPROVE, DECLINE}` — this is what allows `applications.status` to become `DECIDED` |
| `recommendation_at_time` | TEXT | Snapshot of the agent's recommendation band when this decision was made, so `matches_recommendation` is meaningful even across multiple decision events |
| `matches_recommendation` | BOOLEAN | Derived by comparing `decision` to `recommendation_at_time` for *this* event — powers the straight-through approval rate KPI |
| `rationale` | TEXT | Free text from underwriter; required, and specifically flagged in the UI when it diverges from the recommendation |
| `decided_at` | TIMESTAMP | |

**`audit_log`** (append-only, one row per state-changing event across all tables above)
| Column | Type | Notes |
|---|---|---|
| `log_id` | TEXT PK | |
| `application_id` | TEXT FK | |
| `event_type` | TEXT | `INTAKE`, `VALIDATION_FAILED`, `SCORED`, `FAIRNESS_CHECKED`, `RECOMMENDED`, `GUARDRAIL_FLAGGED`, `RESCORED_AFTER_VERIFICATION`, `HUMAN_DECIDED` |
| `event_payload` | TEXT (JSON) | Schema below — a defined shape per `event_type`, not a free-form dump. This was left unspecified in the prior revision (flagged in review); an auditor needs to know exactly what's in it without reading source code. |
| `occurred_at` | TIMESTAMP | |

**`event_payload` schema by `event_type`** (closes the review gap — NFR-04 requires a record presentable to a third party with no additional context):

| `event_type` | Required payload fields |
|---|---|
| `INTAKE` | `document_types_received`, `intake_idempotency_key` |
| `VALIDATION_FAILED` | `failed_checks: [{check_name, evidence}]` |
| `SCORED` | `revision_number`, `composite_score`, `band`, `factor_breakdown: [{factor, raw_value, band_label, clause_id}]` |
| `FAIRNESS_CHECKED` | `revision_number`, `original_band`, `blind_band`, `result` |
| `RECOMMENDED` | `revision_number`, `band`, `explanation_excerpt` |
| `GUARDRAIL_FLAGGED` | `field`, `excerpt`, `reason` |
| `RESCORED_AFTER_VERIFICATION` | `corrected_field_name`, `previous_value`, `new_value`, `triggering_underwriter_id` |
| `HUMAN_DECIDED` | `decision_id`, `decision`, `refer_reason` (if applicable), `is_terminal` |

**Single-application audit export (new — closes the review gap that no self-contained per-application artifact was defined):** the Audit Explorer's per-application detail view (`05_UI_Design.md §5`) includes a **"Generate Audit Package"** action that renders all of the above — application data, every extraction field version, every score/recommendation/fairness revision, guardrail flags, and the full human decision history — into a single self-contained, human-readable document (PDF or standalone HTML), suitable for handing to a regulator without requiring access to the running system or a database dump.

## 4. Policy Config File (drives thresholds without code changes)

A single `policy_config.yaml` (or JSON) holds the weights, band boundaries, and tolerance values referenced in `03_Functional_Specification.md` (§2.1–2.3, §3.1, §1.3), e.g.:

```yaml
weights:
  dti: 0.40
  credit_history: 0.35
  income_stability: 0.25   # combined score = min(tenure_subscore, variability_subscore) — see 03_Functional_Specification.md §2.2

bands:
  # direction: max_asc  -> lower raw value is better; bands checked ascending by `max`
  # direction: min_desc -> higher raw value is better; bands checked descending by `min`
  dti:
    direction: max_asc
    entries:
      - {max: 0.30, score: 1.0, clause: "3.1(a)"}
      - {max: 0.40, score: 0.7, clause: "3.1(b)"}
      - {max: 0.50, score: 0.4, clause: "3.1(c)"}
      - {max: null, score: 0.0, clause: "3.1(d)"}

  credit_history:
    direction: min_desc
    entries:
      - {min: 720, score: 1.0, clause: "4.1(a)"}
      - {min: 650, score: 0.7, clause: "4.1(b)"}
      - {min: 580, score: 0.4, clause: "4.1(c)"}
      - {min: null, score: 0.0, clause: "4.1(d)"}

  # Income stability is two independently-scored sub-factors, combined via min() — not a single band list.
  income_stability_tenure_months:
    direction: min_desc
    entries:
      - {min: 24, score: 1.0, clause: "5.1(a)"}
      - {min: 12, score: 0.7, clause: "5.1(b)"}
      - {min: 6,  score: 0.4, clause: "5.1(c)"}
      - {min: null, score: 0.0, clause: "5.1(d)"}

  income_stability_variability_pct:
    direction: max_asc
    entries:
      - {max: 10, score: 1.0, clause: "5.2(a)"}
      - {max: 25, score: 0.7, clause: "5.2(b)"}
      - {max: 40, score: 0.4, clause: "5.2(c)"}
      - {max: null, score: 0.0, clause: "5.2(d)"}

recommendation_bands:
  approve_min: 0.75
  refer_min: 0.65

document_rules:
  income_tolerance_pct: 15
  statement_max_age_days: 60

extraction_rules:
  # closes the "schema-valid but hallucinated" gap — low-confidence scoring-relevant
  # fields block auto-scoring until a human confirms them (03_Functional_Specification.md §1.2a)
  scoring_relevant_fields: [monthly_income, stated_debt, bureau_score, employment_tenure_months, deposit_amounts]
  low_confidence_action: NEEDS_MANUAL_VERIFICATION
```

This file is the single editable source for anything a real Credit Ops team would need to tune without a code deploy. Note the `income_stability` band lists are keyed by sub-factor (`_tenure_months` / `_variability_pct`) rather than a single combined list — this mirrors the two-sub-score, min-combination rule in `03_Functional_Specification.md §2.2` and is what makes the combination deterministic across implementations.

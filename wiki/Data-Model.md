# Data Model

All application data lives in SQLite (`data/loan_applications.db`), accessed exclusively through the repository layer (`src/repository/`).

## Tables

### `applications`
One row per application.

| Column | Type | Notes |
|--------|------|-------|
| `application_id` | TEXT PK | UUID |
| `submitted_at` | TIMESTAMP | |
| `status` | TEXT | See status list below |
| `status_version` | INTEGER | Optimistic-locking counter — must match on every status write |
| `intake_idempotency_key` | TEXT | Duplicate submissions with the same key are silently de-duped |
| `applicant_name` | TEXT | |
| `applicant_address` | TEXT | |

### `extracted_fields` — append-only versioned
Never overwritten. Corrections add a new row; `is_effective` flags the current value per field.

| Column | Type | Notes |
|--------|------|-------|
| `field_name` | TEXT | e.g. `stated_monthly_income`, `bureau_score` |
| `field_version` | INTEGER | 1 = model extraction; 2+ = human correction |
| `field_value` | TEXT | Stored as text, cast on read |
| `confidence` | TEXT | `high` / `medium` / `low` (NULL for human-entered versions) |
| `evidence_span` | TEXT | Literal source text (version 1); underwriter reason (version 2+) |
| `manually_verified` | BOOLEAN | True on version 2+ rows |
| `is_effective` | BOOLEAN | Exactly one `True` per `(application_id, field_name)` at any time |

### `validation_results`
One row per check per application.

| Column | Notes |
|--------|-------|
| `check_name` | `name_match`, `id_validity`, `income_plausibility`, `statement_recency` |
| `passed` | Boolean |
| `evidence` | LLM-generated rationale |

### `score_breakdowns` — versioned
Versioned by `revision_number` (increments on re-score after field correction).

| Column | Notes |
|--------|-------|
| `revision_number` | 1 = first run; increments on re-score |
| `factor` | `dti`, `credit_history`, `income_stability` |
| `sub_factor` | `tenure` or `variability` for income_stability sub-rows; NULL otherwise |
| `raw_value` | Actual DTI ratio, bureau score, months, or variability % |
| `normalized_score` | 0.0 – 1.0 |
| `weight` | Factor-level weight |
| `weighted_contribution` | |
| `band_label` | `low_risk`, `moderate`, `elevated`, `high_risk` |
| `cited_clause_id` | Deterministic lookup from `policy_config.yaml` |
| `is_fairness_run` | Distinguishes standard run from identity-blind run |

### `recommendations` — versioned
| Column | Notes |
|--------|-------|
| `revision_number` | Matches `score_breakdowns.revision_number` |
| `composite_score` | Float |
| `band` | `APPROVE`, `REFER`, or `DECLINE` |
| `explanation_text` | LLM-composed, clause-grounded explanation |

### `fairness_checks` — versioned
| Column | Notes |
|--------|-------|
| `original_band` | Band from standard scoring |
| `blind_band` | Band from identity-blind scoring |
| `result` | `PASS` or `FAIL` |
| `disparity_detail` | Populated on FAIL |

### `guardrail_flags`
| Column | Notes |
|--------|-------|
| `field` | Which free-text field triggered it |
| `excerpt` | The flagged text |
| `reason` | Why it was flagged |

### `human_decisions` — multiple rows per application
REFER is non-terminal. An application can have multiple decision rows before it resolves.

| Column | Notes |
|--------|-------|
| `sequence_number` | Order of this decision event, starting at 1 |
| `underwriter_id` | Self-reported — not cryptographically verified (see [[Known-Limitations]] L1) |
| `decision` | `APPROVE`, `REFER`, or `DECLINE` |
| `refer_reason` | Required when `decision = REFER`: `REQUEST_MORE_INFO`, `ESCALATE_TO_SENIOR_UNDERWRITER`, `ESCALATE_TO_COMMITTEE` |
| `is_terminal` | True only for APPROVE or DECLINE |
| `recommendation_at_time` | Snapshot of agent's band at decision time |
| `matches_recommendation` | Whether this decision matched the agent's recommendation |
| `rationale` | Required free text |

### `audit_log` — append-only
One row per state-changing event. Never updated or deleted.

| `event_type` | Key payload fields |
|---|---|
| `INTAKE` | `document_types_received`, `intake_idempotency_key` |
| `VALIDATION_FAILED` | `failed_checks: [{check_name, evidence}]` |
| `SCORED` | `revision_number`, `composite_score`, `band`, `factor_breakdown` |
| `FAIRNESS_CHECKED` | `revision_number`, `original_band`, `blind_band`, `result` |
| `RECOMMENDED` | `revision_number`, `band`, `explanation_excerpt` |
| `GUARDRAIL_FLAGGED` | `field`, `excerpt`, `reason` |
| `RESCORED_AFTER_VERIFICATION` | `corrected_field_name`, `previous_value`, `new_value`, `triggering_underwriter_id` |
| `HUMAN_DECIDED` | `decision_id`, `decision`, `refer_reason`, `is_terminal` |

## Application statuses

| Status | Meaning |
|--------|---------|
| `AWAITING_DOCUMENTS` | One or more required documents missing |
| `NEEDS_MANUAL_VERIFICATION` | Low-confidence extraction on a scoring field |
| `INCONSISTENT_DOCUMENTS` | Cross-document validation check failed |
| `PROCESSING_ERROR` | LLM API failure after retry |
| `POLICY_CONFIG_ERROR` | `clause_id` in config has no matching Chroma document |
| `PENDING_HUMAN_REVIEW` | Agent complete; awaiting underwriter |
| `REFERRED_FOR_ESCALATION` | Human issued a non-terminal REFER |
| `DECIDED` | Terminal — human issued APPROVE or DECLINE |

## ChromaDB

Collection `credit_policy_clauses` stores the 24 policy clauses. Used in two ways:

1. **Exact-ID lookup** (`collection.get(ids=[clause_id])`) — used by ScoringNode to fetch clause text. No embedding math. This is the only path that feeds a decision's citation.
2. **Semantic search** — available to underwriters via the UI's policy search only. Never on the scoring path.

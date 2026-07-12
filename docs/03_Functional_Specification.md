# 03 · Functional Specification
## Project 05 — Loan / Credit Application Processing Agent

> Scope note: This document defines the *exact logic* inside each agent node named in `02_Architecture.md`. It does not repeat the component diagram or tech stack rationale. Table schemas referenced here are defined once in `04_Data_Policy_Model.md`.

---

## 1. Document Validation (IntakeNode + ValidationNode)

### 1.1 Required documents
A complete application requires exactly these three document types:
1. **Government ID** — name, date of birth, ID number, expiry date.
2. **Income proof** (payslip / employer letter) — employer name, stated monthly income, pay date/period.
3. **Bank statement** (most recent, min. 1 statement period) — account holder name, period covered, list of deposits, closing balance.

### 1.2 Presence check
- If any of the three document types is absent from the intake payload → status = `AWAITING_DOCUMENTS`, pipeline halts immediately after IntakeNode. No downstream node executes. This directly satisfies **FR-04**: no scoring occurs on partial data.
- Missing-document flag stored per document type (e.g., `missing: ["bank_statement"]`) so the UI can prompt specifically.

### 1.2a Extraction confidence & evidence (closes: hallucination-passes-schema risk)
A Pydantic-valid extracted value can still be wrong — the model can misread "3 months" as `36` and the schema has no way to catch that, since `36` is a perfectly valid integer. To make this failure mode visible instead of silent:
- Every numeric or date field extracted by IntakeNode must be returned by Claude alongside a **confidence** (`high` / `medium` / `low`) and an **evidence span** — the literal source text the value was read from (e.g., `"Employment start date: March 2026"`).
- If any field required for scoring (income, debt, bureau score, employment tenure basis, deposit amounts) comes back `low` confidence, the pipeline does **not** proceed to ValidationNode's downstream scoring path automatically. Status is set to `NEEDS_MANUAL_VERIFICATION`, the field + evidence span + Claude's extracted value are shown to the underwriter, who confirms or corrects the value before the pipeline is allowed to continue.
- This confirmed/corrected value, once set, is what flows into scoring — never the original low-confidence guess.
- The evidence span for every field (regardless of confidence) is also stored and always surfaced in the UI's "Extracted Fields" panel (see `05_UI_Design.md §4`), so spot-checking is a normal part of every review, not just low-confidence ones.

### 1.2b Re-entry after manual verification (new — the original spec said a correction "unblocks scoring" without defining the mechanism; this closes that gap)
When an underwriter confirms or corrects a low-confidence field via the Extracted Fields panel:
1. The correction is written as a **new row** in `extracted_fields` (see `04_Data_Policy_Model.md §3` — the table is versioned, not update-in-place), so the original model-extracted value is never lost; it remains queryable for audit ("did the system almost score with a different number?").
2. This triggers the LangGraph agent to **resume from ScoringNode**, not restart from IntakeNode — extraction and document consistency are already confirmed by the human at this point, so they are not re-run. ScoringNode, FairnessNode, RecommendationNode, GuardrailNode, and AuditNode execute again using the corrected field set.
3. This re-run does **not** create a new `application_id` — it is the same application, continuing forward. It **does** produce new rows in `score_breakdowns`, `recommendations`, and `fairness_checks`, each tagged with an incrementing `revision_number` (see `04_Data_Policy_Model.md §3`), and a new `audit_log` event (`RESCORED_AFTER_VERIFICATION`). Prior rows are never deleted or overwritten — this keeps the append-only audit guarantee intact through a correction, not just through the initial run.
4. The UI and any KPI queries always read the **latest** `revision_number` for "current" display, while the Audit Explorer's detail view shows the full revision history, so an auditor can see both what was originally computed and what corrected it.

### 1.3 Consistency checks (ValidationNode)
Performed only if presence check passes:

| Check | Logic | Failure outcome |
|---|---|---|
| Name match | Applicant name on ID, income proof, and bank statement must refer to the same person (LLM-assisted fuzzy match tolerant of formatting, not tolerant of different people). | `INCONSISTENT` flag; halt before scoring |
| ID validity | ID expiry date must be in the future relative to application submission date. | `INCONSISTENT` flag; halt |
| Income plausibility | Stated income on income proof must be corroborated by recurring deposits of a similar magnitude in the bank statement (within a tolerance band defined in the policy config, e.g. ±15%). | `INCONSISTENT` flag; halt (this is a policy-config value, not hardcoded — see `04_Data_Policy_Model.md`) |
| Statement recency | Bank statement period end date must be within the policy's max staleness window (e.g. 60 days) of submission. | `INCONSISTENT` flag; halt |

- Any single failed check is sufficient to halt the pipeline with status `INCONSISTENT_DOCUMENTS` and a list of the specific failed checks (for the underwriter and for FR-04/FR-13 traceability).
- Consistency checks are LLM-assisted (Claude reads extracted fields and reasons about the match/plausibility) but the **decision of halt-vs-continue is a boolean gate in Python**, not left to free-form LLM judgment — the LLM outputs a structured `{check: str, passed: bool, evidence: str}` per check, and Python ANDs them.

## 2. Policy Scoring (ScoringNode)

Scoring is 100% deterministic Python. Inputs are the validated, structured fields from IntakeNode — never raw text, never free-text notes.

### 2.1 Factors and weights (illustrative — see `04_Data_Policy_Model.md` for the placeholder policy values; a real deployment substitutes the lender's actual published thresholds)

| Factor | Weight | Computed from |
|---|---|---|
| Debt-to-Income (DTI) | 40% | Monthly debt obligations ÷ monthly income (both from validated fields) |
| Credit history | 35% | Simulated/provided credit bureau score + delinquency flags |
| Income stability | 25% | Employment tenure + income variability across bank statement deposits |

**Band evaluation direction and boundary rule (revised — the original "inclusive on the lower bound" wording conflicted with the max-based band shape and is removed; here is the precise, non-contradictory rule):**
Each band list in `policy_config.yaml` carries an explicit `direction` field, and boundaries are resolved purely by that direction's first-match rule — there is no separate "inclusive lower bound" principle layered on top, since that phrasing was the source of the conflict identified in review.
- **`direction: max_asc`** (lower raw value is better, e.g. DTI): entries are checked in the order listed (ascending `max`); the first entry where `value ≤ max` wins. Worked example: DTI = 0.40 exactly → checked against `max: 0.30` (no match, 0.40 > 0.30) → checked against `max: 0.40` (match, 0.40 ≤ 0.40) → **scores 0.7**, the "moderate" band. The value sits exactly on a boundary and resolves to the *better* of the two adjacent bands, because the boundary value belongs to the band whose `max` it equals.
- **`direction: min_desc`** (higher raw value is better, e.g. credit history): entries are checked in the order listed (descending `min`); the first entry where `value ≥ min` wins. Worked example: bureau score = 650 exactly → checked against `min: 720` (no match) → checked against `min: 650` (match, 650 ≥ 650) → **scores 0.7**, the "moderate" band. Same principle: the boundary value belongs to the band whose `min` it equals, which is again the better of the two adjacent bands.
- This means in both directions, a value sitting exactly on a stated boundary always resolves to the better-scoring side of that boundary — a single, consistent, testable rule. Unit tests in `06_CLI_Build_Prompt.md` STEP 3 must include an exact-boundary case for both `max_asc` and `min_desc` band lists to lock this in.
- The recommendation bands (`approve_min: 0.75`, `refer_min: 0.65`) follow the same `min_desc`-style convention already: composite = 0.75 exactly → APPROVE (not REFER); composite = 0.65 exactly → REFER (not DECLINE).

### 2.2 Per-factor scoring

**Income stability — two sub-factors, one combined score (fixes an undefined combination rule flagged in review):**
Income stability is driven by two independent measurements: employment tenure (months) and income variability (%). Each has its own band list and its own clause citations (tenure → Section 5.1 clauses, variability → Section 5.2 clauses — see `04_Data_Policy_Model.md §1`).
1. Compute `tenure_subscore` from the tenure band list (direction `min_desc` — longer tenure is better).
2. Compute `variability_subscore` from the variability band list (direction `max_asc` — lower variability is better).
3. `income_stability_score = min(tenure_subscore, variability_subscore)` — the **weaker of the two governs** (a "weakest-link" rule). This is the conservative, standard credit-risk convention: strong tenure does not offset volatile income and vice versa. It is also fully deterministic, closing the NFR-02 gap identified in review — two implementations following this spec will always produce the same combined score.
4. The clause cited for the income-stability factor is the clause backing whichever sub-score was lower (the binding constraint). If both sub-scores land in the same band value, both clauses are cited.

### 2.3 Composite score
```
composite_score = (dti_score * dti_weight)
                 + (credit_history_score * credit_weight)
                 + (income_stability_score * income_weight)
```
Result is a float in [0.0, 1.0].

### 2.4 Clause citation (revised — deterministic, not semantic search)
**Original design used a Chroma similarity search per factor+band; this was identified in review as unreliable for a legal/regulatory citation ("similarity ≠ correctness," and a wrong citation is worse than none because it creates a false paper trail). Revised design below.**

Every band entry in `policy_config.yaml` already names its exact backing `clause_id` (the policy owner assigns this when authoring the config — see `04_Data_Policy_Model.md §4`). So citation is a **direct, deterministic step**, not a retrieval problem:
1. The scoring engine determines which band each factor fell into (a pure function of the numeric value and the config, per §2.2).
2. That band entry's `clause_id` is read directly from the already-loaded config — no search involved.
3. The engine fetches the full clause **text** for that exact `clause_id` from Chroma via an **exact-ID `get()`**, not a similarity query. Chroma here is functioning as a simple text store keyed by ID; its embedding/similarity capability is not invoked in this path at all.
4. If the `clause_id` named in the config has no matching document in the Chroma store (a config/corpus drift bug), this is treated as a **configuration error**, not a scoring outcome — the application is halted with status `POLICY_CONFIG_ERROR` and flagged for Credit Ops to fix the corpus/config mismatch, rather than silently showing "no clause found" on a live application.

This guarantees FR-08 (citing policy clauses) is satisfied with a citation that is correct by construction, not by search quality. Chroma's semantic search is retained elsewhere in the product — as a free-text policy lookup tool for underwriters during manual review (`05_UI_Design.md §4`) — but never on the path that produces a decision's evidence.

### 2.5 Score breakdown (transparency, FR-06)
The output of ScoringNode is a structured object containing, per factor: raw value, normalized 0–1 score, weight, weighted contribution, band the applicant fell into, and the cited clause. Plus the composite score. This entire object — not just the final band — is what gets shown to the underwriter and stored in the audit record.

## 3. Recommendation (RecommendationNode)

### 3.1 Banding (deterministic, config-driven thresholds)
| Composite score | Band |
|---|---|
| ≥ 0.75 | **APPROVE** |
| 0.65 – 0.75 | **REFER** |
| < 0.65 | **DECLINE** |

- Band boundaries are inclusive on the lower bound of each tier as written above; exact placeholder values live in `04_Data_Policy_Model.md` and are configurable.
- The LLM's role here is limited to composing the natural-language explanation from the already-computed breakdown ("DTI of 0.28 falls in the lowest-risk band per Clause 3.1(a)...") — it does not choose the band.

### 3.2 REFER handling (FR-07, borderline scenario) — revised: REFER is non-terminal end-to-end

**Original design left REFER underspecified as a human decision option with no defined outcome or routing; this is fixed below (flagged in review as a real workflow gap).**

**Agent-level REFER** (the recommendation itself): identical to before — all three bands (APPROVE/REFER/DECLINE) land the application at `PENDING_HUMAN_REVIEW`; REFER differs only in the explanation text, which states the composite score fell in the referral band and names the borderline factor(s).

**Human-level REFER** (what the underwriter can decide) is now explicitly **not a final outcome**, structurally distinct from APPROVE/DECLINE:
- If the underwriter's recorded decision is REFER, a required `refer_reason` (categorical, not free text) must accompany it: `REQUEST_MORE_INFO`, `ESCALATE_TO_SENIOR_UNDERWRITER`, or `ESCALATE_TO_COMMITTEE`.
- The application's status is set to `REFERRED_FOR_ESCALATION` — **not** `DECIDED`. It re-enters the Review Queue tagged with its `refer_reason` and its full prior history intact.
- `human_decisions` supports **multiple rows per application** (a decision history), because an application can be referred more than once before it resolves (e.g., more info requested → resubmitted → escalated to committee → finally decided). Only a row where `decision ∈ {APPROVE, DECLINE}` sets `applications.status = DECIDED` and is treated as terminal.
- `matches_recommendation` is computed per decision event, not once per application — it compares that specific human decision to the recommendation that was live at the time of that event.
- This means an application's audit trail can show a legitimate chain: `Agent: REFER → Human: REFER (ESCALATE_TO_COMMITTEE) → Human: DECLINE (final)` — every step preserved, nothing overwritten, consistent with the append-only audit model in §6.

### 3.3 Adverse-action reasons (stretch goal)
If implemented: when the band is DECLINE, generate up to 4 principal reasons in regulator-friendly language (mirroring the FCRA "specific reasons" requirement), each reason traced 1:1 to the lowest-scoring factor(s) and its cited clause. This generator only runs after a human confirms the DECLINE — it never runs on the agent's raw recommendation alone, preserving the human-gate control.

## 4. Identity-Blind Extraction Consistency Check (FairnessNode) — scope clarified

**Naming note (per review):** this is referred to informally as "the fairness check" elsewhere in this doc set and satisfies the business requirement's literal wording ("re-score with identity removed; recommendation must not change"). But it is important to be precise about what it does and does not test, because a pass here should not be read as "this system is fair":

- **What it tests:** whether the LLM-driven extraction/consistency-reasoning layer let `name` or `address` implicitly influence a numeric factor (e.g., an inferred "this employer/neighborhood sounds unstable" judgment leaking into `income_stability`). Since the deterministic scorer itself only reads numeric fields, a pass here mostly confirms the LLM layer stayed clean.
- **What it does NOT test:** proxy discrimination (address correlating with a protected characteristic through channels the model never explicitly reasons about), disparate impact across an applicant population, or whether the *policy thresholds themselves* produce systematically different outcomes across groups. Those require statistical analysis over a population of real decisions, not a single-application re-run, and are out of scope for this system — see `01_Requirements.md §10` (L2) for the explicit limitation and what a real compliance program would need to add.

### 4.1 Method
1. Take the validated structured `ApplicationRecord` produced after IntakeNode/ValidationNode.
2. Produce a copy with `name` and `address` fields removed/redacted (replaced with neutral placeholders, e.g. `"Applicant"`, `"[redacted]"`) before it is passed to any LLM call downstream (i.e., the consistency-check reasoning and the recommendation-explanation composition are re-run blind).
3. Re-run ScoringNode on this identity-blind record. Because DTI/credit-history/income-stability are numeric fields untouched by the redaction, the *deterministic* score should be identical by construction — the fairness check is really validating that **no upstream LLM step (extraction, consistency reasoning) implicitly let identity leak into a factor value**, e.g. via an inferred "employer name sounds unstable" judgment call.
4. Compare `original_band` vs `blind_band`.

### 4.2 Outcome
| Comparison | Outcome |
|---|---|
| Bands match | `fairness_check: PASS`, both scores stored in the audit record |
| Bands differ | `fairness_check: FAIL` — this is a hard stop: status forced to `PENDING_HUMAN_REVIEW` with a **fairness disparity flag** surfaced prominently in the UI; the disparity itself, both breakdowns, and the differing factor(s) are all persisted. The system never auto-resolves a disparity by picking one score. |

This satisfies **FR-09/FR-10**: identical recommendation is required; any change is a fail, surfaced to the human, never silently averaged or overridden.

## 5. Guardrail / Adversarial Input Handling (GuardrailNode)

### 5.1 Structural guarantee
Free-text fields (e.g., an "application notes" field) are never concatenated into the prompt used for scoring-adjacent reasoning as instructions. They are only ever passed to the LLM inside an explicitly delimited block labeled as untrusted application content, in a call whose sole job is document-consistency reasoning or explanation phrasing — a call that has no ability to alter `composite_score` or `band`, because those are already computed in Python by the time any such text is read.

### 5.2 Detection & logging
- GuardrailNode runs a dedicated classification pass over all free-text fields asking Claude to flag any content that reads as an attempt to instruct the system (e.g., "approve regardless," "manager said so," "skip the check").
- Detected attempts are logged to the audit record as `guardrail_flags: [{field, excerpt, reason}]` — the content is **not removed from the file** (it's part of the application), but it is explicitly marked so the underwriter sees "this application contains an attempted instruction override" alongside the recommendation.
- Detection never blocks the pipeline (a REFER/APPROVE/DECLINE is still produced normally from the policy score) — it only adds a visible flag, because the correct handling of a pressure attempt is transparency to the human, not silent removal.

## 6. Audit Record Contents (AuditNode) — governance, FR-13/FR-14

One audit record per application, written once, append-only. Contains:
1. Raw intake references (document IDs/paths, submission timestamp).
2. Extracted structured fields (post-IntakeNode).
3. Validation result (presence + consistency, pass/fail per check).
4. Score breakdown (per-factor values, bands, weights, cited clause IDs, composite score).
5. Recommendation band + generated explanation text.
6. Fairness check result (both bands, pass/fail, disparity detail if failed).
7. Guardrail flags (if any).
8. Status at time of write (`AWAITING_DOCUMENTS` / `INCONSISTENT_DOCUMENTS` / `NEEDS_MANUAL_VERIFICATION` / `POLICY_CONFIG_ERROR` / `PENDING_HUMAN_REVIEW`).
9. Later, linked separately: one or more human decision records (decision, `refer_reason` if applicable, rationale, underwriter identity, timestamp) — each appended as its own row, never merged into or overwriting the original write or a prior decision event. An application's status only becomes `DECIDED` on a decision row where `decision ∈ {APPROVE, DECLINE}`; a REFER decision appends a row and sets `REFERRED_FOR_ESCALATION` instead (see §3.2).

Exact table/column definitions are in `04_Data_Policy_Model.md §3`.

## 7. Repository Layer (abstraction for storage swap)

All nodes access storage through a thin repository interface (`ApplicationRepository`, `PolicyRepository`) rather than raw SQL/Chroma calls, so that:
- `ApplicationRepository` (SQLite/SQLAlchemy today) could be swapped for PostgreSQL later without touching node logic.
- `PolicyRepository` (Chroma today) could be swapped for a hosted vector store later without touching node logic.

This is the mechanism referenced in `02_Architecture.md §6` that lets the build be "production-aligned" without being production-deployed.

## 8. Error / Edge-Case Handling Summary (expanded per review)

| Condition | Handling |
|---|---|
| Claude API call fails/times out during extraction | Node retries once with backoff; on second failure, application marked `PROCESSING_ERROR`, surfaced to underwriter queue for manual intake — never silently defaults to a score. |
| Claude returns a response but it fails Pydantic schema validation | Retried once with the validation error fed back to the model as correction context; on second failure, `PROCESSING_ERROR`, same as an API failure — never partially populate the record with an invalid shape. |
| Claude returns a schema-valid but likely-wrong value (hallucination that passes type checking) | Mitigated structurally, not detected after the fact: see §1.2a — every scoring-relevant field requires a confidence + evidence span, and low confidence blocks auto-scoring until a human confirms the value. |
| A `clause_id` named in `policy_config.yaml` has no matching document in Chroma | Treated as a **configuration/data-corpus drift error**, not a scoring outcome — status `POLICY_CONFIG_ERROR`, flagged to Credit Ops (this replaces the old "no clause found, fabricate a generic message" fallback, since citation is now deterministic per §2.4 — a missing clause means the config and corpus are out of sync, which is an operational bug to fix, not a per-application edge case). |
| Two documents present but a required field is unreadable (e.g., scanned image too poor) | Treated as a presence failure for that document (equivalent to missing), per FR-04. |
| Duplicate submission (double-click, network retry) of the same intake | Rejected by the repository layer via an idempotency key generated client-side at form-submit time; the second call is a no-op returning the existing `application_id` rather than creating a duplicate record. |
| Two status-changing writes race (e.g., two underwriters acting near-simultaneously) | Rejected via optimistic locking on `applications.status` — the losing write receives a conflict response and the UI asks the user to refresh and re-review before retrying. See `02_Architecture.md §6` for the underlying SQLite WAL + single-writer mitigation. |

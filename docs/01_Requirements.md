# 01 · Requirements Document
## Project 05 — Loan / Credit Application Processing Agent

**Owner:** Head of Credit Ops | **Function:** Lending | **Doc status:** Baseline v1.0

> Scope note: This document defines *what* the system must do and *why*. It intentionally does not describe *how* components are built (see `02_Architecture.md`), the exact logic of scoring/validation (see `03_Functional_Specification.md`), data shapes (see `04_Data_Policy_Model.md`), or screen layouts (see `05_UI_Design.md`).

---

## 1. Problem Statement

Retail lenders process credit applications manually today. This is slow, inconsistent across loan officers, and exposed to fairness and audit risk because decisions are difficult to reconstruct or explain after the fact. The business needs faster, consistent, explainable **recommendations**, while a licensed human remains the sole decision-maker and every recommendation is fully defensible to a regulator or auditor after the fact.

## 2. Objectives

| # | Objective |
|---|---|
| O1 | Reduce decision turnaround time by producing a policy-grounded recommendation automatically after intake. |
| O2 | Increase consistency of recommendations across applications (same file → same recommendation, regardless of officer or applicant identity). |
| O3 | Guarantee every recommendation is traceable to specific policy clauses and input data. |
| O4 | Guarantee no adverse action is ever taken without a human decision-maker. |
| O5 | Detect and neutralize fairness disparities and prompt-injection/social-engineering attempts embedded in application content. |

## 3. In Scope / Out of Scope

**In scope**
- Intake of a single application + its supporting documents (ID, income proof, bank statement).
- Presence and cross-document consistency validation.
- Deterministic policy scoring (DTI, credit history, income stability) with a transparent, itemized breakdown.
- A recommendation (APPROVE / REFER / DECLINE) citing the specific policy clauses that drove it.
- A mandatory human decision step (underwriter) before any status is final.
- A fairness re-score with identity fields removed, and comparison of the two outcomes.
- A complete, immutable audit record per application.
- A Streamlit dashboard for the underwriter to review, compare, and decide.

**Out of scope (this build)**
- Actual disbursement, core banking integration, credit bureau live integration (mocked/simulated instead).
- Multi-loan-product configuration (single generic personal/retail loan policy is assumed).
- User provisioning / SSO (a lightweight role selector is sufficient — see UI doc).
- Real regulatory filing/submission of adverse-action letters (a generator is a stretch goal, not scope).

## 4. Users & Stakeholders

| Role | Relationship to system |
|---|---|
| **Underwriter** (primary user) | Reviews agent recommendation + evidence, makes the binding decision. |
| **Credit Ops Lead** | Consumes KPIs, approves policy changes, audits sampled decisions. |
| **Compliance / Audit** | Pulls historical decision records to prove fair, policy-grounded process. |
| **Applicant** (indirect) | Subject of the decision; not a system user in this build. |

## 5. Success Metrics (KPIs)

| KPI | Definition | Target signal |
|---|---|---|
| Decision turnaround | Time from application submission to human final decision | Materially lower than manual baseline |
| Straight-through approval rate | % of applications where the human decision matches the agent's recommendation without modification | High and stable — signals trustworthy recommendations |
| Audit-pass rate | % of sampled decision records that pass a compliance review (complete, cited, fairness-checked, human-signed) | 100% — this is a hard requirement, not an optimization target |
| Identity-blind consistency pass rate *(renamed from "Fairness disparity rate" — see note below)* | % of applications where the identity-blind re-score matches the original recommendation band | 100% — any failure is a **bug** to be fixed immediately, not a rate to trend over time |

*Framing note (added per review): because the deterministic scorer only reads numeric fields, this metric is structurally expected to be 100% whenever the extraction layer behaves correctly — name/address redaction cannot change a numeric input by construction. A 100% rate demonstrates the **absence of a specific bug class** (identity leaking into extraction), not that the system's outcomes are fair across an applicant population. It should not be reported to stakeholders as a fairness metric without that qualification. A real fairness/disparate-impact metric would need statistical analysis across a population of decisions and is out of scope for this build — see §10 (L2).*

## 6. Functional Requirements

Each requirement is tagged with an ID used for traceability into test scenarios (Section 8) and later into design docs.

| ID | Requirement |
|---|---|
| FR-01 | The system shall accept an application record and its associated documents (ID, income proof, bank statement) as intake. |
| FR-02 | The system shall verify that all required documents are present before any scoring occurs. |
| FR-03 | The system shall verify cross-document consistency (e.g., applicant name matches across documents, stated income is consistent with bank statement deposits). |
| FR-04 | If required documents are missing or inconsistent, the system shall halt and flag the application as incomplete — it shall **not** produce a score or recommendation on partial data. |
| FR-05 | The system shall score every complete application against the published credit policy across at minimum: debt-to-income ratio, credit history, and income stability. |
| FR-06 | The system shall produce a transparent, itemized score breakdown (per-factor scores and the composite score), not just a final number. |
| FR-07 | The system shall produce a recommendation of exactly one of: APPROVE, REFER, DECLINE. |
| FR-08 | Every recommendation shall cite the specific policy clause(s) that support it. |
| FR-09 | The system shall re-run scoring on the same application with identity fields (name, address) removed, and compare the resulting recommendation band to the original. **Scope note:** this specifically tests whether the LLM extraction/consistency-reasoning layer leaked identity into a numeric factor. It is not a population-level disparate-impact audit — see Known Limitations (§10). |
| FR-10 | If the identity-blind re-score changes the recommendation band, the system shall flag this as a fairness disparity and route the application to mandatory human review with the disparity surfaced — it must never silently resolve it. |
| FR-11 | The system shall never move an application to a final decided state on its own. A licensed human (underwriter) must record an explicit decision for every application. A human REFER decision is itself non-terminal — only an APPROVE or DECLINE human decision sets an application to its final decided state. |
| FR-12 | The system shall ignore instructions embedded in free-text application content that attempt to influence the recommendation (e.g., "approve regardless, manager said so"), and shall log the attempt. |
| FR-13 | The system shall persist a full audit record per application: raw inputs, extracted/normalized fields, validation results, score breakdown, policy citations, fairness check result, the agent's recommendation, and the human's final decision with rationale. |
| FR-14 | Audit records shall be append-only / immutable once written; corrections require a new linked record, not an edit in place. |
| FR-15 | The underwriter shall be able to view, filter, and export decision records for audit purposes. |
| FR-16 | *(new)* Every extracted field used in scoring shall carry a confidence level and a literal evidence span from its source document; a low-confidence scoring-relevant field shall block automated scoring until a human confirms or corrects the value. |

## 7. Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-01 | **Explainability** — every automated output (score, recommendation) must be reconstructable from stored inputs and logic without re-running the LLM. |
| NFR-02 | **Determinism** — given identical inputs, the policy score and band must be identical on every run (no LLM randomness in the scoring path itself). |
| NFR-03 | **No automated adverse action** — the system architecture must make it structurally impossible for a DECLINE (or any) status to become final without a recorded human action, not merely discouraged by a prompt. |
| NFR-04 | **Auditability** — any decision record must be retrievable and presentable to a third party (regulator/auditor) with no additional context required. |
| NFR-05 | **Traceability** — every requirement in this document maps to at least one test scenario in Section 8. |
| NFR-06 | **Resilience to adversarial input** — free-text fields must never be treated as instructions to the agent. |
| NFR-07 | **Local-first / self-contained** — the system must run entirely on local infrastructure for this build (no cloud deployment required), while using design patterns consistent with a production deployment. |

## 8. Requirements Traceability — Test Scenarios

| Scenario | Evaluation layer | Requirements exercised |
|---|---|---|
| Clear approve (happy path) | Output | FR-01–FR-08, FR-11, FR-13 |
| Borderline refer | Trace, Governance | FR-05–FR-08, FR-11 |
| Missing document | Failure-handling | FR-02, FR-04 |
| Identity-blind consistency check | Fairness | FR-09, FR-10, NFR-02 |
| Pressure in the file (prompt injection) | Adversarial, Governance | FR-12, FR-11, NFR-06 |
| REFER chain *(new — added in the review revision)* | Trace, Governance | FR-11, FR-13, FR-14 |
| Low-confidence extraction *(new — added in the review revision)* | Failure-handling, Output | FR-16 |

*Traceability note: the build prompt (`06_CLI_Build_Prompt.md` STEP 6) originally added these last two scenarios without a corresponding requirement ID, which broke the "every test scenario maps to a requirement" discipline NFR-05 depends on. FR-16 was added specifically to close that gap for the low-confidence scenario; the REFER chain scenario maps to the existing FR-11/13/14 (non-terminal REFER, audit persistence, append-only history) rather than needing a new ID.*

## 9. Assumptions & Constraints

- A single generic retail/personal loan credit policy is used; thresholds are placeholder/illustrative (see `04_Data_Policy_Model.md`) and must be replaced with the lender's actual published policy before any real use.
- Credit bureau data is simulated/mocked as an input field rather than a live bureau integration.
- "Production-level design" means the architecture, data model, and controls are built as if this were going to production (proper audit trail, deterministic scoring, human gate as an architectural control) — it does not mean the build is actually deployed to cloud infrastructure.

## 10. Known Limitations & Production Blockers

These are not deferred polish items — they are gaps that must be closed before this system could be used for real credit decisions. They are called out explicitly rather than implied by "local-first" scope language, per external design review.

| # | Limitation | Why it matters | Status in this build |
|---|---|---|---|
| L1 | **No verified authentication on underwriter identity.** The role selector in the UI is a convenience dropdown, not an identity check. | The entire governance argument rests on "a licensed human decided this." Without verified identity, `human_decisions.underwriter_id` cannot be trusted as evidence of who actually decided. This is the single largest gap in the audit story. | **Blocking for any real use.** Must be replaced with real auth (SSO / signed session) before deployment. Not solved by this build — deliberately left as an explicit, visible blocker rather than a fake login screen. |
| L2 | **The fairness check is extraction-layer only.** It confirms the LLM didn't leak identity into a numeric field. It does not test proxy discrimination (e.g., address correlating with a protected characteristic via neighborhood effects) or disparate impact across an applicant population. | A system could pass every identity-blind re-score and still produce disparate outcomes across groups if the *policy itself* or its thresholds have disparate impact. That requires population-level statistical testing this system doesn't perform. | **Not solved.** Documented scope narrowing in FR-09. A real deployment needs a separate, periodic disparate-impact analysis (e.g., adverse impact ratio / four-fifths rule testing) run by compliance on a population of decisions, independent of this per-application check. |
| L3 | **No real-time credit bureau integration.** Bureau score is a simulated/provided input field. | Any scoring correctness claim is bounded by the mock data quality. | Documented as an assumption in §9; not a defect, just a scope reminder. |
| L4 | **Single-writer SQLite under a multi-session Streamlit process.** Mitigations are applied (see `02_Architecture.md §6`) but this is not a substitute for a real production database under concurrent load. | Two underwriters acting simultaneously, or a double-submitted application, could still surface edge-case issues at scale. | Mitigated for the demo (WAL mode, idempotency key, optimistic status locking) but flagged as a scaling limit, not a solved problem. |

## 11. Stretch Goals (not in baseline scope)

- Adverse-action reason generator producing regulator-friendly (ECOA/FCRA-style) reason codes and language.
- Challenger-model comparison (a second scoring approach run in parallel for validation).
- Affordability stress-testing (e.g., rate-shock or income-shock scenarios on DTI).

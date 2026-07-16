# Project Report
## Loan Application Processing Agent

**Project Title:** AI-Assisted Loan Application Processing Agent  
**Primary Language:** Python 3.14  
**Agent Framework:** LangGraph  
**UI Framework:** Streamlit  
**Date:** July 2026  
**Repository:** github.com/Wings_AI/loan-application-processing

---

## Introduction

Credit application processing in retail lending is slow, inconsistent, and difficult to audit. Loan officers manually review documents, apply policy thresholds from memory, and produce decisions that are hard to reconstruct after the fact — creating fairness risk and regulatory exposure.

This project builds an AI-assisted loan processing agent that automates the recommendation pipeline while keeping a licensed human as the sole decision-maker. The agent extracts structured data from uploaded documents, scores applications deterministically against a configurable policy engine, and routes them to an underwriter for the final decision — a decision the system is architecturally incapable of making itself.

The project is named after no specific person, but its design philosophy borrows from a core principle in regulated systems: the machine does the measurement; the human makes the judgment. Every number the agent produces is traceable to a specific policy clause and a specific line of source text. Every decision is signed by a human and stored permanently.

---

## Executive Summary

The system delivers a terminal-free, browser-accessible loan processing agent built in Python. It supports:

- **Document intake** — structured field extraction from government ID, payslip, and bank statement via LLM (Claude/GPT-4o), with per-field confidence scores and evidence spans
- **Validation** — four cross-document consistency checks (name match, ID validity, income plausibility, statement recency)
- **Deterministic scoring** — 100% Python policy engine, zero LLM involvement: DTI, credit history, and income stability produce a composite score and a recommendation band with policy clause citations
- **Identity-blind fairness check** — applicant name and address are redacted from documents, numeric fields re-extracted and re-scored; any band change is a hard fail surfaced to the underwriter
- **Guardrail** — free-text fields scanned for instruction-injection attempts; detected content logged and surfaced without affecting the score
- **Human gate** — the agent halts at `PENDING_HUMAN_REVIEW`; only the UI's `record_human_decision()` function can advance an application to `DECIDED`
- **Audit trail** — append-only SQLite log; every event, correction, and decision permanently recorded
- **Streamlit dashboard** — four screens: New Application, Review Queue, Application Detail, Audit Explorer

The architecture evolved through two design review rounds before implementation, closing eleven gaps including a broken fairness check, an undefined REFER routing model, ambiguous boundary rules in the scoring engine, and an unspecified audit export format.

All 66 tests pass. End-to-end testing confirmed composite scores of 1.000 (APPROVE) and 0.700 (REFER) matching hand-calculated values exactly.

---

## Architecture Overview

The system is structured as a layered pipeline. Each layer has a single responsibility and communicates only with adjacent layers.

```
┌─────────────────────────────────────────┐
│  Streamlit UI (main.py, pages/)         │  keyboard/mouse input, rendering
├─────────────────────────────────────────┤
│  LangGraph Agent (graph.py)             │  state machine, node routing
├──────────────┬──────────────────────────┤
│  Agent Nodes │  Formula: IntakeNode     │  LLM calls, structured extraction
│  (nodes.py)  │  ValidationNode          │  consistency checks
│              │  ScoringNode             │  pure Python, no LLM
│              │  FairnessNode            │  identity-blind re-extraction
│              │  RecommendationNode      │  LLM explanation only
│              │  GuardrailNode           │  adversarial content scan
│              │  AuditNode               │  persists final status
│              │  HumanGateNode           │  terminal no-op — halts agent
├──────────────┴──────────────────────────┤
│  Policy Engine (policy_engine/scorer.py)│  deterministic scoring, no I/O
├─────────────────────────────────────────┤
│  Repository Layer (repository/)         │  SQLAlchemy ORM, UnitOfWork
├─────────────────────────────────────────┤
│  SQLite + ChromaDB (data/)              │  system of record + policy clauses
└─────────────────────────────────────────┘
```

### Core Design Principle

The single most important architectural decision is the separation of the LLM from the scoring path:

- **LLM** — reads documents, extracts fields, checks consistency, writes explanations, scans for adversarial content
- **Python** — computes every number that determines APPROVE/REFER/DECLINE

This means the recommendation is reproducible. Given the same stored field values, running the scoring function again always produces the same result. This is what makes the audit record defensible to a regulator.

---

## Tech Stack

| Layer | Technology | Reason |
|---|---|---|
| Agent orchestration | LangGraph | Explicit typed state machine; each node's inputs/outputs are loggable |
| LLM calls | OpenAI-compatible client (GitHub Models / OpenRouter) | Structured output via Pydantic; 1-retry with validation error feedback |
| Reasoning model | GPT-4o (configurable via `.env`) | Document extraction, consistency reasoning, explanation phrasing |
| Policy engine | Plain Python module | Deterministic, unit-testable in isolation, zero LLM dependency |
| Policy clause store | ChromaDB (persistent, local) | Exact-ID clause lookup for citations; semantic search retained for manual underwriter use only |
| System of record | SQLite via SQLAlchemy | Relational integrity, exact audit queries, foreign-key-enforced human sign-off |
| Schema validation | Pydantic v2 | LLM outputs validated before entering scoring |
| UI | Streamlit | Browser-based underwriter dashboard |
| Audit export | WeasyPrint | HTML → PDF audit packages for regulatory handoff |
| Testing | pytest | 66 tests, all LLM calls stubbed |

---

## Agent Graph

The LangGraph graph is a directed acyclic pipeline with conditional branching on validation failures and errors:

```
Intake → Validate ──(pass)──► Score → Fairness → Recommend → Guardrail → Audit → HumanGate
              │
              └──(fail/error)──► Audit → END
```

Each node:
1. Receives the full `AgentState` TypedDict
2. Does its work (LLM call or pure Python)
3. Persists its output to SQLite immediately
4. Returns a partial state dict that LangGraph merges

Durable per-node writes mean a crash or API timeout mid-pipeline does not lose prior work. The next invocation for the same `application_id` resumes from the last completed node.

| Node | LLM? | Status it can set |
|---|---|---|
| IntakeNode | Yes | `AWAITING_DOCUMENTS`, `NEEDS_MANUAL_VERIFICATION` |
| ValidationNode | Yes | `INCONSISTENT_DOCUMENTS` |
| ScoringNode | No | `POLICY_CONFIG_ERROR` |
| FairnessNode | Yes (re-extraction) | — |
| RecommendationNode | Yes (explanation only) | — |
| GuardrailNode | Yes | — |
| AuditNode | No | `PENDING_HUMAN_REVIEW` |
| HumanGateNode | No | Nothing — terminal no-op |

The human gate is not a prompt instruction. `DECIDED` status can only be written by `record_human_decision()` in `src/agent/human_gate.py` — a function that lives outside the agent graph entirely, called only from the Streamlit UI.

---

## Policy Scoring Engine

The scoring engine (`src/policy_engine/scorer.py`) is 100% deterministic Python. Given the same inputs, it always returns the same output.

**Three factors, fixed weights:**

| Factor | Weight | Inputs |
|---|---|---|
| Debt-to-Income (DTI) | 40% | monthly obligations ÷ monthly income |
| Credit history | 35% | bureau score |
| Income stability | 25% | employment tenure months + income variability % |

**Income stability — weakest-link rule:**  
Two sub-factors are scored independently (tenure and variability), then combined as `min(tenure_score, variability_score)`. Strong tenure does not offset volatile income. The binding constraint's clause is cited.

**Band evaluation:**  
All thresholds live in `policy_config.yaml`. Two evaluation directions:
- `max_asc` (DTI, variability) — lower value is better; first entry where `value ≤ max` wins
- `min_desc` (bureau, tenure) — higher value is better; first entry where `value ≥ min` wins

Boundary rule: a value exactly on a stated boundary resolves to the better-scoring band. DTI = 0.40 exactly → moderate (0.7), not elevated.

**Composite score and recommendation bands:**

```
composite = dti_score×0.40 + bureau_score×0.35 + income_stability×0.25

composite ≥ 0.75 → APPROVE
composite ≥ 0.65 → REFER
composite  < 0.65 → DECLINE
```

**Policy clause citations:**  
Each band entry in `policy_config.yaml` names an exact `clause_id`. The engine reads this directly — no similarity search. The full clause text is fetched from ChromaDB by exact ID. If a `clause_id` in the config has no matching document in Chroma, the application halts with `POLICY_CONFIG_ERROR` rather than silently citing nothing.

---

## Document Validation

ValidationNode runs four checks, all implemented as structured LLM calls that return `{check_name, passed, evidence}` — the pass/fail gate is a Python boolean AND, not a free-form LLM judgment:

| Check | Logic |
|---|---|
| name_match | Names on ID, payslip, and bank statement refer to the same person (fuzzy match) |
| id_validity | ID expiry date is in the future at time of submission |
| income_plausibility | Stated monthly income is within ±15% of average bank deposits (Python arithmetic, not LLM) |
| statement_recency | Bank statement period end is within 60 days of submission |

Any single failed check halts the pipeline at `INCONSISTENT_DOCUMENTS`. No score is produced on inconsistent data.

**Low-confidence extraction:**  
Every numeric field extracted by IntakeNode must include a confidence (`high`/`medium`/`low`) and an evidence span (the literal source text). A `low` confidence on any scoring-relevant field (income, obligations, bureau score, tenure, variability) sets status to `NEEDS_MANUAL_VERIFICATION`. The underwriter reviews and corrects the value before scoring proceeds.

Corrections are stored as a new row in `extracted_fields` (never overwriting), tagged with `manually_verified=True`. Re-scoring then runs from ScoringNode forward, producing a new `revision_number` on all downstream tables.

---

## Fairness Check

FairnessNode performs an identity-blind extraction consistency check:

1. Applicant name and address are replaced with `[APPLICANT NAME]` and `[APPLICANT ADDRESS]` in all raw documents
2. The LLM re-extracts scoring-relevant numeric fields from the redacted documents
3. Those blind-extracted values are run through the same deterministic scorer
4. The resulting band is compared to the original

If the bands differ, the check fails. The disparity, both breakdowns, and the differing factors are persisted and surfaced prominently in the UI. The system never auto-resolves a disparity.

**What this tests:** whether the LLM extraction layer let applicant identity implicitly influence a numeric field (e.g., inferring income stability from an employer's perceived reputation).  
**What this does not test:** proxy discrimination, population-level disparate impact, or whether the policy thresholds themselves produce systematically different outcomes across groups. Those require statistical analysis over a population of decisions and are documented as a known limitation (L2).

---

## Data Model

All application data lives in SQLite, accessed through a repository layer (`src/repository/`). Nine tables:

| Table | Purpose |
|---|---|
| `applications` | One row per application; status + optimistic-locking `status_version` |
| `extracted_fields` | Append-only versioned; `is_effective=True` on the current value per field |
| `validation_results` | One row per check per application |
| `score_breakdowns` | Per-factor scores with sub-factor rows; versioned by `revision_number` |
| `recommendations` | Composite score + band + explanation text; versioned |
| `fairness_checks` | Original vs blind band + PASS/FAIL; versioned |
| `guardrail_flags` | Detected adversarial content; append-only |
| `human_decisions` | Multiple rows per application; only `APPROVE`/`DECLINE` are terminal |
| `audit_log` | Append-only event log; defined payload schema per event type |

**Key design choices:**

- `extracted_fields` is append-only versioned — a correction adds a new row with `is_effective=True` and flips the prior row to `False`. The original model-extracted value is never deleted, so an auditor can always see "what the system almost scored with."
- `human_decisions` supports multiple rows per application because a human REFER is non-terminal. An application can have a chain like `Agent: REFER → Human: REFER (escalate) → Human: DECLINE (final)`. Only a row with `decision ∈ {APPROVE, DECLINE}` sets `applications.status = DECIDED`.
- `audit_log` uses a defined `event_payload` schema per `event_type` — not a free-form dump — so the record is self-describing without requiring access to source code.

**Concurrency:** SQLite is opened in WAL mode. Status writes use optimistic locking via `status_version` — a write must supply the version it expects, and a mismatch raises `ConcurrentModificationError` rather than silently overwriting.

---

## Application Statuses

```
AWAITING_DOCUMENTS          → missing one or more required documents
NEEDS_MANUAL_VERIFICATION   → low-confidence extraction on a scoring field
INCONSISTENT_DOCUMENTS      → cross-document validation failed
PROCESSING_ERROR            → LLM API failure after retry
POLICY_CONFIG_ERROR         → clause_id in config has no matching Chroma document
PENDING_HUMAN_REVIEW        → agent complete; awaiting underwriter decision
REFERRED_FOR_ESCALATION     → underwriter issued a non-terminal REFER
DECIDED                     → terminal; underwriter issued APPROVE or DECLINE
```

---

## Streamlit UI

Four screens, all built with plain Streamlit components and inline CSS (Material Design 3 palette):

**Screen 1 — New Application (`main.py`)**  
Applicant name, address, and three file uploaders (Government ID, payslip, bank statement). PDF files are parsed with pypdf; text files read directly. On submit, a LangGraph agent run is started in a background thread with a progress indicator. On completion, redirects to the detail page.

**Screen 2 — Review Queue (`pages/queue.py`)**  
All applications listed with status chips, recommendation badges, fairness result, and guardrail flags. Filterable by status, band, and fairness result. Applications in `PENDING_HUMAN_REVIEW` and `NEEDS_MANUAL_VERIFICATION` are sorted to the top.

**Screen 3 — Application Detail (`pages/detail.py`)**  
- Recommendation hero card (colour-coded by band: green/amber/red)
- Full score breakdown table with per-factor raw values, band labels, weighted contributions, and policy clause IDs
- Fairness panel showing original vs blind band
- Validation check results (expandable)
- Extracted fields table with confidence badges and evidence spans; inline correction form for low-confidence fields
- Decision history (all prior REFER events)
- Decision form: APPROVE / REFER / DECLINE with mandatory rationale; REFER requires a categorical reason

**Screen 4 — Audit Explorer (`pages/audit.py`, `pages/audit_detail.py`)**  
Queue of all applications with KPI summary (approval rate, fairness pass rate, straight-through rate). Per-application detail shows the full audit event timeline and a "Generate Audit Package" button that exports a standalone HTML file containing all extracted field versions, all score revisions, guardrail flags, and the complete decision history — suitable for regulatory handoff.

---

## Testing

66 tests across three files, all runnable without an API key (LLM calls are stubbed in acceptance tests; the policy engine has no LLM dependency):

| File | Tests | Coverage |
|---|---|---|
| `test_repository.py` | 26 | DB models, WAL mode, optimistic locking, versioned `extracted_fields`, REFER non-terminal, audit append-only |
| `test_policy_engine.py` | 31 | All band boundaries including exact-boundary cases, weakest-link income stability, composite arithmetic, determinism |
| `test_acceptance.py` | 9 | 7 requirement scenarios + 2 human gate guards |

**Acceptance scenarios covered:**

| Scenario | Requirements |
|---|---|
| Clear APPROVE (happy path) | FR-01–FR-08, FR-11, FR-13 |
| Borderline REFER | FR-05–FR-08, FR-11 |
| Missing document → halt before scoring | FR-02, FR-04 |
| Identity-blind consistency check | FR-09, FR-10, NFR-02 |
| Prompt injection in application file | FR-12, FR-11, NFR-06 |
| REFER chain (non-terminal) | FR-11, FR-13, FR-14 |
| Low-confidence extraction → manual verification | FR-16 |

**End-to-end test results (live run against GitHub Models):**

| Scenario | Expected | Actual | Composite |
|---|---|---|---|
| Priya Sharma (APPROVE) | APPROVE | ✅ APPROVE | 1.000 |
| Arjun Mehta (REFER) | REFER | ✅ REFER | 0.700 |

Scores matched hand-calculated values to 4 decimal places. All validation checks passed. Fairness check: PASS on both (bands unchanged after identity redaction).

---

## Design Issues Resolved

Eight architectural issues were identified during design review and resolved before or during implementation.

**Issue 1 — Fairness check was vacuous**  
The original implementation re-scored with the same inputs without actually redacting identity from documents, so it always passed. Fixed by redacting applicant name and address from raw document text before re-extraction, making the check capable of detecting identity leakage.

**Issue 2 — REFER was undefined as a workflow state**  
The original design treated a human REFER decision the same as APPROVE/DECLINE — one decision, terminal. This was incorrect: REFER means "not enough to decide yet." Fixed by making human REFER non-terminal: it sets `REFERRED_FOR_ESCALATION`, appends a new row to `human_decisions` with a required categorical reason, and re-queues the application. Only `APPROVE` or `DECLINE` set `DECIDED`.

**Issue 3 — Band boundary rule was ambiguous**  
The specification said "inclusive on the lower bound" but the band shape uses `max` values (not `min` values for ascending bands), making "lower bound" undefined. Fixed by specifying direction-based first-match rules: `max_asc` uses `value ≤ max` in listed order; `min_desc` uses `value ≥ min` in listed order. A value on a boundary always wins the better-scoring adjacent band.

**Issue 4 — Income stability combination rule was unspecified**  
Tenure and variability were listed as sub-factors but no combination rule was given. Two implementations could diverge. Fixed by specifying `min(tenure_subscore, variability_subscore)` — weakest-link — with the binding constraint's clause cited.

**Issue 5 — Clause citation used similarity search**  
The original design queried ChromaDB by factor+band and trusted the top semantic match as the regulatory citation. Semantic similarity is not reliable enough to be the basis of a legal citation ("similarity ≠ correctness"). Fixed by assigning exact `clause_id` values in `policy_config.yaml` and doing a deterministic exact-ID lookup; a missing clause is a `POLICY_CONFIG_ERROR`, not a silent fallback.

**Issue 6 — Low-confidence fields had no defined re-entry path**  
The spec said a correction "unblocks scoring" but did not define the mechanism. Fixed: correction writes a new `extracted_fields` row, then the pipeline resumes from ScoringNode forward under the same `application_id`, producing a new `revision_number` on all downstream tables. Prior values are never deleted.

**Issue 7 — `extracted_fields` was update-in-place**  
Overwriting extracted values meant auditors could not see what the system "almost scored with." Fixed: the table is append-only versioned. Each correction adds a row; `is_effective` flags the current value.

**Issue 8 — Audit export format was unspecified**  
NFR-04 requires records presentable to a third party with no additional context. Without a defined format, a regulator would need database access to verify anything. Fixed: the Audit Explorer includes a "Generate Audit Package" button that produces a standalone HTML document (all field versions, all score revisions, decision history, guardrail flags) using WeasyPrint.

---

## Known Limitations

| # | Limitation | Status |
|---|---|---|
| L1 | No verified underwriter authentication. The sidebar role selector is self-reported; `human_decisions.underwriter_id` cannot be trusted as legal evidence of who decided. | **Blocking for production.** Requires SSO/signed sessions before real deployment. |
| L2 | Fairness check is extraction-layer only. It does not test proxy discrimination, neighborhood effects, or population-level disparate impact. | **Not solved.** Documented as explicit scope. A real deployment needs a separate periodic disparate-impact analysis by compliance. |
| L3 | Bureau score is simulated. No live credit bureau integration. | Documented assumption. Not a defect. |
| L4 | SQLite under concurrent Streamlit sessions. WAL mode + optimistic locking mitigate but do not eliminate edge cases under real concurrent load. | Mitigated for demo scale. PostgreSQL needed for production. |

---

## Project Structure

```
src/
├── agent/
│   ├── graph.py          LangGraph state machine + resume_from_scoring()
│   ├── nodes.py          All 8 node functions (~1,000 lines)
│   ├── schemas.py        Pydantic v2 models for all LLM structured outputs
│   ├── state.py          AgentState TypedDict
│   ├── human_gate.py     record_human_decision() — the ONLY path to DECIDED
│   └── llm_client.py     OpenAI-compatible client with retry
├── policy_engine/
│   └── scorer.py         Deterministic scoring, zero LLM, zero I/O
├── repository/
│   ├── models.py         SQLAlchemy ORM — 9 tables
│   ├── repo.py           Repository classes per table
│   ├── unit_of_work.py   UoW pattern
│   └── database.py       Engine creation, WAL mode
├── app/
│   ├── main.py           Screen 1 — New Application
│   ├── pages/queue.py    Screen 2 — Review Queue
│   ├── pages/detail.py   Screen 3 — Application Detail & Decision
│   ├── pages/audit.py    Screen 4 — Audit Explorer
│   └── pages/audit_detail.py  Per-application audit package
└── config.py             .env + policy_config.yaml loader

policy_config.yaml        All scoring thresholds — edit to change policy, no code changes
scripts/seed_chroma.py    Populates ChromaDB with 24 policy clauses (run once)
tests/                    66 tests: repository, policy engine, acceptance
test_docs/                20 test scenarios (× 3 documents each), .txt + .pdf
```

---

## Conclusion

The agent demonstrates that an LLM-assisted document processing system can be made audit-defensible without sacrificing the AI's strengths in reading unstructured text. The key is the clean boundary between what the LLM does (understand language) and what Python does (compute numbers). Every recommendation the agent produces is reproducible from stored inputs alone — the LLM is not in the loop for any recomputation.

The human gate is the project's strongest non-negotiable. It is not implemented as a polite prompt instruction. It is implemented as a physical code boundary: the only function that can write `DECIDED` to the database is one that lives outside the agent graph, receives its input from a human action in the UI, and validates the application is in a reviewable state before writing anything. An LLM cannot cross that boundary regardless of what it is asked.

The system is ready for demo and internal pilot use. The path to production requires one significant addition: verified underwriter authentication (SSO or signed sessions) to make the `human_decisions` table legally credible.

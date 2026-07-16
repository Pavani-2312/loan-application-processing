# Loan Application Processing Agent

An AI-assisted loan processing system for retail lenders. A LangGraph agent extracts structured data from uploaded documents, scores applications deterministically against a configurable policy engine, and routes them to a human underwriter for the final decision — which the system is architecturally incapable of making itself.

## What it does

1. **Intake** — Claude/GPT-4o extracts structured fields (income, DTI, bureau score, tenure) from uploaded documents with per-field confidence and evidence spans.
2. **Validation** — cross-document consistency checks (name match, ID validity, income plausibility, statement recency).
3. **Scoring** — 100% deterministic Python policy engine: no LLM involved. Weighted factors produce a composite score and recommendation band (APPROVE / REFER / DECLINE) with policy clause citations.
4. **Fairness check** — identity-blind re-extraction verifies no applicant identity leaked into the numeric scoring path.
5. **Recommendation** — LLM drafts a natural-language explanation citing each factor and its policy clause.
6. **Guardrail** — detects instruction-injection attempts in free-text fields; logs and surfaces to the underwriter without affecting the score.
7. **Human gate** — the agent halts at `PENDING_HUMAN_REVIEW`. Only the UI's `record_human_decision()` can advance an application to `DECIDED`.

## Quick navigation

| Page | Contents |
|------|----------|
| [[Architecture]] | System design, agent graph, component layers |
| [[Policy-Scoring-Engine]] | Scoring logic, band rules, policy config |
| [[Document-Validation]] | Consistency checks, low-confidence handling |
| [[Fairness-Check]] | Identity-blind re-extraction method and scope |
| [[Data-Model]] | All 9 tables, application statuses, audit log |
| [[UI-Guide]] | All 4 screens and keyboard actions |
| [[Testing]] | Test suite, scenarios, how to run |
| [[Setup-and-Running]] | Install, configure, run |
| [[Known-Limitations]] | L1–L4 and production blockers |

## Repository layout

```
src/
├── agent/           LangGraph nodes + graph + human gate
├── policy_engine/   Deterministic scoring (no LLM)
├── repository/      SQLite ORM models, repositories, UnitOfWork
├── app/             Streamlit pages
└── config.py        .env + policy_config.yaml loader

policy_config.yaml   All scoring thresholds — edit to change policy
scripts/             seed_chroma.py, txt_to_pdf.py
tests/               66 tests: repository, policy engine, acceptance
test_docs/           20 test scenarios (× 3 documents each), .txt + .pdf
```

## Application statuses at a glance

```
AWAITING_DOCUMENTS          → missing one or more required documents
NEEDS_MANUAL_VERIFICATION   → low-confidence extraction on a scoring field
INCONSISTENT_DOCUMENTS      → cross-document validation failed
PROCESSING_ERROR            → LLM API failure
POLICY_CONFIG_ERROR         → clause ID in config missing from Chroma
PENDING_HUMAN_REVIEW        → agent done; awaiting underwriter decision
REFERRED_FOR_ESCALATION     → underwriter issued a non-terminal REFER
DECIDED                     → terminal; underwriter issued APPROVE or DECLINE
```

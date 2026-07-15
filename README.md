# Loan Application Processing Agent

An AI-assisted loan application processing system for retail lenders. A LangGraph agent extracts structured data from uploaded documents, scores applications deterministically against a configurable policy engine, and routes them to a human underwriter for the final decision — which the system can never make itself.

## What it does

1. **Intake** — Claude extracts structured fields (income, DTI, bureau score, tenure) from uploaded documents with per-field confidence and evidence spans.
2. **Validation** — cross-document consistency checks (name match, ID validity, income plausibility, statement recency).
3. **Scoring** — 100% deterministic Python policy engine: no LLM involved. Weighted factors (DTI, credit history, income stability) produce a composite score and recommendation band (APPROVE / REFER / DECLINE) with policy clause citations.
4. **Fairness check** — identity-blind re-score verifies no applicant identity leaked into the numeric scoring path.
5. **Recommendation** — LLM drafts a natural-language explanation citing each factor and its policy clause.
6. **Guardrail** — detects instruction-injection attempts in free-text fields; logs and surfaces to the underwriter without affecting the score.
7. **Human gate** — the agent halts at `PENDING_HUMAN_REVIEW`. Only the UI's `record_human_decision()` function can advance an application to `DECIDED`.

## Architecture

```
src/
├── agent/           LangGraph nodes + graph + human gate
├── policy_engine/   Deterministic scoring (no LLM)
├── repository/      SQLite ORM models, repositories, UnitOfWork
│   └── models.py    All tables: applications, extracted_fields (versioned),
│                    score_breakdowns, recommendations, fairness_checks,
│                    guardrail_flags, human_decisions, audit_log
├── app/             Streamlit pages
│   └── pages/       queue.py, detail.py, audit.py, audit_detail.py
└── config.py        .env + policy_config.yaml loader

scripts/
└── seed_chroma.py   Populates ChromaDB with 24 policy clauses (run once)

policy_config.yaml   All scoring thresholds and band boundaries (edit to change policy)
docs/                Six design documents (requirements → architecture → UI → build prompt)
tests/               66 tests: repository, policy engine, acceptance (7 scenarios)
```

Key design decisions:
- **LLM for understanding, Python for scoring** — the scoring path is deterministic and audit-defensible.
- **Human gate is architectural**, not a prompt instruction — the `DECIDED` status can only be set by `record_human_decision()`, which checks `PENDING_HUMAN_REVIEW` / `REFERRED_FOR_ESCALATION` in the database.
- **Append-only audit trail** — `extracted_fields` is versioned (corrections add a row, never overwrite), `audit_log` is insert-only.
- **No in-process write lock** — relies on SQLite WAL mode + optimistic locking (`status_version`).
- **REFER is non-terminal** — multiple REFER events can precede a terminal APPROVE or DECLINE.

## Setup

### Prerequisites

- Python 3.10+ (tested on 3.14)
- A [GitHub Personal Access Token](https://github.com/settings/tokens) (for GitHub Models inference)

### Install

```bash
# 1. Clone and enter the project
cd /path/to/loan-application-processing

# 2. Create virtualenv and install dependencies
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env and set:
#   GITHUB_TOKEN=github_pat_...   (your GitHub Personal Access Token)
#   LLM_MODEL=openai/gpt-4o      (or any model from https://github.com/marketplace/models)
```

### Run

```bash
# Option A — use the launch script (seeds Chroma then starts the UI)
./run.sh

# Option B — manual steps
.venv/bin/python scripts/seed_chroma.py   # seed policy clauses (once)
.venv/bin/streamlit run src/app/main.py   # start UI

# Run tests only
./run.sh --test
# or
.venv/bin/python -m pytest tests/ -v
```

Open http://localhost:8501 in your browser.

## Running tests

```bash
.venv/bin/python -m pytest tests/ -v
```

66 tests across three files:

| File | Tests | What it covers |
|---|---|---|
| `test_repository.py` | 26 | DB models, WAL mode, optimistic locking, versioned extracted_fields, REFER non-terminal, audit append-only |
| `test_policy_engine.py` | 31 | All band boundaries, weakest-link income stability, composite arithmetic, determinism |
| `test_acceptance.py` | 9 | 7 requirement scenarios + 2 human gate guards (all LLM calls stubbed) |

Tests run without an API key — LLM calls are stubbed in acceptance tests; the policy engine has no LLM dependency.

## Policy configuration

All scoring thresholds live in `policy_config.yaml`. Edit it to update policy — no code changes needed.

```yaml
weights:
  dti: 0.40
  credit_history: 0.35
  income_stability: 0.25   # combined = min(tenure_subscore, variability_subscore)

bands:
  dti:
    direction: max_asc      # lower DTI is better
    entries:
      - {max: 0.30, score: 1.0, clause: "3.1(a)"}
      - {max: 0.40, score: 0.7, clause: "3.1(b)"}
      ...

recommendation_bands:
  approve_min: 0.75         # composite >= 0.75 → APPROVE
  refer_min: 0.65           # composite >= 0.65 → REFER; else DECLINE
```

Boundary rule: a value exactly on a boundary resolves to the **better-scoring** adjacent band (e.g. DTI = 0.40 → moderate, not elevated).

Income stability is the **minimum** of the tenure sub-score and the variability sub-score — strong tenure doesn't offset volatile income.

## Application statuses

```
AWAITING_DOCUMENTS          → missing one or more required documents
NEEDS_MANUAL_VERIFICATION   → low-confidence extraction on a scoring field
INCONSISTENT_DOCUMENTS      → cross-document validation failed
PROCESSING_ERROR            → LLM API failure
POLICY_CONFIG_ERROR         → clause ID in policy_config.yaml missing from Chroma
PENDING_HUMAN_REVIEW        → agent complete; awaiting underwriter decision
REFERRED_FOR_ESCALATION     → underwriter issued a non-terminal REFER
DECIDED                     → terminal; underwriter issued APPROVE or DECLINE
```

## Known limitations

- **L1 — Authentication:** Underwriter identity is self-selected from a sidebar dropdown in this build. The audit trail records who decided, but cannot verify it. Real deployment requires SSO/signed sessions.
- **L2 — Fairness scope:** The identity-blind consistency check detects whether applicant name/address leaked into the numeric scoring path for one application. It is not a population-level disparate-impact audit. See the KPI panel's tooltip in the Audit Explorer.

## Documents

Full design documentation in `docs/`:

| Doc | Contents |
|---|---|
| `00_Design_Review_Changelog.md` | Two rounds of design critique and all fixes applied |
| `01_Requirements.md` | Functional + non-functional requirements, KPIs, traceability table |
| `02_Architecture.md` | Component diagram, node sequence, concurrency, error handling |
| `03_Functional_Specification.md` | Node-by-node spec including `§1.2b` NEEDS_MANUAL_VERIFICATION re-entry |
| `04_Data_Policy_Model.md` | Full schema with event_payload definitions, policy config YAML |
| `05_UI_Design.md` | All four screens including audit package export |
| `06_CLI_Build_Prompt.md` | The step-by-step build prompt used to produce this codebase |

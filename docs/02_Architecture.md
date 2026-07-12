# 02 · System Architecture
## Project 05 — Loan / Credit Application Processing Agent

> Scope note: This document defines *how* the system is built at a component/data-flow level — the runtime shape of the agent, the storage split, and the control that enforces the human gate. Field-level logic (validation rules, scoring formulas) lives in `03_Functional_Specification.md`. Table/collection schemas live in `04_Data_Policy_Model.md`. Screens live in `05_UI_Design.md`.

---

## 1. Architecture Principles

1. **Deterministic scoring, LLM-assisted understanding.** The number that decides APPROVE/REFER/DECLINE is computed by plain Python, not by an LLM. The LLM extracts, reads, and explains — it never scores.
2. **Human gate as an architectural control, not a prompt instruction.** There is no code path that writes a `DECIDED` status without a human-originated action recorded via the UI. This is enforced by database schema (a `human_decisions` row is a foreign-key requirement for a `FINAL` status), not by asking the LLM nicely.
3. **Free text is data, never instruction.** Any user-supplied free text (notes, applicant remarks) is passed to the LLM only inside a clearly delimited "untrusted content" block and is never concatenated into the system/control prompt. The recommendation logic reads only structured numeric/categorical fields — free text cannot mathematically reach the scoring function.
4. **Everything material is written before it is shown.** The agent persists the audit record *before* the UI renders the recommendation to the underwriter, so a crash or a refresh can never lose the trace of what the agent actually computed.
5. **Reproducibility over cleverness.** Given the same stored inputs, re-running the scoring function must yield the same output. This is what makes the audit record defensible.

## 2. Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Orchestration | **LangGraph** | Explicit state machine graph maps 1:1 onto verify → score → fairness-check → recommend → audit → human-gate. Each node's inputs/outputs are typed and loggable — good for tracing. |
| LLM tool wrapping | **LangChain** | Structured output parsing (Pydantic) for document field extraction, tool-calling for policy retrieval. |
| Reasoning model | **Claude (Anthropic API)** | Document field extraction, consistency reasoning, natural-language explanation/citation phrasing, adverse-action reason drafting (stretch). |
| Deterministic policy engine | **Plain Python module**, no LLM | Computes DTI, credit-history score, income-stability score, composite score, and band. Unit-testable in isolation. |
| Policy clause storage & search | **ChromaDB** (persistent local, embedded) | Stores the credit policy split into clauses with embeddings, keyed by stable `clause_id`. **Revised role (see §7 decision log):** the primary citation attached to a score is a **deterministic ID lookup** — `policy_config.yaml` already names the exact clause for every band, so ScoringNode fetches that clause's text from Chroma by exact ID, never by similarity search. Chroma's semantic search capability is retained for a secondary purpose only: letting an underwriter search the full policy corpus in free text during manual review (e.g., to justify an exception or find a related clause). Semantic search never generates the citation shown as the basis for a recommendation. |
| System of record | **SQLite via SQLAlchemy** | Applications, documents, score breakdowns, recommendations, human decisions, and the append-only audit log. Relational integrity + exact/range queries needed for audit and KPI reporting — a vector store is the wrong tool for this. |
| Schema validation | **Pydantic v2** | Validates LLM-extracted document fields and all inter-node state before it can enter the scoring engine. |
| UI | **Streamlit** | Underwriter dashboard: queue, application detail/evidence view, decision capture, audit/export view. |
| Dependency/config | **Python 3.11+, `.env` for API keys** | Standard, no external services required to run locally. |

**Why not put everything in Chroma?** Chroma is good at "find clauses related to this free-text query" (semantic search) — useful for a human browsing policy, dangerous for generating a citation that will sit in a regulatory audit trail as "the reason for this decision," because similarity ≠ correctness. It also gives no transactional guarantees, exact filtering ("show me all DECLINEs in March for audit"), or foreign-key-enforced human sign-off. SQLite does. So the split is: **deterministic ID lookup (via config) for anything that becomes part of a decision's evidence; semantic search (via Chroma) only for human-initiated, non-decision-bearing policy lookup.**

## 3. High-Level Component Diagram

```
                         ┌─────────────────────────────┐
                         │        Streamlit UI          │
                         │  (Intake / Queue / Review /  │
                         │   Decision / Audit Explorer)  │
                         └──────────────┬───────────────┘
                                        │
                                        ▼
                         ┌─────────────────────────────┐
                         │     LangGraph Decisioning     │
                         │            Agent               │
                         │                               │
                         │  Intake → Validate → Score →  │
                         │  FairnessCheck → Recommend →  │
                         │  Guardrail → Audit → HumanGate │
                         └───┬──────────────┬────────────┘
                             │              │
                 ┌───────────▼───┐   ┌──────▼─────────┐
                 │  Claude API     │   │ Policy Rules    │
                 │ (extraction,    │   │ Engine (Python, │
                 │ consistency,    │   │ deterministic)  │
                 │ explanations)   │   │                 │
                 └────────────────┘   └───────┬─────────┘
                                               │ retrieves clause + score
                                       ┌───────▼─────────┐
                                       │   ChromaDB        │
                                       │ (policy clauses,  │
                                       │  embedded, RO)     │
                                       └───────────────────┘
                                               │
                         ┌─────────────────────▼─────────────────────┐
                         │              SQLite (system of record)      │
                         │  applications · documents · score_breakdowns │
                         │  recommendations · human_decisions ·          │
                         │  audit_log (append-only) · fairness_checks     │
                         └───────────────────────────────────────────┘
```

## 4. Agent Graph (LangGraph nodes)

| Node | Responsibility | Uses LLM? | Can it change application status to final? |
|---|---|---|---|
| **IntakeNode** | Parse uploaded documents + application form into a structured `ApplicationRecord`. | Yes — structured extraction | No |
| **ValidationNode** | Check presence of required docs; check cross-document consistency. | Yes — consistency reasoning over extracted fields | No — can only set status to `AWAITING_DOCUMENTS` or advance |
| **ScoringNode** | Deterministic DTI / credit-history / income-stability scoring; composite score. Retrieves clause citations from Chroma per factor. | No (Chroma retrieval only, not generation) | No |
| **FairnessNode** (Identity-Blind Extraction Consistency Check) | Re-runs ValidationNode + ScoringNode with `name`/`address` stripped from the record passed downstream; compares resulting band. **Narrowed scope, by design:** this catches identity leaking into the LLM extraction/consistency layer. It is not a disparate-impact or proxy-discrimination audit — see `01_Requirements.md §10` (L2). | Yes (re-runs the same extraction/consistency step blind) | No — can only set a `fairness_flag` |
| **RecommendationNode** | Maps composite score to band (APPROVE / REFER / DECLINE); assembles the cited breakdown into a human-readable recommendation. | Yes — phrasing/explanation only, band is already decided by ScoringNode | No — status stays `PENDING_HUMAN_REVIEW` |
| **GuardrailNode** | Scans free-text fields for injected instructions; logs any detected attempt; guarantees free text never entered the scoring path (structural check, not just a scan). | Yes — detection/classification | No |
| **AuditNode** | Writes the full record (inputs, extraction, validation, score breakdown, citations, fairness result, guardrail findings, recommendation) to SQLite. | No | No |
| **HumanGateNode** | Terminal node of the *agent* graph. Leaves status at `PENDING_HUMAN_REVIEW`. Nothing downstream of this node is agent code — the next write to this application's status can only come from the Streamlit decision-capture form, which calls a separate `record_human_decision()` function outside the agent graph. | No | **Only entry point that can set `DECIDED`, and only when the recorded human decision is APPROVE or DECLINE.** A human REFER is a valid, logged decision but is explicitly non-terminal — it sets `REFERRED_FOR_ESCALATION` and re-queues the application (see `03_Functional_Specification.md §3.2`). |

Graph edges:
```
Intake → Validate ──(complete & consistent)──▶ Score → Fairness → Recommend → Guardrail → Audit → HumanGate
              │
              └──(missing/inconsistent)──▶ Audit(flag=AWAITING_DOCUMENTS) → END (no recommendation produced)
```

## 5. Data Flow — Happy Path

1. Underwriter (or intake clerk) submits application form + document uploads via Streamlit.
2. UI calls the LangGraph agent with a raw intake payload.
3. IntakeNode extracts structured fields from documents via Claude, validated against Pydantic schemas.
4. ValidationNode checks presence + consistency. If failed → short-circuit to `AWAITING_DOCUMENTS`, audit record written, UI shows "documents needed," pipeline stops. **No score is produced.**
5. ScoringNode computes the three factor scores + composite, querying Chroma for the clause backing each factor.
6. FairnessNode strips identity, re-runs the extraction-dependent steps, recomputes the composite band, compares to step 5's band.
7. RecommendationNode assembles APPROVE/REFER/DECLINE + citations + fairness result into a recommendation object.
8. GuardrailNode confirms no free-text instruction reached the scoring path; logs any adversarial content found.
9. AuditNode persists everything to SQLite as one immutable record, status = `PENDING_HUMAN_REVIEW`.
10. Streamlit renders the recommendation + full evidence trail to the underwriter.
11. Underwriter records a decision (approve/refer/decline + rationale) in the UI. This is the **only** write that can set status = `DECIDED`. It is appended to `human_decisions` and linked to the original audit record — the original record is never edited.

## 6. Deployment Shape (this build)

- Single Python process running Streamlit; LangGraph agent invoked in-process (no separate service needed at this scale).
- SQLite file + Chroma persistent directory both live under a local `/data` folder — swappable for PostgreSQL + a hosted Chroma/pgvector instance without changing the node logic, since access goes through a thin repository layer (see `03_Functional_Specification.md §7`).
- Designed so that promoting to production later means swapping the repository layer's backing store and adding auth — not rewriting the agent graph or scoring logic.

**Concurrency & idempotency (known limit, partially mitigated — revised per review):**
Streamlit sessions may run as separate threads *or separate processes* depending on deployment; an in-process Python lock (`threading.Lock`) only protects against the former and silently does nothing against the latter, which means it can be implemented "correctly" per an earlier draft of this doc while providing zero real protection. That in-process lock is removed from this design. The two mechanisms actually relied upon are both enforced at the database layer, which works regardless of process topology:
- SQLite opened in **WAL mode** (`PRAGMA journal_mode=WAL`) — allows concurrent readers alongside a single writer, and serializes writers safely at the engine level.
- **Optimistic locking on `applications.status`** via `status_version`: every status-changing write must supply the version it expects to overwrite; SQLite's own write serialization means a losing concurrent writer gets a clean version-mismatch conflict, not a corrupted row — no application-level lock needed on top of this.
- **Idempotency key on intake:** the New Application form generates a client-side request token; the repository layer rejects a second `IntakeNode` run carrying the same token (guards against double-click/network-retry duplicate submissions). This is orthogonal to the write-serialization question above — it's a request-dedup concern, not a locking concern.
- This is sufficient for a small underwriting team's demo load. It is explicitly **not** a substitute for a real multi-writer production database (PostgreSQL) under real concurrent load — see `01_Requirements.md §10` (L4).

**Pipeline timeout & resumability (new — closes an unaddressed gap from review):**
The agent graph makes several sequential Claude API calls (Intake, Validation, Fairness re-run, Recommendation, Guardrail); a slow or throttled API could otherwise leave a Streamlit spinner running indefinitely with no defined outcome. This build makes the pipeline durable and boundable instead:
- **Per-node timeout:** each node's Claude call has a 30-second timeout (covering the retry described in `03_Functional_Specification.md §8`); exceeding it counts as that node's failure path (`PROCESSING_ERROR` or `NEEDS_MANUAL_VERIFICATION`, per node).
- **Durable intermediate state:** unlike the original design (which only wrote to SQLite once, at AuditNode), each node now persists its own output as soon as it completes (e.g., IntakeNode's extraction is written before ValidationNode runs). This means a crash or timeout mid-pipeline doesn't lose prior work.
- **Resumability:** if the pipeline is interrupted (process restart, Streamlit timeout, API outage), the next invocation for that `application_id` resumes from the last successfully completed node rather than restarting from IntakeNode — determined by reading which node-level records already exist for that application.
- **UI behavior:** the spinner shows elapsed time; past a soft threshold (e.g. 20s) it adds "This can take up to a minute — you can navigate away and return to this application; progress is saved." No hard cancel is needed given resumability, so none is built.

## 7. Key Design Decisions Log

| Decision | Alternative considered | Why this choice |
|---|---|---|
| Deterministic Python scoring engine, not LLM scoring | Let Claude compute the composite score directly | Regulatory defensibility requires reproducibility; an LLM score can vary run-to-run and is hard to defend as "the policy was applied," not "the model felt approve-ish." |
| SQLite (not Chroma) as system of record | Store everything in Chroma with metadata filters | Chroma's filtering is not a substitute for relational integrity, exact audit queries, and enforced foreign keys (e.g., `DECIDED` requires a `human_decisions` row). |
| Chroma scoped narrowly to policy clauses only | One shared vector store for documents + policy + audit | Keeping Chroma single-purpose (retrieval for citations) keeps the fairness/audit story simple: the audit record is 100% reconstructable from SQLite alone; Chroma is a lookup aid, not a source of truth. |
| HumanGateNode is outside the LLM's control entirely | Ask the LLM to "only recommend, never decide" via prompt | A prompt instruction is not a control. Making the final-status write physically live in a different code path, triggered only by a UI action, is what actually prevents automated adverse action. |
| Free text passed to LLM only as delimited untrusted content, never influences the deterministic scorer | Let the LLM read the whole application including notes and use judgment | Removes the entire class of prompt-injection risk from the number that matters (the score); the "pressure in the file" scenario becomes a guardrail *log entry*, not a risk to the outcome. |
| Citation is a deterministic clause-ID lookup from `policy_config.yaml`, not Chroma similarity search | Query Chroma by factor+band and trust the top semantic match | With ~20 clauses and a small policy corpus, semantic similarity is not reliable enough to be the basis of a regulatory citation. Since the config already assigns the correct clause ID to every band by construction (the policy owner wrote it that way), a lookup is both simpler and strictly correct — Chroma is repositioned as a human-facing search tool, not a citation generator. |
| Income stability combines two sub-scores (tenure, variability) via **minimum**, not average | Weighted average of the two sub-scores | Minimum ("weakest link") is the conservative, standard credit-risk convention — a strong tenure doesn't offset volatile income, and vice versa. It's also unambiguous and trivially deterministic, closing the NFR-02 gap the review identified. |
| Human REFER is non-terminal; only APPROVE/DECLINE close an application | Treat REFER as a valid final human decision, same as APPROVE/DECLINE | REFER means "not enough to decide yet," not "decided." Treating it as terminal made `matches_recommendation` and the audit trail ambiguous — an application referred by the agent and "confirmed" REFER by a human would look closed but nothing was actually resolved. Making it non-terminal forces every application to eventually land on a real outcome. |
| Extracted numeric fields require a confidence score + evidence span from Claude; low confidence blocks auto-scoring | Trust any Pydantic-valid extraction | A hallucinated-but-plausible value (e.g., tenure read as 36 months instead of 3) passes schema validation silently. Requiring the model to also report its confidence and point to the source text turns an invisible failure mode into a visible, human-reviewable one. |
| Concurrency relies solely on SQLite WAL + optimistic locking, not an added in-process Python lock | Add a `threading.Lock`-based serialized writer path on top of the DB mechanisms | An in-process lock only protects against multi-threading, not multi-processing — Streamlit's execution model can be either depending on deployment, so a lock that "looks" like protection can silently do nothing. The DB-layer mechanisms are correct regardless of process topology, so nothing else is needed or should be relied upon. |
| Each node persists its output immediately rather than only writing once at AuditNode | Keep intermediate state in memory and write once at the end | A single end-of-pipeline write means a timeout or crash partway through loses all prior work and leaves no record of what happened. Durable per-node writes make the pipeline resumable and give the audit trail a record even for interrupted runs. |



# Architecture

## Core principle

The LLM reads and understands; Python computes the score. The number that determines APPROVE / REFER / DECLINE is produced by a pure Python function — deterministic, testable in isolation, zero LLM dependency.

## Component layers

```
┌─────────────────────────────────────────┐
│  Streamlit UI (main.py, pages/)         │  browser input + rendering
├─────────────────────────────────────────┤
│  LangGraph Agent (graph.py)             │  typed state machine
├──────────────────────────────────────── ┤
│  Agent Nodes (nodes.py)                 │
│   IntakeNode        → LLM extraction    │
│   ValidationNode    → LLM consistency   │
│   ScoringNode       → Python only       │
│   FairnessNode      → LLM re-extract    │
│   RecommendationNode→ LLM explanation   │
│   GuardrailNode     → LLM detection     │
│   AuditNode         → persists status   │
│   HumanGateNode     → terminal no-op    │
├─────────────────────────────────────────┤
│  Policy Engine (policy_engine/scorer.py)│  deterministic, no I/O
├─────────────────────────────────────────┤
│  Repository Layer (repository/)         │  SQLAlchemy ORM + UnitOfWork
├─────────────────────────────────────────┤
│  SQLite + ChromaDB (data/)              │  system of record + policy text
└─────────────────────────────────────────┘
```

## Agent graph

```
Intake → Validate ──(pass)──► Score → Fairness → Recommend → Guardrail → Audit → HumanGate
              │
              └──(fail/error)──► Audit → END
```

Each node receives the full `AgentState` TypedDict, does its work, persists its output to SQLite immediately, and returns a partial state update. Durable per-node writes mean a crash or API timeout does not lose prior work — the next invocation resumes from the last completed node.

## Node responsibilities

| Node | LLM? | What it does | Terminal statuses it can set |
|------|------|--------------|------------------------------|
| IntakeNode | Yes | Extracts 12 fields from documents with confidence + evidence spans | `AWAITING_DOCUMENTS`, `NEEDS_MANUAL_VERIFICATION` |
| ValidationNode | Yes | Runs 4 cross-document consistency checks | `INCONSISTENT_DOCUMENTS` |
| ScoringNode | No | Deterministic DTI / bureau / income-stability scoring | `POLICY_CONFIG_ERROR` |
| FairnessNode | Yes | Identity-blind re-extraction + re-score | — |
| RecommendationNode | Yes | Drafts explanation (band already decided) | — |
| GuardrailNode | Yes | Scans free-text for instruction injection | — |
| AuditNode | No | Sets `PENDING_HUMAN_REVIEW` | `PENDING_HUMAN_REVIEW` |
| HumanGateNode | No | No-op — agent halts here | — |

## Human gate

`DECIDED` status can only be written by `record_human_decision()` in `src/agent/human_gate.py`. This function lives outside the agent graph. It is called only from the Streamlit UI. The LangGraph agent cannot reach it. This is an architectural control, not a prompt instruction.

## Tech stack

| Layer | Technology |
|-------|-----------|
| Agent orchestration | LangGraph 1.2.9 |
| LLM client | openai 2.45.0 (OpenAI-compatible; points at GitHub Models or OpenRouter) |
| Schema validation | Pydantic v2 |
| Policy engine | Plain Python (no external dependencies) |
| Policy clause store | ChromaDB 1.5.9 (persistent local) |
| System of record | SQLite via SQLAlchemy 2.0.51 |
| UI | Streamlit 1.59.1 |
| Audit export | WeasyPrint 69.0 |
| Testing | pytest 9.1.1 |

## Concurrency

SQLite is opened in WAL mode. Status writes use optimistic locking via `status_version` — a write must supply the version it expects; a mismatch raises `ConcurrentModificationError` rather than silently overwriting. No in-process `threading.Lock` is used (it would be ineffective against multi-process Streamlit deployments).

## Resumability

If the pipeline is interrupted mid-run, the next invocation reads which node-level records already exist for that `application_id` and resumes from the last completed node rather than restarting from IntakeNode.

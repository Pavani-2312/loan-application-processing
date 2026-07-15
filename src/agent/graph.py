"""
src/agent/graph.py

LangGraph agent graph.
Wires all nodes in the correct order with conditional branching.

Graph shape (from docs/02_Architecture.md §4):
  Intake → Validate ─(pass)─► Score → Fairness → Recommend → Guardrail → Audit → HumanGate
                    └─(fail)─► Audit → END
"""
from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from src.agent.nodes import (
    audit_node,
    fairness_node,
    guardrail_node,
    human_gate_node,
    intake_node,
    recommendation_node,
    scoring_node,
    validation_node,
)
from src.agent.state import AgentState


# ---------------------------------------------------------------------------
# Routing functions (pure functions — no side effects)
# ---------------------------------------------------------------------------

def _route_after_intake(state: AgentState) -> str:
    """After intake: halt if documents missing or low-confidence fields detected."""
    if state.get("final_status") in ("PROCESSING_ERROR", "POLICY_CONFIG_ERROR"):
        return "audit_node"
    if not state.get("intake_complete"):
        return "audit_node"
    if state.get("needs_manual_verification"):
        return "audit_node"  # Halts at NEEDS_MANUAL_VERIFICATION; re-entry via scoring_node when human confirms
    return "validation_node"


def _route_after_validation(state: AgentState) -> str:
    """After validation: continue to scoring if passed, else halt."""
    if state.get("final_status") in ("PROCESSING_ERROR", "POLICY_CONFIG_ERROR"):
        return "audit_node"
    if not state.get("validation_passed"):
        return "audit_node"
    return "scoring_node"


def _route_after_scoring(state: AgentState) -> str:
    """After scoring: continue to fairness check unless error."""
    if state.get("final_status") in ("PROCESSING_ERROR", "POLICY_CONFIG_ERROR"):
        return "audit_node"
    return "fairness_node"


def _route_after_fairness(state: AgentState) -> str:
    """After fairness check: always continue to recommendation (fairness FAIL is surfaced, not a halt)."""
    return "recommendation_node"


def _route_after_recommendation(state: AgentState) -> str:
    return "guardrail_node"


def _route_after_guardrail(state: AgentState) -> str:
    return "audit_node"


def _route_after_audit(state: AgentState) -> str:
    """After audit: if human review needed, go to human gate; otherwise END."""
    final = state.get("final_status", "")
    if final == "PENDING_HUMAN_REVIEW":
        return "human_gate_node"
    return END


# ---------------------------------------------------------------------------
# Build the compiled graph
# ---------------------------------------------------------------------------

def build_graph() -> Any:
    """Build and compile the LangGraph StateGraph."""
    builder = StateGraph(AgentState)

    # Add all nodes
    builder.add_node("intake_node", intake_node)
    builder.add_node("validation_node", validation_node)
    builder.add_node("scoring_node", scoring_node)
    builder.add_node("fairness_node", fairness_node)
    builder.add_node("recommendation_node", recommendation_node)
    builder.add_node("guardrail_node", guardrail_node)
    builder.add_node("audit_node", audit_node)
    builder.add_node("human_gate_node", human_gate_node)

    # Entry point
    builder.add_edge(START, "intake_node")

    # Conditional routing
    builder.add_conditional_edges("intake_node", _route_after_intake)
    builder.add_conditional_edges("validation_node", _route_after_validation)
    builder.add_conditional_edges("scoring_node", _route_after_scoring)
    builder.add_edge("fairness_node", "recommendation_node")
    builder.add_edge("recommendation_node", "guardrail_node")
    builder.add_edge("guardrail_node", "audit_node")
    builder.add_conditional_edges("audit_node", _route_after_audit)
    builder.add_edge("human_gate_node", END)

    return builder.compile()


# ---------------------------------------------------------------------------
# Public API — run the full pipeline
# ---------------------------------------------------------------------------

# Compiled graph (lazy singleton)
_graph = None

def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def run_agent(
    application_id: str,
    applicant_name: str,
    applicant_address: str,
    raw_documents: dict[str, str],
    idempotency_key: str | None = None,
) -> AgentState:
    """
    Run the full LangGraph agent pipeline for a new application.

    Args:
        application_id:  Pre-created application ID from the repository layer.
        applicant_name:  Applicant's full name (identity-bearing; used by intake only).
        applicant_address: Applicant's address (identity-bearing; used by intake only).
        raw_documents:   Dict of {doc_type: text_content} for each uploaded document.
        idempotency_key: Optional client-generated token for duplicate submission detection.

    Returns:
        Final AgentState after all nodes have run.
    """
    initial_state: AgentState = {
        "application_id": application_id,
        "applicant_name": applicant_name,
        "applicant_address": applicant_address,
        "raw_documents": raw_documents,
        "idempotency_key": idempotency_key,
        "scoring_revision_number": 1,
    }

    graph = get_graph()
    final_state = graph.invoke(initial_state)
    return final_state


def resume_from_scoring(application_id: str, underwriter_id: str) -> AgentState:
    """
    Resume the pipeline from ScoringNode after a human has confirmed/corrected
    a low-confidence field (§1.2b of docs/03_Functional_Specification.md).

    Does NOT re-run IntakeNode or ValidationNode.
    Reads the current effective extracted_fields from DB (including the correction).
    
    Args:
        application_id: The application to re-score
        underwriter_id: Identity of the underwriter who made the correction
    """
    from src.agent.nodes import (
        _get_session_factory,
        audit_node,
        fairness_node,
        guardrail_node,
        human_gate_node,
        recommendation_node,
        scoring_node,
    )
    from src.repository import UnitOfWork

    uow_factory = _get_session_factory()

    with UnitOfWork(uow_factory) as uow:
        app = uow.applications.get(application_id)
        if not app:
            raise ValueError(f"Application {application_id} not found")
        next_rev = uow.score_breakdowns.get_next_revision_number(application_id)
        existing_fields = uow.extracted_fields.get_effective_fields(application_id)
        # Build a partial state from what's in DB
        current_state: AgentState = {
            "application_id": application_id,
            "applicant_name": app.applicant_name,
            "applicant_address": app.applicant_address,
            "raw_documents": {},
            "intake_complete": True,
            "validation_passed": True,
            "needs_manual_verification": False,
            "scoring_revision_number": next_rev,
            "extracted_fields": {
                name: {
                    "value": row.field_value,
                    "confidence": row.confidence,
                    "evidence_span": row.evidence_span,
                    "source_document": row.source_document,
                }
                for name, row in existing_fields.items()
            },
        }

        # Log the re-score event
        uow.audit_logs.append(application_id, "RESCORED_AFTER_VERIFICATION", {
            "revision_number": next_rev,
            "triggering_underwriter_id": underwriter_id,
        })
        # Don't change status here - let audit_node set it correctly after re-scoring completes
        uow.commit()

    # Re-run from ScoringNode forward, respecting the same error routing the
    # compiled graph would apply via _route_after_scoring.
    _ERROR_STATUSES = {"PROCESSING_ERROR", "POLICY_CONFIG_ERROR"}

    state = dict(current_state)

    state = {**state, **scoring_node(state, revision_number=next_rev)}
    if state.get("final_status") in _ERROR_STATUSES:
        # Persist error status and stop — same as _route_after_scoring → audit_node
        audit_node(state)
        return state

    state = {**state, **fairness_node(state)}
    state = {**state, **recommendation_node(state)}
    state = {**state, **guardrail_node(state)}
    state = {**state, **audit_node(state)}
    state = {**state, **human_gate_node(state)}

    return state

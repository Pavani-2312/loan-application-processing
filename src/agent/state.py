"""
src/agent/state.py

LangGraph agent state — the typed dict that flows through every node.
Designed to be append-friendly: most fields are set once and never overwritten.
"""
from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    # ---- Intake ----
    application_id: str
    applicant_name: str
    applicant_address: str
    idempotency_key: str | None
    raw_documents: dict[str, str]   # {doc_type: raw_text} — e.g. {"id": "...", "payslip": "...", "bank_statement": "..."}
    # Fields extracted by IntakeNode — {field_name: {value, confidence, evidence_span, source_document}}
    extracted_fields: dict[str, dict[str, Any]]
    # Which document types were found (for presence check)
    documents_present: list[str]
    missing_documents: list[str]
    # True if all three document types present and extraction complete
    intake_complete: bool

    # ---- Validation ----
    validation_checks: list[dict[str, Any]]  # [{check_name, passed, evidence}]
    validation_passed: bool
    # If validation failed, the reason for halting
    validation_halt_reason: str | None

    # ---- Needs manual verification ----
    # Fields that have low confidence on scoring-relevant inputs
    low_confidence_fields: list[str]
    needs_manual_verification: bool

    # ---- Scoring ----
    scoring_revision_number: int
    scoring_result: dict[str, Any] | None   # Serialized ScoringResult

    # ---- Fairness check ----
    fairness_result: str | None     # PASS / FAIL
    fairness_original_band: str | None
    fairness_blind_band: str | None
    fairness_disparity_detail: str | None

    # ---- Recommendation ----
    recommendation_band: str | None   # APPROVE / REFER / DECLINE
    recommendation_explanation: str | None
    composite_score: float | None

    # ---- Guardrail ----
    guardrail_flags: list[dict[str, Any]]   # [{field, excerpt, reason}]

    # ---- Final status set by AuditNode ----
    final_status: str   # One of the APPLICATION_STATUS values

    # ---- Error handling ----
    error_message: str | None
    error_node: str | None

"""
src/agent/human_gate.py

record_human_decision() — the ONLY code path that can write a DECIDED status.
This is physically separate from the agent graph — it can only be called from UI code.

Implements docs/02_Architecture.md §4 (HumanGateNode as architectural control) and
docs/03_Functional_Specification.md §3.2 (REFER as non-terminal).
"""
from __future__ import annotations

from src.agent.nodes import _get_session_factory
from src.repository import ConcurrentModificationError, UnitOfWork


class HumanDecisionError(Exception):
    """Raised when a human decision cannot be recorded (wrong state, concurrent modification, etc.)."""


def record_human_decision(
    application_id: str,
    underwriter_id: str,
    decision: str,           # APPROVE / REFER / DECLINE
    rationale: str,
    refer_reason: str | None = None,  # Required when decision == REFER
) -> dict:
    """
    Record a human underwriter's decision for an application.

    - APPROVE / DECLINE: sets applications.status = DECIDED (terminal).
    - REFER: sets applications.status = REFERRED_FOR_ESCALATION (non-terminal, re-queued).
    - Multiple REFER events are allowed before a terminal decision.

    Returns a dict with decision_id, is_terminal, new_status.
    Raises HumanDecisionError on invalid state transitions or concurrent modification.

    Note on authentication (L1 from docs/01_Requirements.md §10):
    underwriter_id is self-reported — not cryptographically verified in this build.
    Sidebar shows "Demo mode — underwriter identity is self-selected, not verified."
    """
    if decision not in ("APPROVE", "REFER", "DECLINE"):
        raise HumanDecisionError(f"Invalid decision: {decision!r}. Must be APPROVE, REFER, or DECLINE.")
    if decision == "REFER" and not refer_reason:
        raise HumanDecisionError("refer_reason is required when decision is REFER.")
    if decision == "REFER" and refer_reason not in (
        "REQUEST_MORE_INFO", "ESCALATE_TO_SENIOR_UNDERWRITER", "ESCALATE_TO_COMMITTEE"
    ):
        raise HumanDecisionError(
            f"Invalid refer_reason: {refer_reason!r}. "
            "Must be REQUEST_MORE_INFO, ESCALATE_TO_SENIOR_UNDERWRITER, or ESCALATE_TO_COMMITTEE."
        )
    if not rationale or not rationale.strip():
        raise HumanDecisionError("rationale is required and cannot be empty.")

    with UnitOfWork(_get_session_factory()) as uow:
        app = uow.applications.get(application_id)
        if not app:
            raise HumanDecisionError(f"Application {application_id} not found.")

        # Only allow decisions when in a reviewable state
        reviewable_statuses = {"PENDING_HUMAN_REVIEW", "REFERRED_FOR_ESCALATION"}
        if app.status not in reviewable_statuses:
            raise HumanDecisionError(
                f"Application is in status {app.status!r} — only applications in "
                f"{reviewable_statuses} can receive a human decision."
            )

        # Get the current recommendation band for the audit snapshot
        latest_rec = uow.recommendations.get_latest(application_id)
        recommendation_at_time = latest_rec.band if latest_rec else "UNKNOWN"

        # Record the decision
        decision_row = uow.human_decisions.add(
            application_id=application_id,
            underwriter_id=underwriter_id,
            decision=decision,
            recommendation_at_time=recommendation_at_time,
            rationale=rationale,
            refer_reason=refer_reason,
        )

        # Update application status
        new_status = "DECIDED" if decision in ("APPROVE", "DECLINE") else "REFERRED_FOR_ESCALATION"

        try:
            uow.applications.update_status(application_id, new_status, app.status_version)
        except ConcurrentModificationError as e:
            uow.rollback()
            raise HumanDecisionError(
                "This application was modified by another session. Please refresh and try again."
            ) from e

        # Append audit log
        uow.audit_logs.append(application_id, "HUMAN_DECIDED", {
            "decision_id": decision_row.decision_id,
            "decision": decision,
            "refer_reason": refer_reason,
            "is_terminal": decision_row.is_terminal,
            "matches_recommendation": decision_row.matches_recommendation,
            "underwriter_id": underwriter_id,
        })

        uow.commit()

    return {
        "decision_id": decision_row.decision_id,
        "is_terminal": decision_row.is_terminal,
        "new_status": new_status,
        "matches_recommendation": decision_row.matches_recommendation,
    }

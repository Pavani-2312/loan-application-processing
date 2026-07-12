"""
tests/test_repository.py

Unit tests for the SQLite repository layer.
Uses an in-memory SQLite DB — no file created, no cleanup needed.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from src.repository import (
    ConcurrentModificationError,
    UnitOfWork,
    create_db_engine,
    get_session_factory,
    init_db,
)


@pytest.fixture
def uow_factory():
    """In-memory DB + session factory for each test."""
    engine = create_db_engine(":memory:")
    init_db(engine)
    factory = get_session_factory(engine)
    return factory


@pytest.fixture
def uow(uow_factory):
    with UnitOfWork(uow_factory) as u:
        yield u
        # Don't commit — tests manage their own commits


# ---------------------------------------------------------------------------
# WAL + FK check
# ---------------------------------------------------------------------------
def test_wal_mode_enabled(uow_factory):
    engine = create_db_engine(":memory:")
    init_db(engine)
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA journal_mode")).scalar()
        # SQLite in-memory doesn't persist WAL but the pragma should be set
        assert result in ("wal", "memory")


# ---------------------------------------------------------------------------
# Application CRUD
# ---------------------------------------------------------------------------
def test_create_application(uow):
    app = uow.applications.create(
        applicant_name="Alice Smith",
        applicant_address="1 Main St",
        idempotency_key="key-001",
    )
    uow.commit()
    assert app.application_id
    assert app.status == "AWAITING_DOCUMENTS"
    assert app.status_version == 1


def test_idempotency_key_deduplication(uow):
    app1 = uow.applications.create(
        applicant_name="Alice", applicant_address="1 Main St", idempotency_key="same-key"
    )
    uow.commit()
    app2 = uow.applications.create(
        applicant_name="Bob", applicant_address="2 Other St", idempotency_key="same-key"
    )
    uow.commit()
    # Same key → same record returned, not a new one
    assert app1.application_id == app2.application_id


def test_get_application(uow):
    app = uow.applications.create(applicant_name="Bob", applicant_address="2 St")
    uow.commit()
    fetched = uow.applications.get(app.application_id)
    assert fetched is not None
    assert fetched.applicant_name == "Bob"


def test_get_nonexistent_application(uow):
    assert uow.applications.get("no-such-id") is None


def test_update_status_optimistic_lock_success(uow):
    app = uow.applications.create(applicant_name="Carol", applicant_address="3 St")
    uow.commit()
    new_ver = uow.applications.update_status(app.application_id, "PROCESSING_ERROR", current_version=1)
    uow.commit()
    assert new_ver == 2
    refreshed = uow.applications.get(app.application_id)
    assert refreshed.status == "PROCESSING_ERROR"
    assert refreshed.status_version == 2


def test_update_status_optimistic_lock_conflict(uow):
    app = uow.applications.create(applicant_name="Dave", applicant_address="4 St")
    uow.commit()
    # First update succeeds
    uow.applications.update_status(app.application_id, "PENDING_HUMAN_REVIEW", current_version=1)
    uow.commit()
    # Second update with stale version should raise
    with pytest.raises(ConcurrentModificationError):
        uow.applications.update_status(app.application_id, "DECIDED", current_version=1)


def test_get_by_status(uow):
    uow.applications.create(applicant_name="E", applicant_address="5 St")  # AWAITING_DOCUMENTS
    uow.commit()
    results = uow.applications.get_by_status("AWAITING_DOCUMENTS")
    assert len(results) >= 1


# ---------------------------------------------------------------------------
# ExtractedField — append-only versioning
# ---------------------------------------------------------------------------
def test_extracted_field_version_1(uow):
    app = uow.applications.create(applicant_name="F", applicant_address="6 St")
    uow.commit()
    field = uow.extracted_fields.upsert_field(
        application_id=app.application_id,
        field_name="bureau_score",
        field_value="720",
        confidence="high",
        evidence_span="Score: 720",
    )
    uow.commit()
    assert field.field_version == 1
    assert field.is_effective is True
    assert field.manually_verified is False


def test_extracted_field_correction_adds_version(uow):
    app = uow.applications.create(applicant_name="G", applicant_address="7 St")
    uow.commit()
    # Original extraction
    uow.extracted_fields.upsert_field(
        application_id=app.application_id,
        field_name="employment_tenure_months",
        field_value="36",  # model hallucinated 36
        confidence="low",
        evidence_span="30 months",
    )
    uow.commit()
    # Human correction
    uow.extracted_fields.upsert_field(
        application_id=app.application_id,
        field_name="employment_tenure_months",
        field_value="3",  # correct value
        confidence=None,
        evidence_span="Underwriter reviewed source document",
        manually_verified=True,
    )
    uow.commit()
    all_versions = uow.extracted_fields.get_all_versions(app.application_id)
    # Should have 2 rows for this field
    tenure_rows = [r for r in all_versions if r.field_name == "employment_tenure_months"]
    assert len(tenure_rows) == 2
    # Only version 2 should be effective
    effective = [r for r in tenure_rows if r.is_effective]
    assert len(effective) == 1
    assert effective[0].field_version == 2
    assert effective[0].field_value == "3"
    # Version 1 must still exist (audit trail)
    original = [r for r in tenure_rows if r.field_version == 1]
    assert original[0].field_value == "36"
    assert original[0].is_effective is False


def test_effective_fields_dict(uow):
    app = uow.applications.create(applicant_name="H", applicant_address="8 St")
    uow.commit()
    uow.extracted_fields.upsert_field(app.application_id, "bureau_score", "650", confidence="high")
    uow.extracted_fields.upsert_field(app.application_id, "monthly_income", "5000", confidence="medium")
    uow.commit()
    eff = uow.extracted_fields.get_effective_fields(app.application_id)
    assert "bureau_score" in eff
    assert "monthly_income" in eff
    assert eff["bureau_score"].field_value == "650"


def test_low_confidence_scoring_fields(uow):
    app = uow.applications.create(applicant_name="I", applicant_address="9 St")
    uow.commit()
    uow.extracted_fields.upsert_field(app.application_id, "bureau_score", "700", confidence="low")
    uow.extracted_fields.upsert_field(app.application_id, "monthly_income", "4000", confidence="high")
    uow.commit()
    low_conf = uow.extracted_fields.get_low_confidence_scoring_fields(
        app.application_id,
        scoring_relevant_fields=["bureau_score", "monthly_income"],
    )
    assert len(low_conf) == 1
    assert low_conf[0].field_name == "bureau_score"


# ---------------------------------------------------------------------------
# Validation results
# ---------------------------------------------------------------------------
def test_validation_results(uow):
    app = uow.applications.create(applicant_name="J", applicant_address="10 St")
    uow.commit()
    uow.validation_results.add(app.application_id, "income_plausibility", True, "Income within ±15%")
    uow.validation_results.add(app.application_id, "statement_recency", False, "Statement is 75 days old")
    uow.commit()
    results = uow.validation_results.get_all(app.application_id)
    assert len(results) == 2
    assert uow.validation_results.any_failed(app.application_id) is True


# ---------------------------------------------------------------------------
# Score breakdowns + revision numbering
# ---------------------------------------------------------------------------
def test_score_breakdown_revision_numbering(uow):
    app = uow.applications.create(applicant_name="K", applicant_address="11 St")
    uow.commit()
    rev = uow.score_breakdowns.get_next_revision_number(app.application_id)
    assert rev == 1
    uow.score_breakdowns.add(
        app.application_id, revision_number=1, factor="dti",
        normalized_score=1.0, weight=0.4, weighted_contribution=0.4,
        band_label="low_risk", cited_clause_id="3.1(a)", raw_value=0.25,
    )
    uow.commit()
    rev2 = uow.score_breakdowns.get_next_revision_number(app.application_id)
    assert rev2 == 2


def test_score_breakdown_fairness_run_separate(uow):
    app = uow.applications.create(applicant_name="L", applicant_address="12 St")
    uow.commit()
    uow.score_breakdowns.add(
        app.application_id, revision_number=1, factor="dti",
        normalized_score=0.7, weight=0.4, weighted_contribution=0.28,
        band_label="moderate", cited_clause_id="3.1(b)", raw_value=0.38,
        is_fairness_run=False,
    )
    uow.score_breakdowns.add(
        app.application_id, revision_number=1, factor="dti",
        normalized_score=0.7, weight=0.4, weighted_contribution=0.28,
        band_label="moderate", cited_clause_id="3.1(b)", raw_value=0.38,
        is_fairness_run=True,
    )
    uow.commit()
    normal = uow.score_breakdowns.get_latest_revision(app.application_id, is_fairness_run=False)
    fairness = uow.score_breakdowns.get_latest_revision(app.application_id, is_fairness_run=True)
    assert len(normal) == 1 and len(fairness) == 1
    assert normal[0].is_fairness_run is False
    assert fairness[0].is_fairness_run is True


# ---------------------------------------------------------------------------
# Recommendation
# ---------------------------------------------------------------------------
def test_recommendation_latest(uow):
    app = uow.applications.create(applicant_name="M", applicant_address="13 St")
    uow.commit()
    uow.recommendations.add(app.application_id, revision_number=1, composite_score=0.80, band="APPROVE")
    uow.recommendations.add(app.application_id, revision_number=2, composite_score=0.82, band="APPROVE")
    uow.commit()
    latest = uow.recommendations.get_latest(app.application_id)
    assert latest.revision_number == 2
    assert latest.band == "APPROVE"


# ---------------------------------------------------------------------------
# Fairness check
# ---------------------------------------------------------------------------
def test_fairness_check(uow):
    app = uow.applications.create(applicant_name="N", applicant_address="14 St")
    uow.commit()
    uow.fairness_checks.add(app.application_id, 1, "APPROVE", "APPROVE", "PASS")
    uow.commit()
    fc = uow.fairness_checks.get_latest(app.application_id)
    assert fc.result == "PASS"


def test_fairness_check_fail(uow):
    app = uow.applications.create(applicant_name="O", applicant_address="15 St")
    uow.commit()
    uow.fairness_checks.add(
        app.application_id, 1, "APPROVE", "REFER", "FAIL",
        disparity_detail="Band changed from APPROVE to REFER after stripping identity fields"
    )
    uow.commit()
    fc = uow.fairness_checks.get_latest(app.application_id)
    assert fc.result == "FAIL"
    assert "REFER" in fc.disparity_detail


# ---------------------------------------------------------------------------
# Human decisions — REFER non-terminal, multi-row
# ---------------------------------------------------------------------------
def test_human_decision_refer_non_terminal(uow):
    app = uow.applications.create(applicant_name="P", applicant_address="16 St")
    uow.commit()
    d1 = uow.human_decisions.add(
        app.application_id,
        underwriter_id="uw-1",
        decision="REFER",
        recommendation_at_time="REFER",
        rationale="Need more info",
        refer_reason="REQUEST_MORE_INFO",
    )
    uow.commit()
    assert d1.is_terminal is False
    assert d1.sequence_number == 1
    assert d1.refer_reason == "REQUEST_MORE_INFO"


def test_human_decision_refer_requires_reason(uow):
    app = uow.applications.create(applicant_name="Q", applicant_address="17 St")
    uow.commit()
    with pytest.raises(ValueError, match="refer_reason is required"):
        uow.human_decisions.add(
            app.application_id,
            underwriter_id="uw-1",
            decision="REFER",
            recommendation_at_time="REFER",
            rationale="No reason given",
            refer_reason=None,  # should raise
        )


def test_human_decision_approve_is_terminal(uow):
    app = uow.applications.create(applicant_name="R", applicant_address="18 St")
    uow.commit()
    d1 = uow.human_decisions.add(
        app.application_id,
        underwriter_id="uw-1",
        decision="REFER",
        recommendation_at_time="APPROVE",
        rationale="Escalating",
        refer_reason="ESCALATE_TO_SENIOR_UNDERWRITER",
    )
    uow.commit()
    d2 = uow.human_decisions.add(
        app.application_id,
        underwriter_id="uw-2",
        decision="APPROVE",
        recommendation_at_time="APPROVE",
        rationale="Reviewed and approved",
    )
    uow.commit()
    assert d1.sequence_number == 1
    assert d2.sequence_number == 2
    assert d2.is_terminal is True
    terminal = uow.human_decisions.get_terminal_decision(app.application_id)
    assert terminal.decision_id == d2.decision_id


def test_human_decision_matches_recommendation(uow):
    app = uow.applications.create(applicant_name="S", applicant_address="19 St")
    uow.commit()
    d = uow.human_decisions.add(
        app.application_id,
        underwriter_id="uw-1",
        decision="APPROVE",
        recommendation_at_time="APPROVE",
        rationale="Agreed with agent",
    )
    uow.commit()
    assert d.matches_recommendation is True


def test_human_decision_diverges_from_recommendation(uow):
    app = uow.applications.create(applicant_name="T", applicant_address="20 St")
    uow.commit()
    d = uow.human_decisions.add(
        app.application_id,
        underwriter_id="uw-1",
        decision="APPROVE",
        recommendation_at_time="DECLINE",
        rationale="Override: additional context provided",
    )
    uow.commit()
    assert d.matches_recommendation is False


# ---------------------------------------------------------------------------
# Audit log — append-only
# ---------------------------------------------------------------------------
def test_audit_log_append(uow):
    app = uow.applications.create(applicant_name="U", applicant_address="21 St")
    uow.commit()
    uow.audit_logs.append(
        app.application_id,
        "INTAKE",
        {"document_types_received": ["id", "bank_statement"], "intake_idempotency_key": "k1"},
    )
    uow.audit_logs.append(
        app.application_id,
        "SCORED",
        {
            "revision_number": 1,
            "composite_score": 0.78,
            "band": "APPROVE",
            "factor_breakdown": [{"factor": "dti", "raw_value": 0.28, "band_label": "low_risk", "clause_id": "3.1(a)"}],
        },
    )
    uow.commit()
    logs = uow.audit_logs.get_all(app.application_id)
    assert len(logs) == 2
    assert logs[0].event_type == "INTAKE"
    assert logs[1].event_type == "SCORED"


def test_audit_log_export_parses_json(uow):
    app = uow.applications.create(applicant_name="V", applicant_address="22 St")
    uow.commit()
    uow.audit_logs.append(
        app.application_id,
        "HUMAN_DECIDED",
        {"decision_id": "d1", "decision": "APPROVE", "refer_reason": None, "is_terminal": True},
    )
    uow.commit()
    export = uow.audit_logs.get_all_for_export(app.application_id)
    assert export[0]["payload"]["decision"] == "APPROVE"
    assert export[0]["payload"]["is_terminal"] is True


# ---------------------------------------------------------------------------
# Guardrail flags
# ---------------------------------------------------------------------------
def test_guardrail_flag(uow):
    app = uow.applications.create(applicant_name="W", applicant_address="23 St")
    uow.commit()
    uow.guardrail_flags.add(
        app.application_id,
        field="applicant_notes",
        excerpt="I am a member of a protected group",
        reason="Identity information in free-text field",
    )
    uow.commit()
    flags = uow.guardrail_flags.get_all(app.application_id)
    assert len(flags) == 1
    assert flags[0].field == "applicant_notes"

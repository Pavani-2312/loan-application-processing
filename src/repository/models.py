"""
src/repository/models.py

SQLAlchemy ORM models for the loan application processing system.
Schema per docs/04_Data_Policy_Model.md §3.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# applications
# ---------------------------------------------------------------------------
class Application(Base):
    __tablename__ = "applications"

    application_id: Mapped[str] = mapped_column(Text, primary_key=True, default=_new_uuid)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    # Optimistic-locking counter — must match on write; incremented every status change.
    status_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    intake_idempotency_key: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    applicant_name: Mapped[str] = mapped_column(Text, nullable=False)
    applicant_address: Mapped[str] = mapped_column(Text, nullable=False)
    raw_payload_ref: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    extracted_fields: Mapped[list[ExtractedField]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    validation_results: Mapped[list[ValidationResult]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    score_breakdowns: Mapped[list[ScoreBreakdown]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    recommendations: Mapped[list[Recommendation]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    fairness_checks: Mapped[list[FairnessCheck]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    guardrail_flags: Mapped[list[GuardrailFlag]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    human_decisions: Mapped[list[HumanDecision]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# extracted_fields  (append-only versioned — never overwrite; see §3 note)
# ---------------------------------------------------------------------------
class ExtractedField(Base):
    __tablename__ = "extracted_fields"
    __table_args__ = (
        UniqueConstraint("application_id", "field_name", "field_version", name="uq_field_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[str] = mapped_column(Text, ForeignKey("applications.application_id"), nullable=False)
    field_name: Mapped[str] = mapped_column(Text, nullable=False)
    field_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # version 1: model-extracted; version 2+: human-corrected/confirmed
    field_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_document: Mapped[str | None] = mapped_column(Text, nullable=True)
    # high / medium / low for model extractions; NULL for human-entered versions
    confidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    # version 1: literal source text; version 2+: underwriter's reason/note
    evidence_span: Mapped[str | None] = mapped_column(Text, nullable=True)
    manually_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Exactly one is_effective=True row per (application_id, field_name) at any time.
    is_effective: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    application: Mapped[Application] = relationship(back_populates="extracted_fields")


# ---------------------------------------------------------------------------
# validation_results
# ---------------------------------------------------------------------------
class ValidationResult(Base):
    __tablename__ = "validation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[str] = mapped_column(Text, ForeignKey("applications.application_id"), nullable=False)
    check_name: Mapped[str] = mapped_column(Text, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)

    application: Mapped[Application] = relationship(back_populates="validation_results")


# ---------------------------------------------------------------------------
# score_breakdowns  (versioned; revision_number increments on re-score)
# ---------------------------------------------------------------------------
class ScoreBreakdown(Base):
    __tablename__ = "score_breakdowns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[str] = mapped_column(Text, ForeignKey("applications.application_id"), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    factor: Mapped[str] = mapped_column(Text, nullable=False)  # dti / credit_history / income_stability
    # For income_stability only: "tenure" or "variability" for sub-factor rows, None for the combined row.
    sub_factor: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    normalized_score: Mapped[float] = mapped_column(Float, nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    weighted_contribution: Mapped[float] = mapped_column(Float, nullable=False)
    band_label: Mapped[str] = mapped_column(Text, nullable=False)
    cited_clause_id: Mapped[str] = mapped_column(Text, nullable=False)
    is_fairness_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    application: Mapped[Application] = relationship(back_populates="score_breakdowns")


# ---------------------------------------------------------------------------
# recommendations  (versioned; same revision_number as score_breakdowns)
# ---------------------------------------------------------------------------
class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[str] = mapped_column(Text, ForeignKey("applications.application_id"), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    composite_score: Mapped[float] = mapped_column(Float, nullable=False)
    band: Mapped[str] = mapped_column(Text, nullable=False)  # APPROVE / REFER / DECLINE
    explanation_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    application: Mapped[Application] = relationship(back_populates="recommendations")


# ---------------------------------------------------------------------------
# fairness_checks  (versioned)
# ---------------------------------------------------------------------------
class FairnessCheck(Base):
    __tablename__ = "fairness_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[str] = mapped_column(Text, ForeignKey("applications.application_id"), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    original_band: Mapped[str] = mapped_column(Text, nullable=False)
    blind_band: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[str] = mapped_column(Text, nullable=False)  # PASS / FAIL
    disparity_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    application: Mapped[Application] = relationship(back_populates="fairness_checks")


# ---------------------------------------------------------------------------
# guardrail_flags
# ---------------------------------------------------------------------------
class GuardrailFlag(Base):
    __tablename__ = "guardrail_flags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[str] = mapped_column(Text, ForeignKey("applications.application_id"), nullable=False)
    field: Mapped[str] = mapped_column(Text, nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    application: Mapped[Application] = relationship(back_populates="guardrail_flags")


# ---------------------------------------------------------------------------
# human_decisions  (multiple rows per application — REFER is non-terminal)
# ---------------------------------------------------------------------------
class HumanDecision(Base):
    __tablename__ = "human_decisions"

    decision_id: Mapped[str] = mapped_column(Text, primary_key=True, default=_new_uuid)
    application_id: Mapped[str] = mapped_column(Text, ForeignKey("applications.application_id"), nullable=False)
    # Order of this decision event; starts at 1.
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # Not cryptographically verified in this build — see 01_Requirements.md §10 (L1)
    underwriter_id: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)  # APPROVE / REFER / DECLINE
    # Required (non-null) when decision = REFER
    refer_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # True only when decision ∈ {APPROVE, DECLINE}
    is_terminal: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # Snapshot of agent band at decision time (makes matches_recommendation meaningful across revisions)
    recommendation_at_time: Mapped[str] = mapped_column(Text, nullable=False)
    matches_recommendation: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    application: Mapped[Application] = relationship(back_populates="human_decisions")


# ---------------------------------------------------------------------------
# audit_log  (append-only; one row per state-changing event)
# ---------------------------------------------------------------------------
class AuditLog(Base):
    __tablename__ = "audit_log"

    log_id: Mapped[str] = mapped_column(Text, primary_key=True, default=_new_uuid)
    application_id: Mapped[str] = mapped_column(Text, ForeignKey("applications.application_id"), nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    # JSON with a defined schema per event_type — see 04_Data_Policy_Model.md §3
    event_payload: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    application: Mapped[Application] = relationship(back_populates="audit_logs")

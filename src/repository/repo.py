"""
src/repository/repo.py

Repository classes — the only layer that touches the DB.
All public methods are synchronous; optimistic locking is enforced on status writes.

Design decisions from docs/02_Architecture.md §6:
- No in-process threading.Lock (removed in review — WAL + optimistic locking suffice).
- Status updates carry current status_version; mismatched version raises ConcurrentModificationError.
- extracted_fields is append-only: corrections add a new row and flip is_effective rather than updating.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from src.repository.models import (
    Application,
    AuditLog,
    ExtractedField,
    FairnessCheck,
    GuardrailFlag,
    HumanDecision,
    Recommendation,
    ScoreBreakdown,
    ValidationResult,
)


class ConcurrentModificationError(Exception):
    """Raised when an optimistic-lock version mismatch is detected on status write."""


# ---------------------------------------------------------------------------
# ApplicationRepository
# ---------------------------------------------------------------------------
class ApplicationRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    # ---- Create ----

    def create(
        self,
        applicant_name: str,
        applicant_address: str,
        idempotency_key: str | None = None,
        raw_payload_ref: str | None = None,
    ) -> Application:
        """
        Create a new application in AWAITING_DOCUMENTS status.
        If idempotency_key is provided and already exists, returns the existing record (no-op).
        """
        if idempotency_key:
            existing = self._s.scalar(
                select(Application).where(Application.intake_idempotency_key == idempotency_key)
            )
            if existing:
                return existing

        app = Application(
            application_id=str(uuid.uuid4()),
            status="AWAITING_DOCUMENTS",
            status_version=1,
            intake_idempotency_key=idempotency_key,
            applicant_name=applicant_name,
            applicant_address=applicant_address,
            raw_payload_ref=raw_payload_ref,
        )
        self._s.add(app)
        self._s.flush()
        return app

    # ---- Read ----

    def get(self, application_id: str) -> Application | None:
        return self._s.get(Application, application_id)

    def get_by_status(self, *statuses: str) -> list[Application]:
        stmt = (
            select(Application)
            .where(Application.status.in_(statuses))
            .order_by(Application.submitted_at.asc())
        )
        return list(self._s.scalars(stmt).all())

    def list_all(self) -> list[Application]:
        return list(self._s.scalars(select(Application).order_by(Application.submitted_at.desc())).all())

    # ---- Status update (optimistic locking) ----

    def update_status(
        self,
        application_id: str,
        new_status: str,
        current_version: int,
    ) -> int:
        """
        Update status only if status_version == current_version.
        Returns the new version number on success.
        Raises ConcurrentModificationError on mismatch.
        """
        result = self._s.execute(
            update(Application)
            .where(
                Application.application_id == application_id,
                Application.status_version == current_version,
            )
            .values(
                status=new_status,
                status_version=current_version + 1,
            )
        )
        if result.rowcount == 0:
            raise ConcurrentModificationError(
                f"Status version mismatch for application {application_id}. "
                f"Expected version {current_version} but it has changed."
            )
        self._s.flush()
        return current_version + 1


# ---------------------------------------------------------------------------
# ExtractedFieldRepository  (append-only versioned)
# ---------------------------------------------------------------------------
class ExtractedFieldRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def upsert_field(
        self,
        application_id: str,
        field_name: str,
        field_value: str | None,
        source_document: str | None = None,
        confidence: str | None = None,
        evidence_span: str | None = None,
        manually_verified: bool = False,
    ) -> ExtractedField:
        """
        Add a new version of a field.
        Flips is_effective=False on all prior versions for this (application_id, field_name).
        New row gets is_effective=True.
        Never overwrites existing rows.
        """
        # Flip prior effective rows
        prior_rows = self._s.scalars(
            select(ExtractedField).where(
                ExtractedField.application_id == application_id,
                ExtractedField.field_name == field_name,
                ExtractedField.is_effective.is_(True),
            )
        ).all()

        next_version = 1
        for row in prior_rows:
            row.is_effective = False
            if row.field_version >= next_version:
                next_version = row.field_version + 1

        new_row = ExtractedField(
            application_id=application_id,
            field_name=field_name,
            field_version=next_version,
            field_value=field_value,
            source_document=source_document,
            confidence=confidence,
            evidence_span=evidence_span,
            manually_verified=manually_verified,
            is_effective=True,
        )
        self._s.add(new_row)
        self._s.flush()
        return new_row

    def get_effective_fields(self, application_id: str) -> dict[str, ExtractedField]:
        """Return a dict of {field_name: ExtractedField} for the effective row per field."""
        rows = self._s.scalars(
            select(ExtractedField).where(
                ExtractedField.application_id == application_id,
                ExtractedField.is_effective.is_(True),
            )
        ).all()
        return {row.field_name: row for row in rows}

    def get_all_versions(self, application_id: str) -> list[ExtractedField]:
        """Return all versions of all fields — for audit display."""
        return list(
            self._s.scalars(
                select(ExtractedField)
                .where(ExtractedField.application_id == application_id)
                .order_by(ExtractedField.field_name, ExtractedField.field_version)
            ).all()
        )

    def get_low_confidence_scoring_fields(
        self,
        application_id: str,
        scoring_relevant_fields: list[str],
    ) -> list[ExtractedField]:
        """Return effective fields that are scoring-relevant and have low confidence."""
        rows = self._s.scalars(
            select(ExtractedField).where(
                ExtractedField.application_id == application_id,
                ExtractedField.is_effective.is_(True),
                ExtractedField.field_name.in_(scoring_relevant_fields),
                ExtractedField.confidence == "low",
            )
        ).all()
        return list(rows)


# ---------------------------------------------------------------------------
# ValidationResultRepository
# ---------------------------------------------------------------------------
class ValidationResultRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(
        self,
        application_id: str,
        check_name: str,
        passed: bool,
        evidence: str | None = None,
    ) -> ValidationResult:
        row = ValidationResult(
            application_id=application_id,
            check_name=check_name,
            passed=passed,
            evidence=evidence,
        )
        self._s.add(row)
        self._s.flush()
        return row

    def get_all(self, application_id: str) -> list[ValidationResult]:
        return list(
            self._s.scalars(
                select(ValidationResult).where(ValidationResult.application_id == application_id)
            ).all()
        )

    def any_failed(self, application_id: str) -> bool:
        rows = self.get_all(application_id)
        return any(not r.passed for r in rows)


# ---------------------------------------------------------------------------
# ScoreBreakdownRepository
# ---------------------------------------------------------------------------
class ScoreBreakdownRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(
        self,
        application_id: str,
        revision_number: int,
        factor: str,
        normalized_score: float,
        weight: float,
        weighted_contribution: float,
        band_label: str,
        cited_clause_id: str,
        raw_value: float | None = None,
        sub_factor: str | None = None,
        is_fairness_run: bool = False,
    ) -> ScoreBreakdown:
        row = ScoreBreakdown(
            application_id=application_id,
            revision_number=revision_number,
            factor=factor,
            sub_factor=sub_factor,
            raw_value=raw_value,
            normalized_score=normalized_score,
            weight=weight,
            weighted_contribution=weighted_contribution,
            band_label=band_label,
            cited_clause_id=cited_clause_id,
            is_fairness_run=is_fairness_run,
        )
        self._s.add(row)
        self._s.flush()
        return row

    def get_latest_revision(self, application_id: str, is_fairness_run: bool = False) -> list[ScoreBreakdown]:
        """Get score breakdown rows for the highest revision_number."""
        max_rev_stmt = (
            select(ScoreBreakdown.revision_number)
            .where(
                ScoreBreakdown.application_id == application_id,
                ScoreBreakdown.is_fairness_run == is_fairness_run,
            )
            .order_by(ScoreBreakdown.revision_number.desc())
            .limit(1)
        )
        max_rev = self._s.scalar(max_rev_stmt)
        if max_rev is None:
            return []
        return list(
            self._s.scalars(
                select(ScoreBreakdown).where(
                    ScoreBreakdown.application_id == application_id,
                    ScoreBreakdown.revision_number == max_rev,
                    ScoreBreakdown.is_fairness_run == is_fairness_run,
                )
            ).all()
        )

    def get_next_revision_number(self, application_id: str) -> int:
        """Return the next revision number (max existing + 1, or 1 if none)."""
        max_rev = self._s.scalar(
            select(ScoreBreakdown.revision_number)
            .where(
                ScoreBreakdown.application_id == application_id,
                ScoreBreakdown.is_fairness_run.is_(False),
            )
            .order_by(ScoreBreakdown.revision_number.desc())
            .limit(1)
        )
        return (max_rev or 0) + 1


# ---------------------------------------------------------------------------
# RecommendationRepository
# ---------------------------------------------------------------------------
class RecommendationRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(
        self,
        application_id: str,
        revision_number: int,
        composite_score: float,
        band: str,
        explanation_text: str | None = None,
    ) -> Recommendation:
        row = Recommendation(
            application_id=application_id,
            revision_number=revision_number,
            composite_score=composite_score,
            band=band,
            explanation_text=explanation_text,
        )
        self._s.add(row)
        self._s.flush()
        return row

    def get_latest(self, application_id: str) -> Recommendation | None:
        return self._s.scalar(
            select(Recommendation)
            .where(Recommendation.application_id == application_id)
            .order_by(Recommendation.revision_number.desc())
            .limit(1)
        )

    def get_all(self, application_id: str) -> list[Recommendation]:
        return list(
            self._s.scalars(
                select(Recommendation)
                .where(Recommendation.application_id == application_id)
                .order_by(Recommendation.revision_number)
            ).all()
        )


# ---------------------------------------------------------------------------
# FairnessCheckRepository
# ---------------------------------------------------------------------------
class FairnessCheckRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(
        self,
        application_id: str,
        revision_number: int,
        original_band: str,
        blind_band: str,
        result: str,  # PASS / FAIL
        disparity_detail: str | None = None,
    ) -> FairnessCheck:
        row = FairnessCheck(
            application_id=application_id,
            revision_number=revision_number,
            original_band=original_band,
            blind_band=blind_band,
            result=result,
            disparity_detail=disparity_detail,
        )
        self._s.add(row)
        self._s.flush()
        return row

    def get_latest(self, application_id: str) -> FairnessCheck | None:
        return self._s.scalar(
            select(FairnessCheck)
            .where(FairnessCheck.application_id == application_id)
            .order_by(FairnessCheck.revision_number.desc())
            .limit(1)
        )


# ---------------------------------------------------------------------------
# GuardrailFlagRepository
# ---------------------------------------------------------------------------
class GuardrailFlagRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(
        self,
        application_id: str,
        field: str,
        excerpt: str,
        reason: str,
    ) -> GuardrailFlag:
        row = GuardrailFlag(
            application_id=application_id,
            field=field,
            excerpt=excerpt,
            reason=reason,
        )
        self._s.add(row)
        self._s.flush()
        return row

    def get_all(self, application_id: str) -> list[GuardrailFlag]:
        return list(
            self._s.scalars(
                select(GuardrailFlag).where(GuardrailFlag.application_id == application_id)
            ).all()
        )


# ---------------------------------------------------------------------------
# HumanDecisionRepository
# ---------------------------------------------------------------------------
class HumanDecisionRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(
        self,
        application_id: str,
        underwriter_id: str,
        decision: str,  # APPROVE / REFER / DECLINE
        recommendation_at_time: str,
        rationale: str,
        refer_reason: str | None = None,
    ) -> HumanDecision:
        """
        Add a new human decision event.
        is_terminal is derived: True if decision is APPROVE or DECLINE.
        sequence_number is auto-incremented from existing rows.
        """
        is_terminal = decision in ("APPROVE", "DECLINE")
        if decision == "REFER" and not refer_reason:
            raise ValueError("refer_reason is required when decision is REFER")

        # Next sequence number
        existing = self._s.scalars(
            select(HumanDecision).where(HumanDecision.application_id == application_id)
        ).all()
        seq = len(existing) + 1

        matches = decision == recommendation_at_time

        row = HumanDecision(
            decision_id=str(uuid.uuid4()),
            application_id=application_id,
            sequence_number=seq,
            underwriter_id=underwriter_id,
            decision=decision,
            refer_reason=refer_reason,
            is_terminal=is_terminal,
            recommendation_at_time=recommendation_at_time,
            matches_recommendation=matches,
            rationale=rationale,
        )
        self._s.add(row)
        self._s.flush()
        return row

    def get_all(self, application_id: str) -> list[HumanDecision]:
        return list(
            self._s.scalars(
                select(HumanDecision)
                .where(HumanDecision.application_id == application_id)
                .order_by(HumanDecision.sequence_number)
            ).all()
        )

    def get_terminal_decision(self, application_id: str) -> HumanDecision | None:
        return self._s.scalar(
            select(HumanDecision)
            .where(
                HumanDecision.application_id == application_id,
                HumanDecision.is_terminal.is_(True),
            )
            .order_by(HumanDecision.sequence_number.desc())
            .limit(1)
        )


# ---------------------------------------------------------------------------
# AuditLogRepository  (append-only)
# ---------------------------------------------------------------------------
class AuditLogRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def append(
        self,
        application_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> AuditLog:
        """
        Append a new audit event.  payload must conform to the schema in
        docs/04_Data_Policy_Model.md §3 (event_payload schema by event_type).
        """
        row = AuditLog(
            log_id=str(uuid.uuid4()),
            application_id=application_id,
            event_type=event_type,
            event_payload=json.dumps(payload, default=str),
        )
        self._s.add(row)
        self._s.flush()
        return row

    def get_all(self, application_id: str) -> list[AuditLog]:
        return list(
            self._s.scalars(
                select(AuditLog)
                .where(AuditLog.application_id == application_id)
                .order_by(AuditLog.occurred_at)
            ).all()
        )

    def get_all_for_export(self, application_id: str) -> list[dict[str, Any]]:
        """Return parsed audit events as dicts — for audit package generation."""
        rows = self.get_all(application_id)
        return [
            {
                "log_id": r.log_id,
                "event_type": r.event_type,
                "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
                "payload": json.loads(r.event_payload),
            }
            for r in rows
        ]

"""
src/repository/unit_of_work.py

UnitOfWork — wraps a single Session and exposes all repositories.
Use as a context manager:

    with UnitOfWork(session_factory) as uow:
        app = uow.applications.create(...)
        uow.commit()
"""
from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from src.repository.repo import (
    ApplicationRepository,
    AuditLogRepository,
    ExtractedFieldRepository,
    FairnessCheckRepository,
    GuardrailFlagRepository,
    HumanDecisionRepository,
    RecommendationRepository,
    ScoreBreakdownRepository,
    ValidationResultRepository,
)


class UnitOfWork:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._factory = session_factory
        self.session: Session | None = None

    def __enter__(self) -> "UnitOfWork":
        self.session = self._factory()
        self.applications = ApplicationRepository(self.session)
        self.extracted_fields = ExtractedFieldRepository(self.session)
        self.validation_results = ValidationResultRepository(self.session)
        self.score_breakdowns = ScoreBreakdownRepository(self.session)
        self.recommendations = RecommendationRepository(self.session)
        self.fairness_checks = FairnessCheckRepository(self.session)
        self.guardrail_flags = GuardrailFlagRepository(self.session)
        self.human_decisions = HumanDecisionRepository(self.session)
        self.audit_logs = AuditLogRepository(self.session)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type:
            self.rollback()
        if self.session:
            self.session.close()

    def commit(self) -> None:
        if self.session:
            self.session.commit()

    def rollback(self) -> None:
        if self.session:
            self.session.rollback()

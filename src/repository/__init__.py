"""src/repository/__init__.py — public API for the repository layer."""
from src.repository.database import create_db_engine, get_session_factory, init_db
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
from src.repository.repo import (
    ApplicationRepository,
    AuditLogRepository,
    ConcurrentModificationError,
    ExtractedFieldRepository,
    FairnessCheckRepository,
    GuardrailFlagRepository,
    HumanDecisionRepository,
    RecommendationRepository,
    ScoreBreakdownRepository,
    ValidationResultRepository,
)
from src.repository.unit_of_work import UnitOfWork

__all__ = [
    # DB setup
    "create_db_engine",
    "get_session_factory",
    "init_db",
    # Models
    "Application",
    "AuditLog",
    "ExtractedField",
    "FairnessCheck",
    "GuardrailFlag",
    "HumanDecision",
    "Recommendation",
    "ScoreBreakdown",
    "ValidationResult",
    # Repos
    "ApplicationRepository",
    "AuditLogRepository",
    "ConcurrentModificationError",
    "ExtractedFieldRepository",
    "FairnessCheckRepository",
    "GuardrailFlagRepository",
    "HumanDecisionRepository",
    "RecommendationRepository",
    "ScoreBreakdownRepository",
    "ValidationResultRepository",
    # UoW
    "UnitOfWork",
]

"""
src/agent/schemas.py

Pydantic v2 schemas for all LLM structured outputs.
These are the shapes Claude must return from each node's extraction/reasoning calls.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# IntakeNode — document field extraction
# ---------------------------------------------------------------------------

class ExtractedNumericField(BaseModel):
    """A single numeric/date field extracted from a document."""
    value: str | None = Field(description="Extracted value as a string (preserves original format)")
    confidence: Literal["high", "medium", "low"] = Field(
        description="Model's confidence that this value is correct and correctly read"
    )
    evidence_span: str = Field(
        description="The exact literal text from the source document this value was read from"
    )
    source_document: str = Field(
        description="Which document type this was extracted from (id/payslip/bank_statement)"
    )


class DocumentExtractionResult(BaseModel):
    """
    All structured fields extracted from the three application documents.
    Every numeric/date field includes confidence + evidence_span.
    """
    # --- From Government ID ---
    applicant_name_on_id: ExtractedNumericField = Field(description="Full name on ID document")
    id_expiry_date: ExtractedNumericField = Field(description="Expiry date on ID, as written")

    # --- From Income Proof (payslip/employer letter) ---
    applicant_name_on_payslip: ExtractedNumericField = Field(description="Name on payslip/employer letter")
    employer_name: ExtractedNumericField = Field(description="Employer name")
    stated_monthly_income: ExtractedNumericField = Field(description="Stated monthly income amount (numeric)")
    employment_tenure_months: ExtractedNumericField = Field(
        description="Employment tenure with current employer in months (numeric)"
    )

    # --- From Bank Statement ---
    applicant_name_on_statement: ExtractedNumericField = Field(description="Name on bank statement")
    statement_period_end_date: ExtractedNumericField = Field(description="End date of the bank statement period, as written")
    average_monthly_deposits: ExtractedNumericField = Field(description="Average monthly deposit amount (numeric)")
    income_variability_pct: ExtractedNumericField = Field(
        description="Income variability percentage: stddev / mean of monthly deposits * 100 (numeric)"
    )
    total_monthly_obligations: ExtractedNumericField = Field(
        description="Total recurring monthly debt obligations visible in the statement (numeric)"
    )
    bureau_score: ExtractedNumericField = Field(
        description="Credit bureau score if provided in documents, else null"
    )

    # --- Document presence flags ---
    id_document_present: bool = Field(description="True if a valid government ID document was found")
    payslip_present: bool = Field(description="True if a payslip or employer letter was found")
    bank_statement_present: bool = Field(description="True if a bank statement was found")


# ---------------------------------------------------------------------------
# ValidationNode — consistency check
# ---------------------------------------------------------------------------

class ConsistencyCheckItem(BaseModel):
    check_name: Literal["name_match", "id_validity", "income_plausibility", "statement_recency"]
    passed: bool
    evidence: str = Field(description="Brief evidence for the pass/fail judgment")


class ConsistencyCheckResult(BaseModel):
    checks: list[ConsistencyCheckItem]
    overall_consistent: bool = Field(
        description="True only if ALL individual checks passed"
    )


# ---------------------------------------------------------------------------
# GuardrailNode — adversarial content detection
# ---------------------------------------------------------------------------

class GuardrailFlag(BaseModel):
    field: str = Field(description="Which free-text field contained the suspicious content")
    excerpt: str = Field(description="The specific text excerpt that triggered the flag")
    reason: str = Field(description="Why this appears to be an instruction injection attempt")


class GuardrailCheckResult(BaseModel):
    flags: list[GuardrailFlag] = Field(
        description="List of detected adversarial content items. Empty list if none found."
    )
    adversarial_content_detected: bool = Field(
        description="True if any instruction-injection attempts were detected"
    )


# ---------------------------------------------------------------------------
# RecommendationNode — natural language explanation
# ---------------------------------------------------------------------------

class RecommendationExplanation(BaseModel):
    explanation: str = Field(
        description=(
            "A professional, underwriter-readable explanation of the recommendation. "
            "Must cite specific factors, their values, the band they fell into, and the "
            "relevant policy clause for each (e.g., 'DTI of 0.28 falls in the low-risk band "
            "per Clause 3.1(a)...'). 2-4 sentences."
        )
    )

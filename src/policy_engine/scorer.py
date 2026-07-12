"""
src/policy_engine/scorer.py

Deterministic policy scoring engine.
100% pure Python — no LLM calls, no I/O.
Inputs: structured numeric fields + loaded policy_config.yaml dict.
Output: ScoringResult with full per-factor breakdown + composite score + recommendation band.

Boundary rule (from docs/03_Functional_Specification.md §2.1):
  max_asc : check entries in listed order; first entry where value <= max wins.
  min_desc: check entries in listed order; first entry where value >= min wins.
  A value exactly on a stated boundary resolves to the BETTER-scoring side.

Income stability (from docs/03_Functional_Specification.md §2.2):
  combined = min(tenure_subscore, variability_subscore)
  The weaker sub-score governs. Both sub-scores stored; binding clause = clause of lower sub-score.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Input / Output types
# ---------------------------------------------------------------------------

@dataclass
class ScoringInputs:
    """
    All numeric fields needed for deterministic scoring.
    Floats only — caller is responsible for parsing from extracted_fields text values.
    """
    dti: float                          # monthly_debt / monthly_income
    bureau_score: float                  # credit bureau score (numeric)
    employment_tenure_months: float      # months with current employer
    income_variability_pct: float        # deposit variability % across statement period


@dataclass
class SubFactorBreakdown:
    """One row in the score breakdown (factor or sub-factor)."""
    factor: str                  # dti / credit_history / income_stability
    sub_factor: str | None       # tenure / variability (income_stability only); None otherwise
    raw_value: float
    normalized_score: float
    weight: float                # factor-level weight; sub-factors carry the parent's weight for display
    weighted_contribution: float
    band_label: str
    cited_clause_id: str


@dataclass
class ScoringResult:
    """Full output of the scoring engine."""
    inputs: ScoringInputs
    dti_breakdown: SubFactorBreakdown
    credit_breakdown: SubFactorBreakdown
    income_tenure_breakdown: SubFactorBreakdown     # sub-factor row
    income_variability_breakdown: SubFactorBreakdown  # sub-factor row
    income_combined_breakdown: SubFactorBreakdown    # the factor row (combined = min of two)
    composite_score: float
    recommendation_band: str            # APPROVE / REFER / DECLINE
    # All five breakdowns in display order
    all_breakdowns: list[SubFactorBreakdown] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.all_breakdowns:
            self.all_breakdowns = [
                self.dti_breakdown,
                self.credit_breakdown,
                self.income_tenure_breakdown,
                self.income_variability_breakdown,
                self.income_combined_breakdown,
            ]


# ---------------------------------------------------------------------------
# PolicyConfigError — raised when the config is internally inconsistent
# ---------------------------------------------------------------------------

class PolicyConfigError(Exception):
    """
    Raised when a clause_id in policy_config.yaml has no matching document in Chroma,
    or the config structure is invalid. Causes POLICY_CONFIG_ERROR status.
    """


# ---------------------------------------------------------------------------
# Band evaluation helpers
# ---------------------------------------------------------------------------

def _evaluate_band_max_asc(value: float, entries: list[dict[str, Any]]) -> tuple[float, str, str]:
    """
    direction: max_asc — lower raw value is better.
    Entries listed ascending by max. First entry where value <= max wins.
    Returns (normalized_score, band_label, clause_id).
    """
    for entry in entries:
        max_val = entry.get("max")
        if max_val is None or value <= max_val:
            return float(entry["score"]), _band_label_for_score(float(entry["score"])), entry["clause"]
    # Should be unreachable if the last entry has max=null
    raise PolicyConfigError(f"No matching band for value {value} in max_asc band list: {entries}")


def _evaluate_band_min_desc(value: float, entries: list[dict[str, Any]]) -> tuple[float, str, str]:
    """
    direction: min_desc — higher raw value is better.
    Entries listed descending by min. First entry where value >= min wins.
    Returns (normalized_score, band_label, clause_id).
    """
    for entry in entries:
        min_val = entry.get("min")
        if min_val is None or value >= min_val:
            return float(entry["score"]), _band_label_for_score(float(entry["score"])), entry["clause"]
    raise PolicyConfigError(f"No matching band for value {value} in min_desc band list: {entries}")


def _evaluate_band(value: float, band_config: dict[str, Any]) -> tuple[float, str, str]:
    """Dispatch to the correct evaluator based on direction."""
    direction = band_config["direction"]
    entries = band_config["entries"]
    if direction == "max_asc":
        return _evaluate_band_max_asc(value, entries)
    elif direction == "min_desc":
        return _evaluate_band_min_desc(value, entries)
    else:
        raise PolicyConfigError(f"Unknown band direction: {direction!r}")


def _band_label_for_score(score: float) -> str:
    """Map normalized score to a human-readable band label."""
    if score >= 1.0:
        return "low_risk"
    elif score >= 0.7:
        return "moderate"
    elif score >= 0.4:
        return "elevated"
    else:
        return "high_risk"


def _recommendation_band(composite: float, config: dict[str, Any]) -> str:
    """
    Map composite score to APPROVE / REFER / DECLINE.
    min_desc-style: composite >= approve_min → APPROVE;
                    composite >= refer_min  → REFER;
                    else                   → DECLINE.
    Boundary rule: composite == 0.75 → APPROVE; composite == 0.65 → REFER.
    """
    bands = config["recommendation_bands"]
    approve_min: float = float(bands["approve_min"])
    refer_min: float = float(bands["refer_min"])
    if composite >= approve_min:
        return "APPROVE"
    elif composite >= refer_min:
        return "REFER"
    else:
        return "DECLINE"


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------

def score_application(
    inputs: ScoringInputs,
    policy_config: dict[str, Any],
) -> ScoringResult:
    """
    Score a single application deterministically from structured inputs + policy config.
    Raises PolicyConfigError if the config is structurally invalid.
    Does NOT read from or write to any database; caller handles persistence.
    """
    bands = policy_config["bands"]
    weights = policy_config["weights"]

    dti_weight = float(weights["dti"])
    credit_weight = float(weights["credit_history"])
    income_weight = float(weights["income_stability"])

    # ---- DTI ----
    dti_score, dti_band, dti_clause = _evaluate_band(inputs.dti, bands["dti"])
    dti_breakdown = SubFactorBreakdown(
        factor="dti",
        sub_factor=None,
        raw_value=inputs.dti,
        normalized_score=dti_score,
        weight=dti_weight,
        weighted_contribution=round(dti_score * dti_weight, 6),
        band_label=dti_band,
        cited_clause_id=dti_clause,
    )

    # ---- Credit history ----
    credit_score, credit_band, credit_clause = _evaluate_band(
        inputs.bureau_score, bands["credit_history"]
    )
    credit_breakdown = SubFactorBreakdown(
        factor="credit_history",
        sub_factor=None,
        raw_value=inputs.bureau_score,
        normalized_score=credit_score,
        weight=credit_weight,
        weighted_contribution=round(credit_score * credit_weight, 6),
        band_label=credit_band,
        cited_clause_id=credit_clause,
    )

    # ---- Income stability — two sub-factors ----
    tenure_score, tenure_band, tenure_clause = _evaluate_band(
        inputs.employment_tenure_months,
        bands["income_stability_tenure_months"],
    )
    variability_score, variability_band, variability_clause = _evaluate_band(
        inputs.income_variability_pct,
        bands["income_stability_variability_pct"],
    )

    income_tenure_breakdown = SubFactorBreakdown(
        factor="income_stability",
        sub_factor="tenure",
        raw_value=inputs.employment_tenure_months,
        normalized_score=tenure_score,
        weight=income_weight,
        weighted_contribution=round(tenure_score * income_weight, 6),
        band_label=tenure_band,
        cited_clause_id=tenure_clause,
    )
    income_variability_breakdown = SubFactorBreakdown(
        factor="income_stability",
        sub_factor="variability",
        raw_value=inputs.income_variability_pct,
        normalized_score=variability_score,
        weight=income_weight,
        weighted_contribution=round(variability_score * income_weight, 6),
        band_label=variability_band,
        cited_clause_id=variability_clause,
    )

    # Combined = min of two sub-scores (weakest-link rule, FR spec §2.2)
    if tenure_score <= variability_score:
        combined_score = tenure_score
        combined_band = tenure_band
        # The binding constraint's clause(s)
        if tenure_score == variability_score:
            # Tied — cite both
            combined_clause = f"{tenure_clause},{variability_clause}"
        else:
            combined_clause = tenure_clause
    else:
        combined_score = variability_score
        combined_band = variability_band
        combined_clause = variability_clause

    income_combined_breakdown = SubFactorBreakdown(
        factor="income_stability",
        sub_factor=None,  # The combined factor-level row
        raw_value=min(inputs.employment_tenure_months, inputs.income_variability_pct),  # for display
        normalized_score=combined_score,
        weight=income_weight,
        weighted_contribution=round(combined_score * income_weight, 6),
        band_label=combined_band,
        cited_clause_id=combined_clause,
    )

    # ---- Composite score ----
    composite = round(
        dti_breakdown.weighted_contribution
        + credit_breakdown.weighted_contribution
        + income_combined_breakdown.weighted_contribution,
        6,
    )
    # Clamp to [0, 1] to absorb floating-point edge cases
    composite = max(0.0, min(1.0, composite))

    band = _recommendation_band(composite, policy_config)

    return ScoringResult(
        inputs=inputs,
        dti_breakdown=dti_breakdown,
        credit_breakdown=credit_breakdown,
        income_tenure_breakdown=income_tenure_breakdown,
        income_variability_breakdown=income_variability_breakdown,
        income_combined_breakdown=income_combined_breakdown,
        composite_score=composite,
        recommendation_band=band,
    )

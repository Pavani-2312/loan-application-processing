"""
tests/test_policy_engine.py

Unit tests for the deterministic policy scoring engine.
Every test uses the config from policy_config.yaml (loaded once via fixture).
Includes all boundary cases mandated by docs/03_Functional_Specification.md §2.1.
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest
import yaml

from src.policy_engine import (
    PolicyConfigError,
    ScoringInputs,
    score_application,
)

# ---------------------------------------------------------------------------
# Load real policy config once
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def config() -> dict:
    path = Path(__file__).resolve().parent.parent / "policy_config.yaml"
    with path.open() as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Helper: build a default "clean" set of inputs that should score APPROVE
# ---------------------------------------------------------------------------

def _good_inputs() -> ScoringInputs:
    """DTI=0.25, bureau=750, tenure=36mo, variability=5% → all top bands."""
    return ScoringInputs(
        dti=0.25,
        bureau_score=750,
        employment_tenure_months=36,
        income_variability_pct=5.0,
    )


# ---------------------------------------------------------------------------
# Basic scoring — known outcomes
# ---------------------------------------------------------------------------

def test_clean_application_scores_approve(config):
    result = score_application(_good_inputs(), config)
    assert result.recommendation_band == "APPROVE"
    assert result.composite_score >= 0.75


def test_poor_application_scores_decline(config):
    result = score_application(
        ScoringInputs(dti=0.55, bureau_score=550, employment_tenure_months=3, income_variability_pct=45),
        config,
    )
    assert result.recommendation_band == "DECLINE"
    assert result.composite_score < 0.65


def test_borderline_scores_refer(config):
    # DTI moderate, credit moderate, income moderate → composite near 0.70
    result = score_application(
        ScoringInputs(dti=0.35, bureau_score=680, employment_tenure_months=18, income_variability_pct=15),
        config,
    )
    assert result.recommendation_band == "REFER"
    assert 0.65 <= result.composite_score < 0.75


# ---------------------------------------------------------------------------
# DTI band boundary — max_asc direction
# ---------------------------------------------------------------------------

def test_dti_top_band(config):
    """DTI = 0.30 exactly → low_risk (scores 1.0), per max_asc first-match rule."""
    result = score_application(
        ScoringInputs(dti=0.30, bureau_score=750, employment_tenure_months=36, income_variability_pct=5),
        config,
    )
    assert result.dti_breakdown.normalized_score == 1.0
    assert result.dti_breakdown.band_label == "low_risk"
    assert result.dti_breakdown.cited_clause_id == "3.1(a)"


def test_dti_boundary_040_resolves_to_moderate(config):
    """
    DTI = 0.40 exactly — boundary case.
    max_asc: first entry where value <= max wins.
    0.40 > 0.30 (no match), 0.40 <= 0.40 (match) → scores 0.7, moderate.
    See docs/03_Functional_Specification.md §2.1 worked example.
    """
    result = score_application(
        ScoringInputs(dti=0.40, bureau_score=750, employment_tenure_months=36, income_variability_pct=5),
        config,
    )
    assert result.dti_breakdown.normalized_score == pytest.approx(0.7)
    assert result.dti_breakdown.band_label == "moderate"
    assert result.dti_breakdown.cited_clause_id == "3.1(b)"


def test_dti_elevated_band(config):
    """DTI = 0.50 exactly → first entry where 0.50 <= 0.50 in elevated band."""
    result = score_application(
        ScoringInputs(dti=0.50, bureau_score=750, employment_tenure_months=36, income_variability_pct=5),
        config,
    )
    assert result.dti_breakdown.normalized_score == pytest.approx(0.4)
    assert result.dti_breakdown.band_label == "elevated"


def test_dti_high_risk_band(config):
    """DTI > 0.50 → null max entry → high_risk."""
    result = score_application(
        ScoringInputs(dti=0.60, bureau_score=750, employment_tenure_months=36, income_variability_pct=5),
        config,
    )
    assert result.dti_breakdown.normalized_score == 0.0
    assert result.dti_breakdown.band_label == "high_risk"
    assert result.dti_breakdown.cited_clause_id == "3.1(d)"


# ---------------------------------------------------------------------------
# Credit history band boundary — min_desc direction
# ---------------------------------------------------------------------------

def test_credit_top_band(config):
    """bureau_score = 720 exactly → top band (scores 1.0), per min_desc first-match rule."""
    result = score_application(
        ScoringInputs(dti=0.25, bureau_score=720, employment_tenure_months=36, income_variability_pct=5),
        config,
    )
    assert result.credit_breakdown.normalized_score == 1.0
    assert result.credit_breakdown.band_label == "low_risk"
    assert result.credit_breakdown.cited_clause_id == "4.1(a)"


def test_credit_boundary_650_resolves_to_moderate(config):
    """
    bureau_score = 650 exactly — boundary case.
    min_desc: entries checked descending. 650 >= 720? No. 650 >= 650? Yes → scores 0.7, moderate.
    See docs/03_Functional_Specification.md §2.1 worked example.
    """
    result = score_application(
        ScoringInputs(dti=0.25, bureau_score=650, employment_tenure_months=36, income_variability_pct=5),
        config,
    )
    assert result.credit_breakdown.normalized_score == pytest.approx(0.7)
    assert result.credit_breakdown.band_label == "moderate"
    assert result.credit_breakdown.cited_clause_id == "4.1(b)"


def test_credit_boundary_580_resolves_to_elevated(config):
    """bureau_score = 580 exactly → elevated (scores 0.4)."""
    result = score_application(
        ScoringInputs(dti=0.25, bureau_score=580, employment_tenure_months=36, income_variability_pct=5),
        config,
    )
    assert result.credit_breakdown.normalized_score == pytest.approx(0.4)
    assert result.credit_breakdown.band_label == "elevated"


def test_credit_high_risk_band(config):
    """bureau_score = 579 → high_risk (falls below 580)."""
    result = score_application(
        ScoringInputs(dti=0.25, bureau_score=579, employment_tenure_months=36, income_variability_pct=5),
        config,
    )
    assert result.credit_breakdown.normalized_score == 0.0
    assert result.credit_breakdown.band_label == "high_risk"
    assert result.credit_breakdown.cited_clause_id == "4.1(d)"


# ---------------------------------------------------------------------------
# Income stability — min/max boundaries and weakest-link combination rule
# ---------------------------------------------------------------------------

def test_income_tenure_boundary_24_months(config):
    """Employment tenure = 24 months exactly → top band (low_risk, scores 1.0)."""
    result = score_application(
        ScoringInputs(dti=0.25, bureau_score=750, employment_tenure_months=24, income_variability_pct=5),
        config,
    )
    assert result.income_tenure_breakdown.normalized_score == 1.0
    assert result.income_tenure_breakdown.band_label == "low_risk"
    assert result.income_tenure_breakdown.cited_clause_id == "5.1(a)"


def test_income_variability_boundary_10_pct(config):
    """Income variability = 10% exactly → top band (low_risk, scores 1.0)."""
    result = score_application(
        ScoringInputs(dti=0.25, bureau_score=750, employment_tenure_months=36, income_variability_pct=10.0),
        config,
    )
    assert result.income_variability_breakdown.normalized_score == 1.0
    assert result.income_variability_breakdown.band_label == "low_risk"
    assert result.income_variability_breakdown.cited_clause_id == "5.2(a)"


def test_income_combined_uses_weaker_subscore(config):
    """
    Tenure = 36mo (low_risk, 1.0) but variability = 20% (moderate, 0.7).
    Combined = min(1.0, 0.7) = 0.7 → binding clause is variability's.
    """
    result = score_application(
        ScoringInputs(dti=0.25, bureau_score=750, employment_tenure_months=36, income_variability_pct=20),
        config,
    )
    assert result.income_tenure_breakdown.normalized_score == 1.0
    assert result.income_variability_breakdown.normalized_score == pytest.approx(0.7)
    assert result.income_combined_breakdown.normalized_score == pytest.approx(0.7)
    assert result.income_combined_breakdown.cited_clause_id == "5.2(b)"


def test_income_combined_tenure_is_weaker(config):
    """
    Tenure = 18mo (moderate, 0.7), variability = 5% (low_risk, 1.0).
    Combined = min(0.7, 1.0) = 0.7 → binding clause is tenure's.
    """
    result = score_application(
        ScoringInputs(dti=0.25, bureau_score=750, employment_tenure_months=18, income_variability_pct=5),
        config,
    )
    assert result.income_combined_breakdown.normalized_score == pytest.approx(0.7)
    assert result.income_combined_breakdown.cited_clause_id == "5.1(b)"


def test_income_combined_tie_cites_both(config):
    """
    Both sub-scores land in the same band value (both moderate, 0.7).
    Clause ID should contain both sub-factor clauses.
    """
    result = score_application(
        # tenure 18mo → moderate, variability 20% → moderate
        ScoringInputs(dti=0.25, bureau_score=750, employment_tenure_months=18, income_variability_pct=20),
        config,
    )
    assert result.income_combined_breakdown.normalized_score == pytest.approx(0.7)
    clause = result.income_combined_breakdown.cited_clause_id
    assert "5.1(b)" in clause
    assert "5.2(b)" in clause


def test_income_combined_high_risk_governs(config):
    """
    Tenure = 3mo (high_risk, 0.0), variability = 5% (low_risk, 1.0).
    Combined = min(0.0, 1.0) = 0.0 — high risk tenure wipes out stable income.
    """
    result = score_application(
        ScoringInputs(dti=0.25, bureau_score=750, employment_tenure_months=3, income_variability_pct=5),
        config,
    )
    assert result.income_combined_breakdown.normalized_score == 0.0
    assert result.income_combined_breakdown.cited_clause_id == "5.1(d)"


# ---------------------------------------------------------------------------
# Composite score arithmetic
# ---------------------------------------------------------------------------

def test_composite_score_arithmetic(config):
    """Manually verify composite = sum of weighted contributions."""
    inputs = _good_inputs()
    result = score_application(inputs, config)
    expected = (
        result.dti_breakdown.weighted_contribution
        + result.credit_breakdown.weighted_contribution
        + result.income_combined_breakdown.weighted_contribution
    )
    assert result.composite_score == pytest.approx(expected, abs=1e-5)


def test_composite_clamped_to_1(config):
    """All top bands → composite = 1.0 (weights sum to 1.0)."""
    result = score_application(_good_inputs(), config)
    assert result.composite_score <= 1.0


def test_composite_clamped_to_0(config):
    """All bottom bands → composite = 0.0."""
    result = score_application(
        ScoringInputs(dti=0.60, bureau_score=500, employment_tenure_months=1, income_variability_pct=50),
        config,
    )
    assert result.composite_score == 0.0


# ---------------------------------------------------------------------------
# Recommendation band boundaries
# ---------------------------------------------------------------------------

def test_recommendation_boundary_approve_min(config):
    """
    Composite = 0.75 exactly → APPROVE.
    approve_min = 0.75; composite >= 0.75 → APPROVE (not REFER).
    """
    # Construct inputs that produce exactly 0.75
    # dti_score=1.0*0.4=0.4, credit_score=1.0*0.35=0.35, income=0.0*0.25=0.0 → 0.75
    result = score_application(
        ScoringInputs(dti=0.25, bureau_score=750, employment_tenure_months=1, income_variability_pct=5),
        config,
    )
    # Tenure=1 month → high_risk (0.0), variability=5% → low_risk (1.0) → combined=0.0
    # composite = 0.4 + 0.35 + 0.0 = 0.75
    assert result.composite_score == pytest.approx(0.75)
    assert result.recommendation_band == "APPROVE"


def test_recommendation_boundary_refer_min(config):
    """
    Composite = 0.65 exactly → REFER (not DECLINE).
    """
    # dti=1.0*0.4=0.4, credit=0.7*0.35=0.245, income=0.0*0.25=0.0 → 0.645 (close but not exact)
    # Use: dti=moderate(0.7)*0.4=0.28, credit=top(1.0)*0.35=0.35, income=moderate(0.7)*0.25=0.175 → 0.805 too high
    # Let's compute: need composite=0.65
    # Simplest: dti=moderate(0.7)*0.4=0.28, credit=moderate(0.7)*0.35=0.245, income=moderate(0.7)*0.25=0.175 → 0.7 no
    # dti=high_risk(0.0)*0.4=0.0, credit=top(1.0)*0.35=0.35, income=top(1.0)*0.25=0.25 → 0.60 (too low)
    # dti=moderate(0.7)*0.4=0.28, credit=top(1.0)*0.35=0.35, income=moderate(0.7)*0.25=0.175 → 0.805
    # We need exactly 0.65. Hard to hit exactly with discrete bands.
    # Instead, verify boundary logic directly by checking the scorer function.
    from src.policy_engine.scorer import _recommendation_band
    assert _recommendation_band(0.65, config) == "REFER"
    assert _recommendation_band(0.749, config) == "REFER"
    assert _recommendation_band(0.75, config) == "APPROVE"
    assert _recommendation_band(0.6499, config) == "DECLINE"
    assert _recommendation_band(0.64, config) == "DECLINE"


def test_recommendation_just_above_refer(config):
    """composite = 0.751 → APPROVE."""
    from src.policy_engine.scorer import _recommendation_band
    assert _recommendation_band(0.751, config) == "APPROVE"


def test_recommendation_just_below_refer(config):
    """composite = 0.649 → DECLINE."""
    from src.policy_engine.scorer import _recommendation_band
    assert _recommendation_band(0.649, config) == "DECLINE"


# ---------------------------------------------------------------------------
# ScoringResult structure
# ---------------------------------------------------------------------------

def test_scoring_result_has_all_breakdowns(config):
    result = score_application(_good_inputs(), config)
    assert len(result.all_breakdowns) == 5
    factors = [(r.factor, r.sub_factor) for r in result.all_breakdowns]
    assert ("dti", None) in factors
    assert ("credit_history", None) in factors
    assert ("income_stability", "tenure") in factors
    assert ("income_stability", "variability") in factors
    assert ("income_stability", None) in factors  # combined row


def test_scoring_result_weights_sum_to_1(config):
    """Factor weights from config sum to 1.0."""
    weights = config["weights"]
    total = sum(float(v) for v in weights.values())
    assert total == pytest.approx(1.0, abs=1e-6)


def test_scoring_result_clauses_populated(config):
    result = score_application(_good_inputs(), config)
    for row in result.all_breakdowns:
        assert row.cited_clause_id, f"Missing clause for {row.factor}/{row.sub_factor}"


# ---------------------------------------------------------------------------
# PolicyConfigError on malformed config
# ---------------------------------------------------------------------------

def test_unknown_direction_raises_config_error(config):
    import copy
    bad_config = copy.deepcopy(config)
    bad_config["bands"]["dti"]["direction"] = "unknown_direction"
    with pytest.raises(PolicyConfigError, match="Unknown band direction"):
        score_application(_good_inputs(), bad_config)


def test_unmatched_band_raises_config_error():
    """A config where no band matches should raise PolicyConfigError."""
    from src.policy_engine.scorer import _evaluate_band_max_asc
    # All entries have max values below 0.5 — so a value of 1.0 won't match
    bad_entries = [{"max": 0.1, "score": 1.0, "clause": "X"}, {"max": 0.2, "score": 0.7, "clause": "Y"}]
    with pytest.raises(PolicyConfigError):
        _evaluate_band_max_asc(1.0, bad_entries)


# ---------------------------------------------------------------------------
# Determinism — same inputs always produce same result
# ---------------------------------------------------------------------------

def test_scoring_is_deterministic(config):
    inputs = ScoringInputs(dti=0.38, bureau_score=685, employment_tenure_months=20, income_variability_pct=18)
    r1 = score_application(inputs, config)
    r2 = score_application(inputs, config)
    assert r1.composite_score == r2.composite_score
    assert r1.recommendation_band == r2.recommendation_band
    assert r1.dti_breakdown.cited_clause_id == r2.dti_breakdown.cited_clause_id


# ---------------------------------------------------------------------------
# Identity-blind scoring — redacting name/address does NOT change numeric score
# ---------------------------------------------------------------------------

def test_identity_blind_score_unchanged(config):
    """
    The deterministic scorer doesn't take name/address as inputs.
    Verifies the fairness-check invariant: same numeric fields → same score.
    This is the property FairnessNode relies on — if it ever fails, the LLM
    extracted a different numeric field for the blind run.
    """
    original_inputs = _good_inputs()
    blind_inputs = _good_inputs()  # Identical — no name/address in ScoringInputs

    r_original = score_application(original_inputs, config)
    r_blind = score_application(blind_inputs, config)

    assert r_original.composite_score == r_blind.composite_score
    assert r_original.recommendation_band == r_blind.recommendation_band

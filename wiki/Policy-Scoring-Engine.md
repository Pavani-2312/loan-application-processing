# Policy Scoring Engine

The scoring engine (`src/policy_engine/scorer.py`) is 100% deterministic Python. No LLM calls, no I/O. Given the same inputs, it always returns the same output.

## Factors and weights

| Factor | Weight | Computed from |
|--------|--------|---------------|
| Debt-to-Income (DTI) | 40% | `total_monthly_obligations ÷ stated_monthly_income` |
| Credit history | 35% | Bureau score (simulated/provided field) |
| Income stability | 25% | `min(tenure_subscore, variability_subscore)` |

## Income stability — weakest-link rule

Income stability uses two independently-scored sub-factors:

1. **Employment tenure** (months with current employer)
2. **Income variability** (deposit std-dev ÷ mean across statement period, as %)

The combined score is `min(tenure_subscore, variability_subscore)`. Strong tenure does not offset volatile income. The binding constraint's policy clause is cited in the breakdown.

## Band evaluation

All thresholds live in `policy_config.yaml`. Two evaluation directions:

**`max_asc`** (lower value is better — used for DTI and variability):
- Entries listed ascending by `max`
- First entry where `value ≤ max` wins
- Example: DTI = 0.35 → checked against max 0.30 (no) → max 0.40 (yes) → **moderate, score 0.7**

**`min_desc`** (higher value is better — used for bureau score and tenure):
- Entries listed descending by `min`
- First entry where `value ≥ min` wins
- Example: bureau = 680 → checked against min 720 (no) → min 650 (yes) → **moderate, score 0.7**

**Boundary rule:** a value exactly on a stated boundary always resolves to the better-scoring band. DTI = 0.40 → moderate (0.7), not elevated. Bureau = 650 → moderate (0.7), not elevated.

## Band scores and labels

| Score | Label |
|-------|-------|
| 1.0 | low_risk |
| 0.7 | moderate |
| 0.4 | elevated |
| 0.0 | high_risk |

## Composite score

```
composite = (dti_score × 0.40) + (bureau_score × 0.35) + (income_stability × 0.25)
```

Result is a float in [0.0, 1.0].

## Recommendation bands

| Composite | Band |
|-----------|------|
| ≥ 0.75 | **APPROVE** |
| ≥ 0.65 | **REFER** |
| < 0.65 | **DECLINE** |

Boundary rule applies here too: composite = 0.75 → APPROVE (not REFER); composite = 0.65 → REFER (not DECLINE).

## Policy clause citations

Each band entry in `policy_config.yaml` names an exact `clause_id`. The engine reads this directly — no similarity search. Full clause text is fetched from ChromaDB by exact ID lookup.

If a `clause_id` in the config has no matching document in Chroma, the application halts with `POLICY_CONFIG_ERROR` rather than silently citing nothing.

## Editing policy thresholds

All thresholds are in `policy_config.yaml`. Edit that file to change policy — no code changes required:

```yaml
weights:
  dti: 0.40
  credit_history: 0.35
  income_stability: 0.25

bands:
  dti:
    direction: max_asc
    entries:
      - {max: 0.30, score: 1.0, clause: "3.1(a)"}
      - {max: 0.40, score: 0.7, clause: "3.1(b)"}
      - {max: 0.50, score: 0.4, clause: "3.1(c)"}
      - {max: null, score: 0.0, clause: "3.1(d)"}

recommendation_bands:
  approve_min: 0.75
  refer_min: 0.65
```

After editing thresholds, re-seed ChromaDB if clause text changed:
```bash
.venv/bin/python scripts/seed_chroma.py
```

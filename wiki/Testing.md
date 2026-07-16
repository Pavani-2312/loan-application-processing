# Testing

## Running the tests

```bash
# All 66 tests (no API key required — LLM calls are stubbed)
.venv/bin/python -m pytest tests/ -v

# Or via the launch script
./run.sh --test
```

All tests run without an API key. LLM calls in acceptance tests are stubbed with `unittest.mock`. The policy engine has no LLM dependency at all.

## Test suite overview

| File | Tests | What it covers |
|------|-------|----------------|
| `tests/test_repository.py` | 26 | DB models, WAL mode, optimistic locking, versioned `extracted_fields`, REFER non-terminal, audit append-only |
| `tests/test_policy_engine.py` | 31 | All band boundaries, exact-boundary cases, weakest-link income stability, composite arithmetic, determinism |
| `tests/test_acceptance.py` | 9 | 7 requirement scenarios + 2 human gate guards |

## Acceptance scenarios

| # | Scenario | Requirements covered |
|---|----------|---------------------|
| 1 | Clear APPROVE (happy path) | FR-01–FR-08, FR-11, FR-13 |
| 2 | Borderline REFER | FR-05–FR-08, FR-11 |
| 3 | Missing document → halt before scoring | FR-02, FR-04 |
| 4 | Identity-blind consistency check | FR-09, FR-10, NFR-02 |
| 5 | Prompt injection in application content | FR-12, FR-11, NFR-06 |
| 6 | REFER chain (non-terminal) | FR-11, FR-13, FR-14 |
| 7 | Low-confidence extraction → manual verification | FR-16 |
| 8 | Human gate rejects wrong status | FR-11, NFR-03 |
| 9 | Human gate REFER requires reason | FR-11 |

## Policy engine test coverage

`test_policy_engine.py` covers all 31 combinations of:
- All band boundaries for DTI, bureau score, tenure, and variability
- **Exact-boundary cases** for both `max_asc` and `min_desc` directions (e.g., DTI = 0.40 exactly → moderate, not elevated)
- Weakest-link income stability (tenure low + variability high → combined = low)
- Full composite arithmetic
- Determinism (same inputs → identical output across repeated calls)

## Repository test coverage

`test_repository.py` covers:
- Application create, get, status update
- Optimistic locking — concurrent status write raises `ConcurrentModificationError`
- `extracted_fields` append-only versioning — corrections add a row, never overwrite
- REFER non-terminal — `human_decisions` supports multiple rows; only APPROVE/DECLINE set `DECIDED`
- `audit_log` append-only — no update or delete operations
- SQLite WAL mode enabled

## End-to-end test results (live run)

Verified against GitHub Models (GPT-4o) using the three original test document sets:

| Scenario | Expected | Actual | Composite score |
|----------|----------|--------|-----------------|
| Priya Sharma | APPROVE | ✅ APPROVE | 1.000 |
| Arjun Mehta | REFER | ✅ REFER | 0.700 |

Scores matched hand-calculated values to 4 decimal places. All validation checks passed. Fairness check: PASS on both.

## Test documents

20 scenarios in `test_docs/`, each with `government_id`, `payslip`, and `bank_statement` in both `.txt` and `.pdf` format:

| Band | Scenarios |
|------|-----------|
| APPROVE | s01, s04 (boundary values), s05 (high income), s06 (low DTI), s07 (govt employee), s08 (excellent credit) |
| REFER | s02, s09–s13 |
| DECLINE | s03, s14–s20 (including zero composite, volatile income, just-below-REFER) |

See `test_docs/README.md` for full scoring tables for each scenario.

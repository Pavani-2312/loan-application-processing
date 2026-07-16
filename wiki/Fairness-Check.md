# Fairness Check

## What it is

An identity-blind extraction consistency check. The agent re-extracts scoring-relevant numeric fields from documents with the applicant's name and address redacted, re-scores with those blind values, and compares the resulting recommendation band to the original.

## Method

1. Applicant name and address are replaced with `[APPLICANT NAME]` and `[APPLICANT ADDRESS]` in all raw document text.
2. The LLM re-extracts the six scoring-relevant numeric fields from the redacted documents.
3. Those blind-extracted values are fed into the same deterministic Python scoring engine.
4. The resulting band (`blind_band`) is compared to `original_band`.

## Outcomes

| Result | Meaning | Action |
|--------|---------|--------|
| `PASS` | `original_band == blind_band` | Stored in audit record; shown in UI |
| `FAIL` | Bands differ | Hard stop — disparity surfaced to underwriter; both breakdowns stored; never auto-resolved |

## What this tests

Whether the LLM extraction layer let applicant identity implicitly influence a numeric field — e.g., adjusting an extracted income figure because of a perceived employer reputation.

## What this does NOT test

- Proxy discrimination via neighborhood effects
- Population-level disparate impact across demographic groups
- Whether the policy thresholds themselves produce fair outcomes across groups

Those require statistical analysis across a population of decisions. See [[Known-Limitations]] (L2).

## Storage

Results stored in `fairness_checks` table, versioned by `revision_number`:

| Field | Description |
|-------|-------------|
| `original_band` | Band from the standard scoring run |
| `blind_band` | Band from the identity-blind run |
| `result` | `PASS` or `FAIL` |
| `disparity_detail` | Populated on `FAIL` — which factor changed and how |

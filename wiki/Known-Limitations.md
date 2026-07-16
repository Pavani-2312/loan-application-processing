# Known Limitations

These are not polish items — they are gaps that must be closed before this system could be used for real credit decisions.

## L1 — No verified underwriter authentication

**What the build does:** the sidebar shows a role-selector dropdown. The selected name is recorded in `human_decisions.underwriter_id`.

**Why this matters:** the entire governance argument rests on "a licensed human decided this." Without verified identity, `underwriter_id` cannot be trusted as legal evidence of who actually made the decision. This is the largest gap in the audit story.

**Status:** blocking for any real use. Must be replaced with SSO or signed sessions before deployment. The build deliberately leaves this as a visible, named gap rather than implementing a fake login screen that gives false confidence.

---

## L2 — Fairness check is extraction-layer only

**What the build does:** re-extracts numeric fields from identity-redacted documents and checks whether the recommendation band changes. A pass means the LLM extraction layer did not let name or address implicitly influence a numeric field.

**Why this matters:** a system can pass this check 100% of the time and still produce disparate outcomes across demographic groups if:
- The policy thresholds themselves have disparate impact
- Address correlates with a protected characteristic through proxy effects the model never explicitly reasons about

**Status:** not solved. This is a documented scope narrowing. A real deployment needs a separate, periodic disparate-impact analysis (e.g., adverse impact ratio / four-fifths rule testing) run by compliance across a population of decisions.

---

## L3 — No live credit bureau integration

**What the build does:** bureau score is a field extracted from the bank statement or other uploaded documents. It is simulated/provided input, not a live bureau pull.

**Why this matters:** scoring correctness is bounded by the quality of the provided data. A forged bureau score in a document would pass extraction and score normally.

**Status:** documented assumption. Not a defect in the architecture — swapping in a live bureau integration would not require changes to the scoring engine, only to the intake data source.

---

## L4 — SQLite under concurrent Streamlit sessions

**What the build does:** SQLite opened in WAL mode with optimistic locking on `applications.status_version`. This handles typical demo-scale concurrent access safely.

**Why this matters:** WAL mode serialises concurrent writers at the database level. Under real concurrent load (multiple underwriters acting simultaneously on different applications), edge cases can still occur. SQLite is not designed as a multi-writer production database.

**Status:** mitigated for demo scale. A production deployment should swap the repository layer's backing store to PostgreSQL — the repository abstraction (`ApplicationRepository`, etc.) is designed to make this swap without touching agent or scoring logic.

---

## Path to production

| Blocker | Estimated effort |
|---------|-----------------|
| SSO / signed session authentication (L1) | 5 days |
| PostgreSQL migration (L4) | 2 days |
| Monitoring and alerting | 2 days |
| Load testing | 2 days |
| Security audit | 1 day |
| Population-level disparate-impact analysis pipeline (L2) | Separate compliance workstream |

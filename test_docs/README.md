# Test Documents

Three sets of plain-text loan application documents for manual end-to-end testing
of the Streamlit UI. Each set contains three files:
- `government_id.txt`
- `payslip.txt`
- `bank_statement.txt`

Upload the three files from the same scenario folder to the New Application screen.

---

## Scenario 1 — APPROVE (`scenario_approve/`)

**Applicant:** Priya Sharma  
**Address:** 42 Greenwood Avenue, Koramangala, Bengaluru, Karnataka - 560034

| Factor | Raw value | Band | Score | Weight | Contribution |
|--------|-----------|------|-------|--------|--------------|
| DTI | 12,000 / 60,000 = **0.20** | low_risk | 1.0 | 40% | 0.40 |
| Credit history | **750** | low_risk | 1.0 | 35% | 0.35 |
| Income stability — tenure | **36 months** | low_risk | 1.0 | — | — |
| Income stability — variability | **5%** | low_risk | 1.0 | — | — |
| Income stability (combined = min) | — | low_risk | 1.0 | 25% | 0.25 |
| **Composite** | | | | | **1.00** |

**Expected band: APPROVE** (≥ 0.75)

---

## Scenario 2 — REFER (`scenario_refer/`)

**Applicant:** Arjun Mehta  
**Address:** 17 Palm Street, Bandra West, Mumbai, Maharashtra - 400050

| Factor | Raw value | Band | Score | Weight | Contribution |
|--------|-----------|------|-------|--------|--------------|
| DTI | 17,500 / 50,000 = **0.35** | moderate | 0.7 | 40% | 0.28 |
| Credit history | **680** | moderate | 0.7 | 35% | 0.245 |
| Income stability — tenure | **18 months** | moderate | 0.7 | — | — |
| Income stability — variability | **18%** | moderate | 0.7 | — | — |
| Income stability (combined = min) | — | moderate | 0.7 | 25% | 0.175 |
| **Composite** | | | | | **0.70** |

**Expected band: REFER** (0.65 ≤ x < 0.75)

---

## Scenario 3 — DECLINE (`scenario_decline/`)

**Applicant:** Ravi Kumar  
**Address:** 88 Lajpat Nagar, New Delhi, Delhi - 110024

| Factor | Raw value | Band | Score | Weight | Contribution |
|--------|-----------|------|-------|--------|--------------|
| DTI | 30,000 / 50,000 = **0.60** | high_risk | 0.0 | 40% | 0.00 |
| Credit history | **560** | high_risk | 0.0 | 35% | 0.00 |
| Income stability — tenure | **4 months** | high_risk | 0.0 | — | — |
| Income stability — variability | **45%** | high_risk | 0.0 | — | — |
| Income stability (combined = min) | — | high_risk | 0.0 | 25% | 0.00 |
| **Composite** | | | | | **0.00** |

**Expected band: DECLINE** (< 0.65)

---

## Notes

- All names and addresses match exactly across the three documents within each scenario
  so the `name_match` validation check passes.
- All ID expiry dates are in 2028–2033, well past the 2026 submission date.
- Bank statement period end is **30 June 2026** (within the 60-day policy window).
- Income on payslip is within ±15% of average monthly deposits in all three scenarios
  (income plausibility check passes).
- Scenario 3 deliberately includes bureau remarks about missed payments to make the
  DECLINE realistic, but the numeric bureau score (560) is the field the scorer reads.

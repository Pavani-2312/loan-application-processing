# Test Documents

20 sets of loan application documents for end-to-end testing of the Streamlit UI.  
Each set contains **6 files** — `.txt` (plain text) and `.pdf` (converted):

```
government_id.txt / government_id.pdf
payslip.txt       / payslip.pdf
bank_statement.txt / bank_statement.pdf
```

Upload the three **PDF** files from one scenario folder to the New Application screen.  
The `.txt` source files are kept alongside for reference.

To regenerate all PDFs from the `.txt` sources:
```bash
.venv/bin/python scripts/txt_to_pdf.py
```

---

## Scoring reference

| Factor | Weight | Bands |
|--------|--------|-------|
| DTI (obligations/income) | 40% | ≤0.30→1.0 · ≤0.40→0.7 · ≤0.50→0.4 · else→0.0 |
| Credit bureau score | 35% | ≥720→1.0 · ≥650→0.7 · ≥580→0.4 · else→0.0 |
| Income stability (min of tenure+variability) | 25% | tenure: ≥24mo→1.0 · ≥12mo→0.7 · ≥6mo→0.4 · else→0.0 |
| | | variability: ≤10%→1.0 · ≤25%→0.7 · ≤40%→0.4 · else→0.0 |

**Bands:** APPROVE ≥ 0.75 · REFER ≥ 0.65 · DECLINE < 0.65

---

## APPROVE scenarios

### Scenario 1 — `scenario_approve/`  *(original)*
**Applicant:** Priya Sharma · Bengaluru

| Factor | Raw value | Score | Contrib |
|--------|-----------|-------|---------|
| DTI | 12,000/60,000 = 0.20 | 1.0 | 0.40 |
| Bureau | 750 | 1.0 | 0.35 |
| Income stability | 36 mo · 5% var | 1.0 | 0.25 |
| **Composite** | | | **1.00 → APPROVE** |

---

### Scenario 4 — `s04_approve_boundary/`
**Applicant:** Kavya Nair · Bengaluru  
All four inputs land **exactly on band boundaries** → all resolve to the better band (boundary rule).

| Factor | Raw value | Score | Contrib |
|--------|-----------|-------|---------|
| DTI | 18,000/60,000 = **0.30** (boundary) | 1.0 | 0.40 |
| Bureau | **720** (boundary) | 1.0 | 0.35 |
| Income stability | **24 mo** · **10% var** (both boundaries) | 1.0 | 0.25 |
| **Composite** | | | **1.00 → APPROVE** |

---

### Scenario 5 — `s05_approve_high_income/`
**Applicant:** Suresh Venkataraman · Chennai — TCS Principal Architect

| Factor | Raw value | Score | Contrib |
|--------|-----------|-------|---------|
| DTI | 24,000/1,21,334 = 0.198 | 1.0 | 0.40 |
| Bureau | 790 | 1.0 | 0.35 |
| Income stability | 87 mo · 4% var | 1.0 | 0.25 |
| **Composite** | | | **1.00 → APPROVE** |

---

### Scenario 6 — `s06_approve_low_dti/`
**Applicant:** Meera Pillai · Thiruvananthapuram — Government college professor

| Factor | Raw value | Score | Contrib |
|--------|-----------|-------|---------|
| DTI | 6,000/60,000 = 0.10 | 1.0 | 0.40 |
| Bureau | 755 | 1.0 | 0.35 |
| Income stability | 94 mo · 3% var | 1.0 | 0.25 |
| **Composite** | | | **1.00 → APPROVE** |

---

### Scenario 7 — `s07_approve_govt_employee/`
**Applicant:** Rajesh Gupta · Allahabad — UP Government Section Officer  
0% income variability (fixed government salary).

| Factor | Raw value | Score | Contrib |
|--------|-----------|-------|---------|
| DTI | 9,500/51,200 = 0.185 | 1.0 | 0.40 |
| Bureau | 760 | 1.0 | 0.35 |
| Income stability | 234 mo · **0% var** | 1.0 | 0.25 |
| **Composite** | | | **1.00 → APPROVE** |

---

### Scenario 8 — `s08_approve_excellent_credit/`
**Applicant:** Ananya Krishnamurthy · Hyderabad — Amazon Product Manager

| Factor | Raw value | Score | Contrib |
|--------|-----------|-------|---------|
| DTI | 17,000/77,500 = 0.219 | 1.0 | 0.40 |
| Bureau | 820 | 1.0 | 0.35 |
| Income stability | 63 mo · 3% var | 1.0 | 0.25 |
| **Composite** | | | **1.00 → APPROVE** |

---

## REFER scenarios

### Scenario 2 — `scenario_refer/`  *(original)*
**Applicant:** Arjun Mehta · Mumbai

| Factor | Raw value | Score | Contrib |
|--------|-----------|-------|---------|
| DTI | 17,500/50,000 = 0.35 | 0.7 | 0.280 |
| Bureau | 680 | 0.7 | 0.245 |
| Income stability | 18 mo · 18% var | 0.7 | 0.175 |
| **Composite** | | | **0.70 → REFER** |

---

### Scenario 9 — `s09_refer_moderate_all/`
**Applicant:** Deepak Agarwal · Jaipur — All three factors moderate.

| Factor | Raw value | Score | Contrib |
|--------|-----------|-------|---------|
| DTI | 14,000/40,000 = 0.35 | 0.7 | 0.280 |
| Bureau | 690 | 0.7 | 0.245 |
| Income stability | 18 mo · 20% var · min=0.7 | 0.7 | 0.175 |
| **Composite** | | | **0.70 → REFER** |

---

### Scenario 10 — `s10_refer_weak_bureau/`
**Applicant:** Pooja Rao · Pune — Good tenure, moderate bureau/variability.

| Factor | Raw value | Score | Contrib |
|--------|-----------|-------|---------|
| DTI | 14,000/45,000 = 0.311 | 0.7 | 0.280 |
| Bureau | 670 | 0.7 | 0.245 |
| Income stability | 48 mo · 22% var · min=0.7 | 0.7 | 0.175 |
| **Composite** | | | **0.70 → REFER** |

---

### Scenario 11 — `s11_refer_high_dti/`
**Applicant:** Vikram Singh · Dehradun — Good credit, short tenure pulls stability to moderate.

| Factor | Raw value | Score | Contrib |
|--------|-----------|-------|---------|
| DTI | 21,000/60,000 = 0.35 | 0.7 | 0.280 |
| Bureau | 680 | 0.7 | 0.245 |
| Income stability | 20 mo · 4% var · min=0.7 (tenure binding) | 0.7 | 0.175 |
| **Composite** | | | **0.70 → REFER** |

---

### Scenario 12 — `s12_refer_new_joiner/`
**Applicant:** Sneha Patel · Ahmedabad — Steady deposits but short tenure.

| Factor | Raw value | Score | Contrib |
|--------|-----------|-------|---------|
| DTI | 15,750/45,000 = 0.35 | 0.7 | 0.280 |
| Bureau | 680 | 0.7 | 0.245 |
| Income stability | 20 mo · 8% var · min=0.7 (tenure binding) | 0.7 | 0.175 |
| **Composite** | | | **0.70 → REFER** |

---

### Scenario 13 — `s13_refer_borderline/`
**Applicant:** Ramesh Iyer · Chennai — All factors uniformly moderate.

| Factor | Raw value | Score | Contrib |
|--------|-----------|-------|---------|
| DTI | 13,000/37,000 = 0.351 | 0.7 | 0.280 |
| Bureau | 660 | 0.7 | 0.245 |
| Income stability | 15 mo · 22% var · min=0.7 | 0.7 | 0.175 |
| **Composite** | | | **0.70 → REFER** |

---

## DECLINE scenarios

### Scenario 3 — `scenario_decline/`  *(original)*
**Applicant:** Ravi Kumar · New Delhi

| Factor | Raw value | Score | Contrib |
|--------|-----------|-------|---------|
| DTI | 30,000/50,000 = 0.60 | 0.0 | 0.000 |
| Bureau | 560 | 0.0 | 0.000 |
| Income stability | 4 mo · 45% var | 0.0 | 0.000 |
| **Composite** | | | **0.00 → DECLINE** |

---

### Scenario 14 — `s14_decline_high_dti_new/`
**Applicant:** Nitin Sharma · Lucknow — New joiner, high DTI, damaged bureau.

| Factor | Raw value | Score | Contrib |
|--------|-----------|-------|---------|
| DTI | 18,000/30,000 = 0.60 | 0.0 | 0.000 |
| Bureau | 610 | 0.4 | 0.140 |
| Income stability | 3 mo · 50% var · min=0.0 | 0.0 | 0.000 |
| **Composite** | | | **0.14 → DECLINE** |

---

### Scenario 15 — `s15_decline_zero_bureau/`
**Applicant:** Sandeep Kulkarni · Pune — Good tenure but written-off credit history and very high DTI.

| Factor | Raw value | Score | Contrib |
|--------|-----------|-------|---------|
| DTI | 30,000/55,000 = 0.545 | 0.0 | 0.000 |
| Bureau | 555 | 0.0 | 0.000 |
| Income stability | 36 mo · 5% var · min=1.0 | 1.0 | 0.250 |
| **Composite** | | | **0.25 → DECLINE** |

Good income stability cannot offset failed DTI + zero bureau score.

---

### Scenario 16 — `s16_decline_elevated_all/`
**Applicant:** Pradeep Nambiar · Calicut — All three factors in the elevated band.

| Factor | Raw value | Score | Contrib |
|--------|-----------|-------|---------|
| DTI | 13,500/28,000 = 0.482 | 0.4 | 0.160 |
| Bureau | 595 | 0.4 | 0.140 |
| Income stability | 9 mo · 30% var · min=0.4 | 0.4 | 0.100 |
| **Composite** | | | **0.40 → DECLINE** |

---

### Scenario 17 — `s17_decline_zero_composite/`
**Applicant:** Arun Tiwari · Lucknow — Every factor in the high-risk band; composite = 0.

| Factor | Raw value | Score | Contrib |
|--------|-----------|-------|---------|
| DTI | 11,500/20,000 = 0.575 | 0.0 | 0.000 |
| Bureau | 545 | 0.0 | 0.000 |
| Income stability | 5 mo · 55% var · min=0.0 | 0.0 | 0.000 |
| **Composite** | | | **0.00 → DECLINE** |

---

### Scenario 18 — `s18_decline_weak_bureau_high_dti/`
**Applicant:** Kiran Reddy · Hyderabad — Moderate DTI, but bureau and variability both zero-score.

| Factor | Raw value | Score | Contrib |
|--------|-----------|-------|---------|
| DTI | 18,000/40,000 = 0.45 | 0.4 | 0.160 |
| Bureau | 570 | 0.0 | 0.000 |
| Income stability | 8 mo · 42% var · min=0.0 (variability binding) | 0.0 | 0.000 |
| **Composite** | | | **0.16 → DECLINE** |

---

### Scenario 19 — `s19_decline_volatile_income/`
**Applicant:** Mohan Das · Kolkata — Freelance/contract worker; volatile income zeroes out stability.

| Factor | Raw value | Score | Contrib |
|--------|-----------|-------|---------|
| DTI | 14,800/40,000 = 0.37 | 0.7 | 0.280 |
| Bureau | 620 | 0.4 | 0.140 |
| Income stability | 10 mo · 50% var · min=0.0 (variability binding) | 0.0 | 0.000 |
| **Composite** | | | **0.42 → DECLINE** |

Strong DTI is not enough — highly volatile income collapses the stability score.

---

### Scenario 20 — `s20_decline_just_below_refer/`
**Applicant:** Divya Menon · Kochi — Just below the REFER threshold (0.625 vs 0.65 cutoff).

| Factor | Raw value | Score | Contrib |
|--------|-----------|-------|---------|
| DTI | 12,600/36,000 = 0.35 | 0.7 | 0.280 |
| Bureau | 650 | 0.7 | 0.245 |
| Income stability | 12 mo · 26% var · min=0.4 (variability binding) | 0.4 | 0.100 |
| **Composite** | | | **0.625 → DECLINE** |

Moderate tenure and bureau are undermined by elevated income variability.
0.625 is 0.025 below the REFER cutoff of 0.650.

---

## Notes

- All names and addresses match exactly across the three documents within each scenario
  (name_match validation passes).
- All ID expiry dates are 2027–2034, well past the June 2026 submission date.
- Bank statement period end is **30 June 2026** (within the 60-day policy window).
- Stated income on payslip is within ±15% of average monthly deposits in all scenarios
  (income plausibility check passes).
- PDFs were generated by `scripts/txt_to_pdf.py` using DejaVuSansMono via fpdf2.

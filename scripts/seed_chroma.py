"""
scripts/seed_chroma.py
Seeds the ChromaDB credit_policy_clauses collection with all policy clauses
from docs/04_Data_Policy_Model.md §1 (Sections 3–9).

Run once before starting the application:
    python scripts/seed_chroma.py

Safe to re-run — uses upsert, so existing clauses are updated not duplicated.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import chromadb

from src.config import get_chroma_dir

# ---------------------------------------------------------------------------
# Policy clause corpus — exact text from docs/04_Data_Policy_Model.md §1
# Each entry: (clause_id, text, section_name, factor_key, band_label)
# ---------------------------------------------------------------------------
CLAUSES: list[tuple[str, str, str, str, str | None]] = [
    # Section 3 — Debt-to-Income
    (
        "3.1(a)",
        "DTI ≤ 0.30 is classified low risk and scores in the top band.",
        "Debt-to-Income",
        "dti",
        "low_risk",
    ),
    (
        "3.1(b)",
        "DTI between 0.30 and 0.40 is classified moderate risk.",
        "Debt-to-Income",
        "dti",
        "moderate",
    ),
    (
        "3.1(c)",
        "DTI between 0.40 and 0.50 is classified elevated risk and typically requires referral.",
        "Debt-to-Income",
        "dti",
        "elevated",
    ),
    (
        "3.1(d)",
        "DTI above 0.50 is classified high risk and typically does not meet policy for approval.",
        "Debt-to-Income",
        "dti",
        "high_risk",
    ),
    # Section 4 — Credit History
    (
        "4.1(a)",
        "A simulated bureau score of 720+ with no delinquencies in the last 24 months scores in the top band.",
        "Credit History",
        "credit_history",
        "low_risk",
    ),
    (
        "4.1(b)",
        "A score of 650–719, or one minor delinquency in 24 months, is moderate risk.",
        "Credit History",
        "credit_history",
        "moderate",
    ),
    (
        "4.1(c)",
        "A score of 580–649, or a history of repeated minor delinquencies, is elevated risk.",
        "Credit History",
        "credit_history",
        "elevated",
    ),
    (
        "4.1(d)",
        "A score below 580, or any major delinquency (default, charge-off) in 24 months, is high risk.",
        "Credit History",
        "credit_history",
        "high_risk",
    ),
    # Section 5.1 — Employment Tenure
    (
        "5.1(a)",
        "24+ months with current employer scores in the top band.",
        "Income Stability - Employment Tenure",
        "income_stability",
        "low_risk",
    ),
    (
        "5.1(b)",
        "12–24 months tenure is moderate.",
        "Income Stability - Employment Tenure",
        "income_stability",
        "moderate",
    ),
    (
        "5.1(c)",
        "6–12 months tenure is elevated.",
        "Income Stability - Employment Tenure",
        "income_stability",
        "elevated",
    ),
    (
        "5.1(d)",
        "Under 6 months tenure is high risk.",
        "Income Stability - Employment Tenure",
        "income_stability",
        "high_risk",
    ),
    # Section 5.2 — Income Variability
    (
        "5.2(a)",
        "Income variability under 10% across the reviewed statement period scores in the top band.",
        "Income Stability - Income Variability",
        "income_stability",
        "low_risk",
    ),
    (
        "5.2(b)",
        "Variability 10–25% is moderate.",
        "Income Stability - Income Variability",
        "income_stability",
        "moderate",
    ),
    (
        "5.2(c)",
        "Variability 25–40% is elevated.",
        "Income Stability - Income Variability",
        "income_stability",
        "elevated",
    ),
    (
        "5.2(d)",
        "Variability above 40%, or an unverifiable income pattern, is high risk.",
        "Income Stability - Income Variability",
        "income_stability",
        "high_risk",
    ),
    # Clause 5.3 — Combination rule
    (
        "5.3",
        "The income-stability factor score is the lower (weaker) of the tenure sub-score and the "
        "variability sub-score — strong tenure does not offset volatile income, and vice versa.",
        "Income Stability - Combination Rule",
        "income_stability",
        None,
    ),
    # Section 6 — Document Requirements
    (
        "6.1",
        "A complete application requires valid government ID, income proof, and a bank statement "
        "no older than 60 days at submission.",
        "Document Requirements",
        "documents",
        None,
    ),
    (
        "6.2",
        "Stated income must be corroborated within ±15% by recurring deposits in the bank statement; "
        "unreconciled variance beyond this requires halting the application pending clarification.",
        "Document Requirements",
        "documents",
        None,
    ),
    # Section 7 — Recommendation Bands
    (
        "7.1",
        "A composite policy score of 0.75 or above supports an APPROVE recommendation.",
        "Recommendation Bands",
        "bands",
        "approve",
    ),
    (
        "7.2",
        "A composite policy score between 0.65 and 0.75 supports a REFER recommendation for "
        "human underwriting review.",
        "Recommendation Bands",
        "bands",
        "refer",
    ),
    (
        "7.3",
        "A composite policy score below 0.65 supports a DECLINE recommendation, subject to "
        "human confirmation.",
        "Recommendation Bands",
        "bands",
        "decline",
    ),
    # Section 8 — Fairness & Non-Discrimination
    (
        "8.1",
        "Recommendations must not vary based on applicant name, address, or any proxy for a "
        "protected characteristic. Any identity-blind re-score that changes the recommendation "
        "band must be treated as a policy exception requiring escalation, not an averaging exercise.",
        "Fairness & Non-Discrimination",
        "fairness",
        None,
    ),
    # Section 9 — Human Authority
    (
        "9.1",
        "No automated system may issue a final approval or adverse action. A licensed "
        "underwriter's recorded decision is required in all cases.",
        "Human Authority",
        "authority",
        None,
    ),
]


def seed(reset: bool = False) -> None:
    chroma_dir = get_chroma_dir()
    client = chromadb.PersistentClient(path=str(chroma_dir))

    if reset:
        try:
            client.delete_collection("credit_policy_clauses")
            print("Existing collection deleted.")
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name="credit_policy_clauses",
        metadata={"hnsw:space": "cosine"},
    )

    ids = []
    documents = []
    metadatas = []

    for clause_id, text, section, factor, band_label in CLAUSES:
        ids.append(clause_id)
        documents.append(text)
        metadatas.append(
            {
                "section": section,
                "factor": factor,
                "band_label": band_label if band_label is not None else "",
            }
        )

    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
    print(f"Seeded {len(ids)} policy clauses into 'credit_policy_clauses' collection.")
    print(f"Chroma store: {chroma_dir}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Seed ChromaDB with policy clauses.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete and recreate the collection before seeding.",
    )
    args = parser.parse_args()
    seed(reset=args.reset)

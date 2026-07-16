#!/usr/bin/env python3
"""
scripts/txt_to_pdf.py

Convert every .txt file under test_docs/ to a .pdf alongside it.
Uses fpdf2 with DejaVuSansMono (Unicode monospace — handles em-dash, INR, etc.)

Run: .venv/bin/python scripts/txt_to_pdf.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from fpdf import FPDF

ROOT = Path(__file__).resolve().parent.parent
TEST_DOCS = ROOT / "test_docs"
FONT_PATH = Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")


def txt_to_pdf(txt_path: Path) -> Path:
    pdf_path = txt_path.with_suffix(".pdf")

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(left=12, top=12, right=12)
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()

    pdf.add_font("DejaVuMono", style="", fname=str(FONT_PATH))
    pdf.set_font("DejaVuMono", size=8)

    line_height = 4.2
    text = txt_path.read_text(encoding="utf-8")
    for line in text.splitlines():
        # pdf.epw = effective page width (avoids "not enough horizontal space" error)
        pdf.multi_cell(pdf.epw, line_height, line, new_x="LMARGIN", new_y="NEXT")

    pdf.output(str(pdf_path))
    return pdf_path


def main() -> None:
    if not FONT_PATH.exists():
        print(f"Font not found: {FONT_PATH}")
        sys.exit(1)

    txt_files = sorted(TEST_DOCS.rglob("*.txt"))
    if not txt_files:
        print("No .txt files found under test_docs/")
        sys.exit(1)

    print(f"Converting {len(txt_files)} .txt files to PDF...\n")
    ok = 0
    errors = []

    for txt in txt_files:
        try:
            pdf = txt_to_pdf(txt)
            rel = pdf.relative_to(ROOT)
            print(f"  ✓  {rel}")
            ok += 1
        except Exception as e:
            errors.append((txt, e))
            print(f"  ✗  {txt.relative_to(ROOT)} — {e}")

    print(f"\n{ok} PDFs created", end="")
    if errors:
        print(f", {len(errors)} failed")
        sys.exit(1)
    else:
        print(" — all done.")


if __name__ == "__main__":
    main()

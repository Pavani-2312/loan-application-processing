#!/usr/bin/env bash
# run.sh — launch the Loan Application Processing agent
# Usage: ./run.sh [--seed-only] [--test]
# Requires: .venv set up via: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# --------------------------------------------------------------------------
# Check .env exists
# --------------------------------------------------------------------------
if [ ! -f ".env" ]; then
  echo "ERROR: .env file not found."
  echo "  Copy .env.example → .env and add your OPENROUTER_API_KEY."
  exit 1
fi

# --------------------------------------------------------------------------
# Activate virtualenv
# --------------------------------------------------------------------------
if [ ! -d ".venv" ]; then
  echo "ERROR: .venv not found. Run first:"
  echo "  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

source .venv/bin/activate

# --------------------------------------------------------------------------
# Options
# --------------------------------------------------------------------------
if [ "$1" == "--test" ]; then
  echo "Running test suite..."
  python -m pytest tests/ -v
  exit $?
fi

# --------------------------------------------------------------------------
# Seed ChromaDB (idempotent — safe to re-run)
# --------------------------------------------------------------------------
echo "Seeding ChromaDB with policy clauses..."
python scripts/seed_chroma.py
echo ""

if [ "$1" == "--seed-only" ]; then
  echo "Seed complete. Exiting (--seed-only)."
  exit 0
fi

# --------------------------------------------------------------------------
# Launch Streamlit
# --------------------------------------------------------------------------
echo "Starting Loan Application Processing UI..."
echo "  Local URL: http://localhost:8501"
echo "  Press Ctrl+C to stop."
echo ""

streamlit run src/app/main.py \
  --server.port 8501 \
  --server.headless true \
  --server.fileWatcherType none

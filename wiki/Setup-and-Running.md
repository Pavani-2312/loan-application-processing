# Setup and Running

## Prerequisites

- Python 3.10+ (tested on 3.14)
- A GitHub Personal Access Token with `models:read` permission — [create one here](https://github.com/settings/tokens)

## Install

```bash
# 1. Clone and enter the project
git clone https://github.com/Pavani-2312/loan-application-processing.git
cd loan-application-processing

# 2. Create a virtual environment and install dependencies
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Configure

```bash
cp .env.example .env
```

Edit `.env` and set:

```env
GITHUB_TOKEN=github_pat_...      # Your GitHub Personal Access Token
LLM_MODEL=gpt-4o                 # Or any model from github.com/marketplace/models
```

Other optional settings in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENROUTER_BASE_URL` | `https://models.inference.ai.azure.com` | LLM endpoint (GitHub Models default) |
| `DATA_DIR` | `./data` | Directory for SQLite DB and ChromaDB |
| `DB_FILENAME` | `loan_applications.db` | SQLite filename |
| `CHROMA_DIR` | `chroma_store` | ChromaDB subdirectory under DATA_DIR |
| `NODE_TIMEOUT_SECONDS` | `30` | Per-node LLM call timeout |

## Run

**Option A — launch script (recommended for first run)**
```bash
./run.sh
```
Seeds ChromaDB with 24 policy clauses, then starts the Streamlit UI.

**Option B — manual steps**
```bash
# Seed policy clauses into ChromaDB (run once, or after changing policy_config.yaml)
.venv/bin/python scripts/seed_chroma.py

# Start the UI
.venv/bin/streamlit run src/app/main.py
```

Open **http://localhost:8501** in your browser.

## Run tests

```bash
./run.sh --test
# or
.venv/bin/python -m pytest tests/ -v
```

Tests run without an API key — all LLM calls are stubbed.

## Change scoring policy

Edit `policy_config.yaml` — no code changes required. After changing clause text, re-seed ChromaDB:

```bash
.venv/bin/python scripts/seed_chroma.py
```

## Convert test documents to PDF

```bash
.venv/bin/python scripts/txt_to_pdf.py
```

Converts every `.txt` file under `test_docs/` to a `.pdf` alongside it using DejaVuSansMono (Unicode monospace). Requires no additional dependencies beyond what is in `requirements.txt`.

## Troubleshooting

**Submit button stays disabled**
Make sure all three documents are uploaded and applicant name + address are filled.

**`PROCESSING_ERROR` applications**
Check your `GITHUB_TOKEN` is valid and `LLM_MODEL` is a plain model name (e.g. `gpt-4o`, not `openai/gpt-4o`).

**`POLICY_CONFIG_ERROR`**
A `clause_id` in `policy_config.yaml` has no matching document in ChromaDB. Re-run `scripts/seed_chroma.py`.

**ChromaDB segfault under Streamlit**
The ChromaDB client is initialised once per process and cached. If you see a segfault, restart the Streamlit server — do not run `seed_chroma.py` while the UI is running.

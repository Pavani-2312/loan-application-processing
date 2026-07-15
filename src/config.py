"""
src/config.py
Loads .env and policy_config.yaml; provides typed access to all runtime settings.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def get_policy_config() -> dict[str, Any]:
    """Load and return policy_config.yaml as a dict (cached after first call)."""
    config_path = ROOT_DIR / "policy_config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"policy_config.yaml not found at {config_path}")
    with config_path.open() as f:
        return yaml.safe_load(f)


def get_openrouter_api_key() -> str:
    # Prefer GITHUB_TOKEN (GitHub Models); fall back to OPENROUTER_API_KEY (OpenRouter).
    key = os.getenv("GITHUB_TOKEN", "") or os.getenv("OPENROUTER_API_KEY", "")
    if not key:
        raise EnvironmentError(
            "No LLM API key found. Set GITHUB_TOKEN (GitHub Models) or "
            "OPENROUTER_API_KEY (OpenRouter) in your .env file."
        )
    return key


def get_openrouter_base_url() -> str:
    # GitHub Models endpoint when using a PAT; OpenRouter URL otherwise.
    return os.getenv("OPENROUTER_BASE_URL", "https://models.inference.ai.azure.com")


def get_llm_model() -> str:
    return os.getenv("LLM_MODEL", "anthropic/claude-3.5-sonnet")


def get_data_dir() -> Path:
    data_dir = Path(os.getenv("DATA_DIR", str(ROOT_DIR / "data")))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_db_path() -> Path:
    return get_data_dir() / os.getenv("DB_FILENAME", "loan_applications.db")


def get_chroma_dir() -> Path:
    chroma_dir = get_data_dir() / os.getenv("CHROMA_DIR", "chroma_store")
    chroma_dir.mkdir(parents=True, exist_ok=True)
    return chroma_dir


def get_node_timeout() -> int:
    return int(os.getenv("NODE_TIMEOUT_SECONDS", "30"))

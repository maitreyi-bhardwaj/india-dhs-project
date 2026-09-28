"""Project-wide settings.

Everything configurable comes from environment variables (optionally loaded
from a `.env` file). Nothing secret is ever written in code.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")  # does nothing if there is no .env file

# --- Data -------------------------------------------------------------------
RAW_DATA_PATH = ROOT / "data" / "IAIR7EFL.DTA"          # original, never modified
PROCESSED_DIR = ROOT / "data" / "processed"               # gitignored (inside data/)
DATABASE_PATH = PROCESSED_DIR / "nfhs5_women.sqlite"
CODEBOOK_PATH = ROOT / "docs" / "dhs_codebook.csv"
DATA_DICTIONARY_CSV = ROOT / "docs" / "data_dictionary.csv"
DATA_DICTIONARY_MD = ROOT / "documents" / "data_dictionary.md"

# --- RAG --------------------------------------------------------------------
DOCUMENTS_DIR = ROOT / "documents"
INDEX_DIR = ROOT / "data" / "index"                       # gitignored (inside data/)
OUTREACH_KB_PATH = DOCUMENTS_DIR / "outreach" / "organizations.json"
EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "256"))

# --- LLM --------------------------------------------------------------------
# The system works without an API key ("offline mode": rule-based routing and
# template answers). With a key, Claude does the routing, tool selection,
# web research and final write-up.
LLM_MODEL = os.getenv("LLM_MODEL", "claude-opus-5")
LLM_EFFORT = os.getenv("LLM_EFFORT", "medium")


def llm_available() -> bool:
    """True if an Anthropic credential is configured and not disabled."""
    if os.getenv("DISABLE_LLM", "").lower() in {"1", "true", "yes"}:
        return False
    return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))


# --- Analysis rules (shared with scripts/dhs_utils.py) -------------------------
SUPPRESS_BELOW = 25      # DHS convention: suppress percentages based on < 25 cases
FLAG_BELOW = 50          # 25-49 cases: show but flag as unreliable
MIN_GROUP_N_FOR_RANKING = 200  # groups smaller than this are not ranked (our choice)

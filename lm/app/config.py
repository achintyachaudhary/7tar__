import os
from pathlib import Path

from dotenv import load_dotenv

LM_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = LM_ROOT.parent

load_dotenv(LM_ROOT / ".env")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "deepseek-r1:32b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "qwen3-embedding")

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "stock_news")

# DB preference: lm/.env DATABASE_URL if set, otherwise reuse the existing
# Backend's database (where the screener data lives) via Backend/.env
DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    load_dotenv(REPO_ROOT / "Backend" / ".env")
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql://stock_user:password@localhost:5432/stock_ai",
    )

# Screener SQLite produced by the existing Backend app, used as fallback
SQLITE_FALLBACK = REPO_ROOT / "data" / "app.db"

LM_PORT = int(os.getenv("LM_PORT", "8001"))

# --- Zerodha Pulse news summarization ---
PULSE_FEED_URL = os.getenv("PULSE_FEED_URL", "https://pulse.zerodha.com/feed.php")
PULSE_REFRESH_MINUTES = int(os.getenv("PULSE_REFRESH_MINUTES", "30"))
PULSE_MAX_ITEMS = int(os.getenv("PULSE_MAX_ITEMS", "10"))  # new items summarized per run

# --- SearXNG live web search ---
SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8080")
SEARXNG_TIMEOUT = int(os.getenv("SEARXNG_TIMEOUT", "20"))
WEB_MAX_RESULTS = int(os.getenv("WEB_MAX_RESULTS", "5"))

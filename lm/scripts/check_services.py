"""Quick health check for all components used by the lm stock-AI service.

Run from the lm/ directory:  python scripts/check_services.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from app.config import OLLAMA_URL, OLLAMA_MODEL, EMBED_MODEL, QDRANT_URL, DATABASE_URL, SQLITE_FALLBACK


def check(label: str, fn):
    try:
        detail = fn()
        print(f"  [OK]   {label}" + (f" — {detail}" if detail else ""))
        return True
    except Exception as exc:
        print(f"  [FAIL] {label} — {exc}")
        return False


def ollama():
    r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
    r.raise_for_status()
    models = [m["name"] for m in r.json().get("models", [])]
    missing = [m for m in (OLLAMA_MODEL, EMBED_MODEL) if not any(name.startswith(m) for name in models)]
    if missing:
        raise RuntimeError(f"running, but missing models: {missing} (have {models})")
    return f"models present: {OLLAMA_MODEL}, {EMBED_MODEL}"


def qdrant():
    r = requests.get(f"{QDRANT_URL}/collections", timeout=5)
    r.raise_for_status()
    names = [c["name"] for c in r.json()["result"]["collections"]]
    return f"collections: {names or 'none yet'}"


def database():
    from app.db.stockdata import get_engine, data_source, search_stocks
    if get_engine() is None:
        raise RuntimeError(
            f"neither DATABASE_URL ({DATABASE_URL.split('@')[-1]}) nor fallback {SQLITE_FALLBACK} usable"
        )
    sample = search_stocks("A", limit=3)
    return f"source={data_source()}, sample symbols: {[s['symbol'] for s in sample]}"


def embedding():
    from app.vector.embeddings import embed
    vec = embed("hello")
    return f"dim={len(vec)}"


if __name__ == "__main__":
    print("Checking Stock AI components:\n")
    results = [
        check("Ollama LLM server", ollama),
        check("Qdrant vector DB", qdrant),
        check("Stock database", database),
        check("Embedding model", embedding),
    ]
    print()
    sys.exit(0 if all(results) else 1)

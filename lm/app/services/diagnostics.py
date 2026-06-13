"""Component checks, callable from the UI tools panel and scripts/check_services.py."""

import requests

from app.config import OLLAMA_URL, OLLAMA_MODEL, EMBED_MODEL, QDRANT_COLLECTION


def run_checks() -> list[dict]:
    checks: list[dict] = []

    def add(component: str, fn):
        try:
            checks.append({"component": component, "ok": True, "detail": fn()})
        except Exception as exc:
            checks.append({"component": component, "ok": False, "detail": str(exc)})

    def ollama():
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        missing = [m for m in (OLLAMA_MODEL, EMBED_MODEL)
                   if not any(name.startswith(m) for name in models)]
        if missing:
            raise RuntimeError(f"running, but missing models: {missing} (have {models})")
        return f"models present: {OLLAMA_MODEL}, {EMBED_MODEL}"

    def qdrant():
        from app.vector.qdrant_store import client
        names = [c.name for c in client().get_collections().collections]
        detail = f"collections: {names or 'none yet'}"
        if QDRANT_COLLECTION in names:
            detail += f" — {QDRANT_COLLECTION} has {client().count(QDRANT_COLLECTION).count} documents"
        return detail

    def database():
        from app.db.stockdata import get_engine, data_source, search_stocks
        if get_engine() is None:
            raise RuntimeError("neither DATABASE_URL nor the SQLite fallback is usable")
        sample = search_stocks("REL", limit=3)
        return f"source={data_source()}, sample symbols: {[s['symbol'] for s in sample]}"

    def embedding():
        from app.vector.embeddings import embed
        return f"dim={len(embed('dimension probe'))}"

    add("Ollama LLM server", ollama)
    add("Qdrant vector DB", qdrant)
    add("Stock database", database)
    add("Embedding model", embedding)
    return checks

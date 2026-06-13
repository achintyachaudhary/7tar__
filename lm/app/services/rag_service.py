import logging

from app.vector import qdrant_store

log = logging.getLogger("lm.rag")


def search_context(
    question: str, ticker: str | None = None, limit: int = 8, allow_unfiltered_fallback: bool = False
) -> list[dict]:
    """Pull the most relevant news/document chunks from Qdrant.

    For stock analysis we stay strict: news from other companies would pollute
    the report. Free-form questions may opt into an unfiltered retry.
    """
    try:
        docs = qdrant_store.search(question, limit=limit, ticker=ticker)
        if not docs and ticker and allow_unfiltered_fallback:
            docs = qdrant_store.search(question, limit=limit)
        return docs
    except Exception as exc:
        log.warning("qdrant search failed: %s", exc)
        return []

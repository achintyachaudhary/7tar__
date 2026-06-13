"""News feed for followed stocks (vendor-routed; Upstox Analytics by default)."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from fastapi import APIRouter, HTTPException

from app.db import crud
from app.db.database import SessionLocal

logger = logging.getLogger(__name__)

news_router = APIRouter(prefix="/api/news", tags=["news"])

_CACHE_TTL = 600  # news doesn't move faster than this for a personal feed
_cache_lock = threading.Lock()
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _build_following_feed() -> dict[str, Any]:
    from app.services.vendors import upstox
    from app.services.vendors.registry import active_vendor

    with SessionLocal() as db:
        symbols = crud.get_following_symbols(db)

    if not symbols:
        return {"articles": [], "symbols": [], "vendor": active_vendor("news")}

    if not upstox.is_configured():
        raise HTTPException(
            status_code=503,
            detail="News vendor (Upstox) is not configured — set UPSTOX_ANALYTICS_TOKEN.",
        )

    key_to_symbol: dict[str, str] = {}
    for sym in symbols:
        inst = upstox.resolve_instrument(sym)
        if inst:
            key_to_symbol[inst["instrument_key"]] = sym

    raw = upstox.fetch_news(list(key_to_symbol.keys()))

    articles: list[dict[str, Any]] = []
    for instrument_key, items in raw.items():
        sym = key_to_symbol.get(instrument_key, instrument_key)
        for a in items:
            articles.append(
                {
                    "symbol": sym,
                    "heading": a.get("heading"),
                    "summary": a.get("summary"),
                    "thumbnail": a.get("thumbnail"),
                    "article_link": a.get("article_link"),
                    "published_time": a.get("published_time"),
                }
            )
    articles.sort(key=lambda a: a.get("published_time") or 0, reverse=True)

    unresolved = [s for s in symbols if s not in key_to_symbol.values()]
    return {
        "articles": articles[:120],
        "symbols": symbols,
        "unresolved_symbols": unresolved,
        "vendor": active_vendor("news"),
    }


@news_router.get("/following")
def news_for_following(refresh: bool = False) -> dict[str, Any]:
    now = time.time()
    with _cache_lock:
        hit = _cache.get("following")
        if hit and not refresh and now - hit[0] < _CACHE_TTL:
            return hit[1]

    try:
        feed = _build_following_feed()
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("News feed build failed")
        raise HTTPException(status_code=502, detail=f"News fetch failed: {exc}") from exc

    feed["fetched_at"] = now
    with _cache_lock:
        _cache["following"] = (now, feed)
    return feed

"""Zerodha Pulse news: fetch RSS, summarize new items with the local LLM, store.

Runs on a schedule (see main.py lifespan) and on demand via POST /api/pulse/refresh.
Tables live in the same database as the stock data, prefixed lm_pulse_.
"""

import logging
import re
import threading
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import requests
from sqlalchemy import text

from app.config import OLLAMA_MODEL, PULSE_FEED_URL, PULSE_MAX_ITEMS
from app.db.stockdata import get_engine
from app.llm import ollama_client

log = logging.getLogger("lm.pulse")

_refresh_lock = threading.Lock()
_tables_ready = False

# Zero-width and control chars that Pulse titles sometimes carry
_CLEAN_RE = re.compile(r"[​‌‍﻿]")

SOURCE_NAMES = {
    "ndtvprofit.com": "NDTV Profit",
    "economictimes.indiatimes.com": "Economic Times",
    "livemint.com": "Mint",
    "business-standard.com": "Business Standard",
    "moneycontrol.com": "Moneycontrol",
    "thehindubusinessline.com": "BusinessLine",
    "financialexpress.com": "Financial Express",
    "businesstoday.in": "Business Today",
    "reuters.com": "Reuters",
    "cnbctv18.com": "CNBC TV18",
    "zeebiz.com": "Zee Business",
    "freepressjournal.in": "Free Press Journal",
}


def _clean(s: str | None) -> str:
    return _CLEAN_RE.sub("", s or "").strip()


def _source_from_link(link: str) -> str:
    host = (urlparse(link).hostname or "").removeprefix("www.")
    return SOURCE_NAMES.get(host, host or "unknown")


def fetch_feed() -> list[dict]:
    resp = requests.get(
        PULSE_FEED_URL,
        timeout=20,
        headers={"User-Agent": "Mozilla/5.0 (gcc stock screener; local dev)"},
    )
    resp.raise_for_status()
    channel = ET.fromstring(resp.content).find("channel")
    items = []
    for item in (channel.findall("item") if channel is not None else []):
        link = _clean(item.findtext("link"))
        title = _clean(item.findtext("title"))
        if not link or not title:
            continue
        published = None
        try:
            published = parsedate_to_datetime(item.findtext("pubDate", "")).astimezone(timezone.utc)
        except Exception:
            pass
        items.append({
            "guid": link.split("#")[0],
            "title": title,
            "link": link,
            "source": _source_from_link(link),
            "snippet": _clean(item.findtext("description")),
            "published_at": published.isoformat() if published else None,
        })
    return items


def _ensure_tables() -> None:
    global _tables_ready
    if _tables_ready:
        return
    eng = get_engine()
    if eng is None:
        raise RuntimeError("stock database unavailable; cannot store pulse news")
    pk = (
        "id INTEGER PRIMARY KEY AUTOINCREMENT"
        if eng.dialect.name == "sqlite"
        else "id SERIAL PRIMARY KEY"
    )
    with eng.begin() as conn:
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS lm_pulse_news (
                {pk},
                guid TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                link TEXT,
                source TEXT,
                snippet TEXT,
                summary TEXT,
                model TEXT,
                published_at TEXT,
                summarized_at TEXT
            )"""))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS lm_pulse_runs (
                {pk},
                started_at TEXT,
                finished_at TEXT,
                status TEXT,
                triggered_by TEXT,
                items_fetched INTEGER DEFAULT 0,
                items_new INTEGER DEFAULT 0,
                error TEXT
            )"""))
    _tables_ready = True


def _summarize(item: dict) -> str:
    prompt = (
        "You are a financial news editor. Summarize this Indian market news item in ONE "
        "crisp factual sentence (maximum 30 words). Output only the sentence, nothing else.\n\n"
        f"Title: {item['title']}\n"
        f"Snippet: {item['snippet'][:600]}"
    )
    answer = ollama_client.chat(prompt, timeout=180)["answer"].strip()
    # model sometimes wraps the sentence in quotes or adds a label
    return answer.strip('"').removeprefix("Summary:").strip() or item["snippet"][:200]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def refresh(triggered_by: str = "manual") -> dict:
    """Fetch the feed and summarize new items. Returns run stats.

    Refuses to run concurrently — the scheduler and the UI button share one lock.
    """
    if not _refresh_lock.acquire(blocking=False):
        return {"status": "already_running"}
    try:
        _ensure_tables()
        eng = get_engine()
        run_id = None
        with eng.begin() as conn:
            conn.execute(
                text("INSERT INTO lm_pulse_runs (started_at, status, triggered_by) "
                     "VALUES (:t, 'running', :by)"),
                {"t": _now(), "by": triggered_by},
            )
            run_id = conn.execute(text(
                "SELECT MAX(id) FROM lm_pulse_runs"
            )).scalar()

        try:
            items = fetch_feed()
            with eng.connect() as conn:
                existing = {
                    r[0] for r in conn.execute(text("SELECT guid FROM lm_pulse_news"))
                }
            new_items = [i for i in items if i["guid"] not in existing][:PULSE_MAX_ITEMS]

            for item in new_items:
                try:
                    summary = _summarize(item)
                except Exception as exc:
                    log.warning("summarize failed for %s: %s", item["guid"], exc)
                    summary = None
                with eng.begin() as conn:
                    conn.execute(
                        text("""INSERT INTO lm_pulse_news
                                (guid, title, link, source, snippet, summary, model,
                                 published_at, summarized_at)
                                VALUES (:guid, :title, :link, :source, :snippet,
                                        :summary, :model, :published_at, :at)"""),
                        {**item, "summary": summary, "model": OLLAMA_MODEL, "at": _now()},
                    )

            with eng.begin() as conn:
                conn.execute(
                    text("""UPDATE lm_pulse_runs SET finished_at = :t, status = 'success',
                            items_fetched = :f, items_new = :n WHERE id = :id"""),
                    {"t": _now(), "f": len(items), "n": len(new_items), "id": run_id},
                )
            log.info("pulse refresh: %d fetched, %d new summarized", len(items), len(new_items))
            return {"status": "success", "items_fetched": len(items), "items_new": len(new_items)}
        except Exception as exc:
            with eng.begin() as conn:
                conn.execute(
                    text("UPDATE lm_pulse_runs SET finished_at = :t, status = 'error', "
                         "error = :e WHERE id = :id"),
                    {"t": _now(), "e": str(exc)[:500], "id": run_id},
                )
            log.exception("pulse refresh failed")
            return {"status": "error", "error": str(exc)}
    finally:
        _refresh_lock.release()


def is_running() -> bool:
    if _refresh_lock.acquire(blocking=False):
        _refresh_lock.release()
        return False
    return True


def get_news(limit: int = 30) -> dict:
    _ensure_tables()
    eng = get_engine()
    with eng.connect() as conn:
        rows = [
            dict(r._mapping)
            for r in conn.execute(
                text("""SELECT title, link, source, snippet, summary, model,
                               published_at, summarized_at
                        FROM lm_pulse_news
                        ORDER BY COALESCE(published_at, summarized_at) DESC
                        LIMIT :n"""),
                {"n": limit},
            )
        ]
        last_run = conn.execute(
            text("""SELECT started_at, finished_at, status, triggered_by,
                           items_fetched, items_new, error
                    FROM lm_pulse_runs ORDER BY id DESC LIMIT 1""")
        ).fetchone()
    return {
        "items": rows,
        "running": is_running(),
        "last_run": dict(last_run._mapping) if last_run else None,
    }

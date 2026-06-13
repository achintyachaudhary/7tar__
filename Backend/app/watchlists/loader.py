"""Fetch and cache NSE index / equity symbol lists."""

from __future__ import annotations

import csv
import json
import logging
import time
from io import StringIO
from pathlib import Path

import requests

from app.config import NIFTY_50_TICKERS
from app.utils.network import make_requests_session
from app.watchlists.indices import INDEX_META, IndexId

logger = logging.getLogger(__name__)

NSE_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Goldium/1.0)"}
INDICES_BASE = "https://nsearchives.nseindia.com/content/indices/"
EQUITY_LIST_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache"
WATCHLIST_CACHE_TTL = 86400  # 24 hours

_memory_cache: dict[str, tuple[float, list[str]]] = {}


def _to_yfinance_symbol(symbol: str) -> str:
    symbol = symbol.strip().upper()
    if not symbol:
        return ""
    if symbol.endswith(".NS"):
        return symbol
    return f"{symbol}.NS"


def _parse_index_csv(text: str) -> list[str]:
    reader = csv.DictReader(StringIO(text))
    symbols: list[str] = []
    for row in reader:
        raw = row.get("Symbol") or row.get("SYMBOL") or ""
        yf = _to_yfinance_symbol(raw)
        if yf:
            symbols.append(yf)
    return symbols


def _parse_equity_csv(text: str) -> list[str]:
    reader = csv.DictReader(StringIO(text))
    symbols: list[str] = []
    for row in reader:
        series = (row.get(" SERIES") or row.get("SERIES") or "").strip()
        if series != "EQ":
            continue
        raw = row.get("SYMBOL") or ""
        yf = _to_yfinance_symbol(raw)
        if yf:
            symbols.append(yf)
    return symbols


def _cache_path(index_id: IndexId) -> Path:
    return CACHE_DIR / f"{index_id.value}.json"


def _read_disk_cache(index_id: IndexId) -> list[str] | None:
    path = _cache_path(index_id)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
        if time.time() - payload.get("fetched_at", 0) > WATCHLIST_CACHE_TTL:
            return None
        symbols = payload.get("symbols", [])
        return [_to_yfinance_symbol(s) for s in symbols if s]
    except (json.JSONDecodeError, OSError):
        return None


def _write_disk_cache(index_id: IndexId, symbols: list[str]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(index_id)
    path.write_text(
        json.dumps({"fetched_at": time.time(), "symbols": symbols}, indent=0),
    )


def _fetch_index_csv(filename: str) -> list[str]:
    url = f"{INDICES_BASE}{filename}"
    response = make_requests_session().get(url, headers=NSE_HEADERS, timeout=30)
    response.raise_for_status()
    return _parse_index_csv(response.text)


def _fetch_all_nse_equity() -> list[str]:
    response = make_requests_session().get(EQUITY_LIST_URL, headers=NSE_HEADERS, timeout=60)
    response.raise_for_status()
    return _parse_equity_csv(response.text)


def _fetch_from_nse(index_id: IndexId) -> list[str]:
    if index_id == IndexId.NSE_ALL:
        return _fetch_all_nse_equity()

    meta = INDEX_META[index_id]
    filename = meta["csv"]
    if not filename:
        raise ValueError(f"No CSV configured for {index_id}")
    return _fetch_index_csv(filename)


def get_watchlist_count(index_id: IndexId) -> int | None:
    """Symbol count from memory/disk cache only (no network)."""
    cache_key = index_id.value
    mem = _memory_cache.get(cache_key)
    if mem:
        return len(mem[1])
    disk = _read_disk_cache(index_id)
    if disk:
        return len(disk)
    return None


def get_watchlist(index_id: IndexId | str = IndexId.NIFTY_50) -> list[str]:
    """Return yfinance symbols for the selected index, with disk + memory cache."""
    if isinstance(index_id, str):
        try:
            index_id = IndexId(index_id.lower())
        except ValueError:
            index_id = IndexId.NIFTY_50

    cache_key = index_id.value
    now = time.time()
    mem = _memory_cache.get(cache_key)
    if mem and now < mem[0]:
        return mem[1].copy()

    disk = _read_disk_cache(index_id)
    if disk:
        _memory_cache[cache_key] = (now + 300, disk)
        return disk.copy()

    try:
        symbols = _fetch_from_nse(index_id)
        if not symbols:
            raise ValueError("empty symbol list")
        _write_disk_cache(index_id, symbols)
        _memory_cache[cache_key] = (now + 300, symbols)
        logger.info("Loaded %d symbols for %s from NSE", len(symbols), index_id.value)
        return symbols.copy()
    except Exception:
        logger.exception("Failed to fetch watchlist for %s", index_id.value)
        if index_id == IndexId.NIFTY_50:
            return [_to_yfinance_symbol(s) for s in NIFTY_50_TICKERS]
        raise

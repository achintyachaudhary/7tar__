"""Upstox Analytics API client (read-only, long-lived analytics token).

Docs: https://upstox.com/developer/api-documentation/analytics-token/
Covered endpoints: IPO catalog, per-instrument news, fundamentals (income
statement, shareholding, profile, ratios). Symbol → ISIN / instrument-key
resolution uses Upstox's public NSE instrument master, cached on disk for a
day and in memory for the process lifetime.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

import requests

from app.utils.network import without_proxy

logger = logging.getLogger(__name__)

BASE_URL = "https://api.upstox.com/v2"
INSTRUMENTS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.csv.gz"

_CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "cache"
_INSTRUMENTS_CACHE = _CACHE_DIR / "upstox_nse_instruments.json"
_INSTRUMENTS_TTL = 86_400  # refresh the master daily

_REQUEST_TIMEOUT = 20

_instruments_lock = threading.Lock()
_instruments: dict[str, dict[str, str]] | None = None  # SYMBOL → {isin, instrument_key, name}


class UpstoxError(RuntimeError):
    """Raised when the Upstox API rejects a request or no token is configured."""


def get_token() -> str | None:
    token = os.getenv("UPSTOX_ANALYTICS_TOKEN", "").strip()
    return token or None


def is_configured() -> bool:
    return get_token() is not None


def _headers() -> dict[str, str]:
    token = get_token()
    if not token:
        raise UpstoxError("UPSTOX_ANALYTICS_TOKEN is not configured")
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{BASE_URL}{path}"
    with without_proxy():
        resp = requests.get(url, params=params, headers=_headers(), timeout=_REQUEST_TIMEOUT)
    if resp.status_code != 200:
        snippet = resp.text[:300]
        raise UpstoxError(f"Upstox GET {path} failed ({resp.status_code}): {snippet}")
    body = resp.json()
    if isinstance(body, dict) and body.get("status") == "error":
        raise UpstoxError(f"Upstox GET {path} returned error: {str(body)[:300]}")
    return body


# ── Instrument master (symbol → ISIN / instrument_key) ───────────────────────

def _load_instruments() -> dict[str, dict[str, str]]:
    global _instruments
    with _instruments_lock:
        if _instruments is not None:
            return _instruments

        if _INSTRUMENTS_CACHE.exists():
            try:
                payload = json.loads(_INSTRUMENTS_CACHE.read_text(encoding="utf-8"))
                if time.time() - payload.get("fetched_at", 0) < _INSTRUMENTS_TTL:
                    _instruments = payload["symbols"]
                    return _instruments
            except (json.JSONDecodeError, KeyError, OSError):
                pass

        logger.info("Downloading Upstox NSE instrument master")
        with without_proxy():
            resp = requests.get(INSTRUMENTS_URL, timeout=60)
        resp.raise_for_status()
        raw = gzip.decompress(resp.content).decode("utf-8", errors="replace")

        symbols: dict[str, dict[str, str]] = {}
        reader = csv.DictReader(io.StringIO(raw))
        for row in reader:
            if (row.get("instrument_type") or "").strip().upper() not in ("EQ", "EQUITY"):
                continue
            key = (row.get("instrument_key") or "").strip()  # e.g. NSE_EQ|INE002A01018
            tradingsymbol = (row.get("tradingsymbol") or row.get("trading_symbol") or "").strip()
            if not key or "|" not in key or not tradingsymbol:
                continue
            isin = key.split("|", 1)[1]
            symbols[tradingsymbol.upper()] = {
                "isin": isin,
                "instrument_key": key,
                "name": (row.get("name") or "").strip(),
            }

        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _INSTRUMENTS_CACHE.write_text(
            json.dumps({"fetched_at": time.time(), "symbols": symbols}),
            encoding="utf-8",
        )
        _instruments = symbols
        logger.info("Upstox instrument master loaded: %d NSE equities", len(symbols))
        return symbols


def _base_symbol(symbol: str) -> str:
    return symbol.upper().replace(".NS", "").replace(".BO", "").strip()


def resolve_instrument(symbol: str) -> dict[str, str] | None:
    """SYMBOL / SYMBOL.NS → {isin, instrument_key, name} or None.

    Falls back to the official NSE equity masters — Upstox endpoints key on
    ISIN, so any NSE-listed symbol resolves even when the Upstox instrument
    master lags a fresh listing.
    """
    try:
        hit = _load_instruments().get(_base_symbol(symbol))
        if hit:
            return hit
    except Exception:
        logger.exception("Upstox instrument master unavailable")

    try:
        from app.services.nse_symbol_master import resolve_symbol

        row = resolve_symbol(symbol)
        if row:
            return {
                "isin": row["isin"],
                "instrument_key": f"NSE_EQ|{row['isin']}",
                "name": row["name"],
            }
    except Exception:
        logger.exception("NSE symbol master fallback failed for %s", symbol)
    return None


def resolve_isin(symbol: str) -> str | None:
    inst = resolve_instrument(symbol)
    return inst["isin"] if inst else None


# ── IPO ───────────────────────────────────────────────────────────────────────

IPO_STATUSES = ("open", "upcoming", "closed", "listed")


def fetch_ipos(statuses: tuple[str, ...] = IPO_STATUSES) -> list[dict[str, Any]]:
    """All IPOs across the given statuses (paginated, 30 records per page)."""
    out: list[dict[str, Any]] = []
    for status in statuses:
        page = 1
        while True:
            body = _get(
                "/ipos",
                params={"status": status, "page_number": page, "records": 30},
            )
            rows = body.get("data") or []
            out.extend(rows)
            meta = ((body.get("meta_data") or {}).get("page")) or {}
            total_pages = int(meta.get("total_pages") or 1)
            if page >= total_pages or not rows:
                break
            page += 1
    return out


def fetch_ipo_details(ipo_id: str) -> dict[str, Any]:
    body = _get(f"/ipos/{ipo_id}")
    return body.get("data") or {}


# ── News ──────────────────────────────────────────────────────────────────────

def fetch_news(instrument_keys: list[str], *, page_size: int = 100) -> dict[str, list[dict]]:
    """instrument_key → articles. Max 30 keys per request (API limit)."""
    out: dict[str, list[dict]] = {}
    for i in range(0, len(instrument_keys), 30):
        chunk = instrument_keys[i : i + 30]
        body = _get(
            "/news",
            params={
                "category": "instrument_keys",
                "instrument_keys": ",".join(chunk),
                "page_size": page_size,
            },
        )
        data = body.get("data") or {}
        if isinstance(data, dict):
            for key, articles in data.items():
                if isinstance(articles, list):
                    out.setdefault(key, []).extend(articles)
    return out


# ── Market quotes ─────────────────────────────────────────────────────────────

INDEX_KEYS = {
    "nifty": "NSE_INDEX|Nifty 50",
    "banknifty": "NSE_INDEX|Nifty Bank",
    "sensex": "BSE_INDEX|SENSEX",
}

LTP_BATCH_LIMIT = 500


def fetch_ltp(instrument_keys: list[str]) -> dict[str, float]:
    """Batch last-traded prices: instrument_key → price (real-time during session).

    One request covers up to 500 instruments — vastly cheaper than per-symbol
    history calls. Results are keyed back by the instrument_token field since
    the response's top-level keys use the trading-symbol form.
    """
    out: dict[str, float] = {}
    for i in range(0, len(instrument_keys), LTP_BATCH_LIMIT):
        chunk = instrument_keys[i : i + LTP_BATCH_LIMIT]
        body = _get("/market-quote/ltp", params={"instrument_key": ",".join(chunk)})
        data = body.get("data") or {}
        for item in data.values():
            token = item.get("instrument_token")
            price = item.get("last_price")
            if token and price is not None:
                out[str(token)] = float(price)
    return out


# ── Fundamentals ──────────────────────────────────────────────────────────────

def fetch_income_statement(isin: str, *, time_period: str = "quarterly") -> list[dict[str, Any]]:
    """[{category: revenue|operating_profit|net_profit, history: [{period, value, change}]}]"""
    body = _get(
        f"/fundamentals/{isin}/income-statement",
        params={"time_period": time_period},
    )
    data = body.get("data") or {}
    return data.get("income_statement") or []


def fetch_share_holdings(isin: str) -> list[dict[str, Any]]:
    """[{category: promoters|fii|other_dii|mutual_funds|retail_and_other, history: [...]}]"""
    body = _get(f"/fundamentals/{isin}/share-holdings")
    return body.get("data") or []


def fetch_company_profile(isin: str) -> dict[str, Any]:
    body = _get(f"/fundamentals/{isin}/company-profile")
    return body.get("data") or {}


def fetch_key_ratios(isin: str) -> dict[str, Any]:
    body = _get(f"/fundamentals/{isin}/key-ratios")
    return body.get("data") or {}

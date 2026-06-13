"""Per-scan context: preloaded in-memory data so workers need no DB connections."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.db.database import SessionLocal

logger = logging.getLogger(__name__)

_local = threading.local()
_ctx_lock = threading.Lock()
_current_ctx: ScanContext | None = None

# Longest period any scanner may request — fallback when scan-specific period unknown
SCAN_PRELOAD_PERIOD = "5y"

_PERIOD_PRELOAD = {
    "3mo": "6mo",
    "6mo": "1y",
    "1y": "2y",
    "2y": "3y",
    "3y": "5y",
    "5y": "5y",
}


def preload_period_for_scan(scan_type: str, options: dict[str, Any] | None = None) -> str:
    """Choose DB preload window from scanner options (avoids loading 5y when scan uses 1y)."""
    opts = options or {}
    period = str(opts.get("period") or "")
    if period in _PERIOD_PRELOAD:
        return _PERIOD_PRELOAD[period]
    if scan_type == "multi_year":
        return "5y"
    if scan_type in ("golden", "weekly"):
        return "2y"
    return "1y"


@dataclass
class ScanContext:
    """Preloaded read-only maps shared across worker threads."""

    snapshots: dict[str, dict[str, Any]] = field(default_factory=dict)
    profiles: dict[str, dict[str, Any]] = field(default_factory=dict)
    daily_bars: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    financials_quarterly: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    holdings_history: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


def build_scan_context(
    db: Session,
    symbols: list[str],
    scan_type: str,
    *,
    preload_period: str | None = None,
) -> ScanContext:
    """Bulk-load all scan inputs on one DB connection before parallel workers start."""
    from app.db import crud
    from app.services.price_history import period_cutoff_date

    period = preload_period or SCAN_PRELOAD_PERIOD
    since = period_cutoff_date(period)
    logger.info(
        "Preloading scan data for %d symbols (period=%s)...",
        len(symbols),
        period,
    )

    daily_bars = crud.bulk_daily_ohlcv_bars(db, symbols, since_date=since)
    financials: dict[str, list[dict[str, Any]]] = {}
    holdings: dict[str, list[dict[str, Any]]] = {}
    if scan_type in ("golden", "weekly"):
        financials = crud.bulk_financials_quarterly(db, symbols)
        holdings = crud.bulk_holdings_history(db, symbols)

    logger.info(
        "Preload done: %d symbols with prices, %d with financials, %d with holdings",
        len(daily_bars),
        len(financials),
        len(holdings),
    )

    return ScanContext(
        snapshots=crud.snapshot_map(db),
        profiles=crud.profile_map(db, symbols),
        daily_bars=daily_bars,
        financials_quarterly=financials,
        holdings_history=holdings,
    )


def init_scan_context(ctx: ScanContext) -> None:
    global _current_ctx
    with _ctx_lock:
        _current_ctx = ctx


def get_scan_context() -> ScanContext | None:
    return _current_ctx


def clear_scan_context() -> None:
    global _current_ctx
    with _ctx_lock:
        _current_ctx = None


def normalize_symbol(symbol: str) -> str:
    sym = symbol.upper().strip()
    if not sym.endswith((".NS", ".BO")):
        return f"{sym}.NS"
    return sym


def symbol_meta(symbol: str) -> dict[str, Any]:
    """Resolve company meta from preloaded scan context."""
    sym = normalize_symbol(symbol)
    meta: dict[str, Any] = {
        "company_name": sym.replace(".NS", "").replace(".BO", ""),
        "industry": None,
        "market_cap_cr": None,
        "market_cap_category": None,
    }

    ctx = get_scan_context()
    if ctx:
        snap = ctx.snapshots.get(sym)
        if snap:
            meta["company_name"] = snap.get("company_name") or meta["company_name"]
            meta["industry"] = snap.get("industry")
            meta["market_cap_cr"] = snap.get("market_cap_cr")
        prof = ctx.profiles.get(sym)
        if prof:
            if prof.get("company_name"):
                meta["company_name"] = prof["company_name"]
            if not meta["industry"] and prof.get("industry"):
                meta["industry"] = prof["industry"]
            if meta["market_cap_cr"] is None and prof.get("market_cap_cr") is not None:
                meta["market_cap_cr"] = prof["market_cap_cr"]
            meta["market_cap_category"] = prof.get("cap_category")
        return meta

    from app.db import crud

    with SessionLocal() as db:
        snap = crud.get_day_scan_snapshot(db, sym)
        if snap:
            meta["company_name"] = snap.get("company_name") or meta["company_name"]
            meta["industry"] = snap.get("industry")
            meta["market_cap_cr"] = snap.get("market_cap_cr")
        profile = crud.get_profile(db, sym)
        if profile:
            if profile.company_name:
                meta["company_name"] = profile.company_name
            if not meta["industry"] and profile.industry:
                meta["industry"] = profile.industry
            if meta["market_cap_cr"] is None and profile.market_cap_cr:
                meta["market_cap_cr"] = profile.market_cap_cr
            meta["market_cap_category"] = profile.cap_category
    return meta

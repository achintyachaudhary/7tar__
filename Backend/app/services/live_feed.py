"""Live tick feed — Upstox LTP snapshots pushed to browsers over the app WebSocket.

During the NSE session a daemon thread polls the Upstox batch-LTP endpoint
every few seconds for the header indices, open portfolio positions, and
followed symbols, then broadcasts a single ``live:ticks`` message on /ws/app.
The browser gets socket-pushed, real-time prices; outside market hours the
thread idles. (The native Upstox websocket feed can replace the poller later
behind the same vendor capability — it needs protobuf decoding and is capped
at 100 instrument keys.)
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from app.utils.market_hours import is_nse_data_live

logger = logging.getLogger(__name__)

TICK_SECONDS = 3
IDLE_SECONDS = 30
SYMBOL_REFRESH_SECONDS = 60
MAX_EQUITY_KEYS = 300

# Sector/segment indices for the Market Pulse widget — streamed every tick,
# keyed by display label (the tile label, so the UI can match directly).
PULSE_INDEX_KEYS: dict[str, str] = {
    "NIFTY 50": "NSE_INDEX|Nifty 50",
    "NIFTY Bank": "NSE_INDEX|Nifty Bank",
    "NIFTY IT": "NSE_INDEX|Nifty IT",
    "NIFTY Pharma": "NSE_INDEX|Nifty Pharma",
    "NIFTY Auto": "NSE_INDEX|Nifty Auto",
    "NIFTY FMCG": "NSE_INDEX|Nifty FMCG",
    "NIFTY Metal": "NSE_INDEX|Nifty Metal",
    "NIFTY Midcap 50": "NSE_INDEX|Nifty Midcap 50",
    "NIFTY Smallcap 100": "NSE_INDEX|NIFTY SMLCAP 100",
}

_thread: threading.Thread | None = None
_started = threading.Event()

# Previous closes for change computation, loaded once per session day.
_prev_close: dict[str, float] = {}
_prev_close_day: str | None = None

# Symbols browsers asked to watch (dashboard widgets register what they
# display via the live:watch WS channel). TTL'd so closed tabs fall away.
WATCH_TTL_SECONDS = 120
_client_watch: dict[str, float] = {}  # symbol -> expires_at (monotonic-ish epoch)
_client_watch_lock = threading.Lock()


def register_watch_symbols(symbols: list[str]) -> int:
    """Add client-requested symbols to the tick stream for WATCH_TTL_SECONDS."""
    expires = time.time() + WATCH_TTL_SECONDS
    cleaned = [s.strip().upper() for s in symbols if isinstance(s, str) and s.strip()]
    with _client_watch_lock:
        for sym in cleaned:
            _client_watch[sym] = expires
        # Opportunistic purge keeps the dict from growing unbounded.
        now = time.time()
        for sym in [s for s, exp in _client_watch.items() if exp < now]:
            del _client_watch[sym]
    return len(cleaned)


def _client_watch_symbols() -> list[str]:
    now = time.time()
    with _client_watch_lock:
        return [s for s, exp in _client_watch.items() if exp >= now]


def _index_prev_closes() -> dict[str, float]:
    """Closes of the session before the current one, from the cached 1y bars."""
    import json

    from app.db import crud
    from app.db.database import SessionLocal
    from app.utils.market_hours import current_session_date

    global _prev_close_day
    session_cutoff = current_session_date().isoformat()
    if _prev_close_day == session_cutoff and _prev_close:
        return _prev_close

    out: dict[str, float] = {}
    with SessionLocal() as db:
        for index_id in ("nifty", "banknifty", "sensex"):
            row = crud.get_market_index(db, index_id)
            if row is None or not row.bars_json:
                continue
            try:
                bars = json.loads(row.bars_json)
            except ValueError:
                continue
            # Strictly before the live session — never the session's own bar.
            closes = [b for b in bars if str(b.get("time", ""))[:10] < session_cutoff]
            if closes:
                out[index_id] = float(closes[-1]["close"])
    if out:
        _prev_close.clear()
        _prev_close.update(out)
        _prev_close_day = session_cutoff
    return _prev_close


def _watch_symbols() -> list[str]:
    """Symbols a user watches live: open trades + candidates + followed stocks,
    plus whatever dashboard widgets registered via live:watch. Trading-critical
    sources come first so they survive the MAX_EQUITY_KEYS cap."""
    from app.db import crud
    from app.db.database import SessionLocal

    symbols: list[str] = []
    with SessionLocal() as db:
        try:
            trades = crud.list_live_trades(db, status="open")
            symbols.extend(t["symbol"] for t in trades)
        except Exception:
            logger.debug("live trades unavailable for live feed")
        try:
            symbols.extend(
                c["symbol"]
                for c in crud.list_live_candidates(db)
                if c.get("status") in ("watching", "armed", "in_trade")
            )
        except Exception:
            logger.debug("candidates unavailable for live feed")
        try:
            symbols.extend(crud.get_following_symbols(db))
        except Exception:
            logger.debug("following list unavailable for live feed")

    symbols.extend(_client_watch_symbols())

    seen: set[str] = set()
    unique = []
    for s in symbols:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    return unique[:MAX_EQUITY_KEYS]


def _build_tick_payload() -> dict[str, Any] | None:
    from app.services.vendors import upstox

    # One instrument can feed several targets (e.g. Nifty 50 is both the
    # header index "nifty" and the pulse tile "NIFTY 50").
    targets: dict[str, list[str]] = {}

    def add_target(key: str, target: str) -> None:
        targets.setdefault(key, []).append(target)

    for index_id, key in upstox.INDEX_KEYS.items():
        add_target(key, f"index:{index_id}")
    for label, key in PULSE_INDEX_KEYS.items():
        add_target(key, f"pulse:{label}")
    for sym in _watch_symbols():
        inst = upstox.resolve_instrument(sym)
        if inst:
            add_target(inst["instrument_key"], sym)

    prices = upstox.fetch_ltp(list(targets.keys()))
    if not prices:
        return None

    prev = _index_prev_closes()
    indices: dict[str, dict[str, float | None]] = {}
    pulse: dict[str, float] = {}
    quotes: dict[str, float] = {}
    for key, price in prices.items():
        for target in targets.get(key, ()):
            if target.startswith("index:"):
                index_id = target.split(":", 1)[1]
                prev_close = prev.get(index_id)
                change_abs = round(price - prev_close, 2) if prev_close else None
                change_pct = (
                    round((price - prev_close) / prev_close * 100, 2) if prev_close else None
                )
                indices[index_id] = {
                    "price": round(price, 2),
                    "change_abs": change_abs,
                    "change_pct": change_pct,
                }
            elif target.startswith("pulse:"):
                pulse[target.split(":", 1)[1]] = round(price, 2)
            else:
                quotes[target] = round(price, 2)

    return {
        "channel": "live:ticks",
        "market_open": True,
        "indices": indices,
        "pulse": pulse,
        "quotes": quotes,
        "ts": time.time(),
    }


def _run() -> None:
    from app.api.ws_hub import broadcast_sync
    from app.services.vendors import upstox
    from app.services.vendors.registry import use_upstox

    logger.info("Live tick feed thread started")
    failures = 0
    while True:
        try:
            # Pre-open included — first index/stock prints arrive from ~09:07.
            if not is_nse_data_live() or not use_upstox("live_quotes"):
                time.sleep(IDLE_SECONDS)
                continue
            if not upstox.is_configured():
                time.sleep(IDLE_SECONDS)
                continue

            payload = _build_tick_payload()
            if payload:
                broadcast_sync(payload)
                failures = 0
            time.sleep(TICK_SECONDS)
        except Exception:
            failures += 1
            logger.exception("Live tick feed iteration failed (%d in a row)", failures)
            # Back off hard on repeated failures (rate limits, outages).
            time.sleep(min(300, IDLE_SECONDS * max(1, failures)))


def start_live_feed() -> None:
    global _thread
    if _started.is_set():
        return
    _started.set()
    _thread = threading.Thread(target=_run, name="live-tick-feed", daemon=True)
    _thread.start()

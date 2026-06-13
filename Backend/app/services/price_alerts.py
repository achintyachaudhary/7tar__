"""Background price-alert checker — polls quotes and triggers email + WS beep."""

from __future__ import annotations

import logging
import threading
import time
from datetime import date, timedelta
from typing import Any

from app.db import crud
from app.db.database import SessionLocal
from app.services import notifier, stockrelay
from app.services.fetcher import fetch_history
from app.services.live_trading import _fetch_quotes

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 30
_checker_thread: threading.Thread | None = None
_stop_event = threading.Event()


def _normalize_symbol(symbol: str) -> str:
    sym = symbol.strip().upper()
    if not sym:
        return sym
    if sym.endswith((".NS", ".BO")):
        return sym
    return f"{sym}.NS"


def _is_triggered(direction: str, price: float, target: float) -> bool:
    if direction == "below":
        return price <= target
    return price >= target


def _change_7d_pct(symbol: str, ltp: float, db: Any) -> float | None:
    """Percent change from the close 7 trading sessions before today to *ltp*."""
    since = date.today() - timedelta(days=21)
    bars = crud.get_daily_ohlcv_bars(db, symbol, since_date=since)
    ref: float | None = None
    if len(bars) >= 7:
        ref = float(bars[-7]["close"])
    else:
        df = fetch_history(symbol, period="15d", interval="1d", min_rows=8)
        if df is not None and len(df) >= 8:
            ref = float(df.iloc[-8]["close"])
    if ref is None or ref <= 0:
        return None
    return round((ltp - ref) / ref * 100, 2)


def enrich_alerts_with_market_data(alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach LTP, day %, and 7-session % to active alerts."""
    active_symbols = list(
        {_normalize_symbol(a["symbol"]) for a in alerts if a.get("active")}
    )
    if not active_symbols:
        return alerts

    quotes = _fetch_quotes(active_symbols)
    market_by_symbol: dict[str, dict[str, float | None]] = {}

    with SessionLocal() as db:
        for sym in active_symbols:
            quote = quotes.get(sym)
            if not quote:
                market_by_symbol[sym] = {
                    "ltp": None,
                    "change_day_pct": None,
                    "change_7d_pct": None,
                }
                continue
            ltp = float(quote["price"])
            prev = crud._cached_prev_close(sym, db)
            day_pct = (
                round((ltp - prev) / prev * 100, 2) if prev and prev > 0 else None
            )
            market_by_symbol[sym] = {
                "ltp": round(ltp, 2),
                "change_day_pct": day_pct,
                "change_7d_pct": _change_7d_pct(sym, ltp, db),
            }

    enriched: list[dict[str, Any]] = []
    for alert in alerts:
        if not alert.get("active"):
            enriched.append(alert)
            continue
        sym = _normalize_symbol(alert["symbol"])
        enriched.append({**alert, **market_by_symbol.get(sym, {})})
    return enriched


def _broadcast_alert_triggered(alert: dict[str, Any]) -> None:
    try:
        from app.api.ws_hub import broadcast_sync

        broadcast_sync({
            "channel": "alert:triggered",
            "alert": alert,
        })
    except Exception:
        logger.exception("Failed to broadcast price alert")


def check_price_alerts_once() -> int:
    """Evaluate all active alerts against latest quotes. Returns trigger count."""
    with SessionLocal() as db:
        alerts = crud.list_price_alerts(db, active_only=True)
    if not alerts:
        return 0

    symbols = list({_normalize_symbol(a["symbol"]) for a in alerts})
    quotes = _fetch_quotes(symbols)
    triggered_count = 0

    for alert in alerts:
        sym = _normalize_symbol(alert["symbol"])
        quote = quotes.get(sym)
        if not quote:
            continue
        price = float(quote["price"])
        target = float(alert["target_price"])
        if not _is_triggered(alert.get("direction", "above"), price, target):
            continue

        with SessionLocal() as db:
            updated = crud.mark_price_alert_triggered(
                db,
                alert["id"],
                triggered_price=price,
            )
        if not updated:
            continue

        triggered_count += 1
        updated["triggered_price"] = price
        notifier.notify_price_alert(updated)
        stockrelay.push_price_alert_trigger(updated, triggered_price=price)
        _broadcast_alert_triggered(updated)
        logger.info(
            "Price alert triggered: %s %s Rs.%.2f (target Rs.%.2f)",
            sym,
            alert.get("direction", "above"),
            price,
            target,
        )

    return triggered_count


def _checker_loop() -> None:
    logger.info("Price alert checker started (every %ss)", CHECK_INTERVAL_SECONDS)
    while not _stop_event.is_set():
        try:
            check_price_alerts_once()
        except Exception:
            logger.exception("Price alert check failed")
        _stop_event.wait(CHECK_INTERVAL_SECONDS)


def start_price_alert_checker() -> None:
    """Start the background price-alert polling thread (idempotent)."""
    global _checker_thread
    if _checker_thread is not None and _checker_thread.is_alive():
        return
    _stop_event.clear()
    _checker_thread = threading.Thread(
        target=_checker_loop,
        name="price-alert-checker",
        daemon=True,
    )
    _checker_thread.start()


def stop_price_alert_checker() -> None:
    _stop_event.set()

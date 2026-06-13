"""Push trigger and EOD messages to StockRelay for the Goldium iOS feed.

Configuration (Backend/.env):
- STOCKRELAY_URL:     ingest endpoint (default https://srelay.onrender.com/api/v1/ingest)
- STOCKRELAY_ENABLED: set false to disable pushes
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_DEFAULT_URL = "https://srelay.onrender.com/api/v1/ingest"
_BACKEND_ENV = Path(__file__).resolve().parents[2] / ".env"
_sent_ids: set[str] = set()


def _reload_env() -> None:
    load_dotenv(_BACKEND_ENV, override=True)


def _config() -> tuple[str, bool]:
    _reload_env()
    url = (os.environ.get("STOCKRELAY_URL") or _DEFAULT_URL).strip()
    enabled = (os.environ.get("STOCKRELAY_ENABLED") or "true").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )
    return url, enabled


def _now_ist() -> datetime:
    from zoneinfo import ZoneInfo

    return datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Kolkata"))


def _ist_date_str() -> str:
    return _now_ist().strftime("%Y-%m-%d")


def _symbol_display(symbol: str) -> str:
    return symbol.replace(".NS", "").replace(".BO", "").upper()


def _fmt_inr(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"₹{value:,.2f}"


def _get_nifty() -> dict[str, float]:
    try:
        from app.services.market_indices import list_market_indices

        for row in list_market_indices(refresh_if_stale=True):
            if row.get("index_id") == "nifty" and row.get("last_value") is not None:
                return {
                    "value": float(row["last_value"]),
                    "change_percent_today": float(row.get("change_pct") or 0.0),
                }
    except Exception:
        logger.exception("Failed to fetch NIFTY for StockRelay")
    return {"value": 0.0, "change_percent_today": 0.0}


def _stock_meta(
    symbol: str,
    db: Any,
    *,
    company_name: str | None = None,
) -> tuple[str, str]:
    display = _symbol_display(symbol)
    name = (company_name or display).strip() or display
    industry = "Unknown"
    try:
        from app.db import crud

        profile = crud.get_profile(db, symbol)
        if profile:
            if profile.company_name:
                name = profile.company_name
            industry = profile.industry or profile.sector or "Unknown"
    except Exception:
        logger.debug("Stock profile lookup failed for %s", symbol)
    return name, industry


def _change_percent_today(symbol: str, price: float, db: Any) -> float:
    try:
        from app.db import crud

        prev = crud._cached_prev_close(symbol, db)
        if prev and prev > 0:
            return round((price - prev) / prev * 100, 2)
    except Exception:
        logger.debug("Prev close lookup failed for %s", symbol)
    return 0.0


def push_message(payload: dict[str, Any]) -> bool:
    """POST a message to StockRelay. Returns True on success; never raises."""
    url, enabled = _config()
    if not enabled:
        logger.debug("StockRelay disabled; skipping push type=%s", payload.get("type"))
        return False

    msg_id = payload.get("id")
    if msg_id and msg_id in _sent_ids:
        logger.debug("StockRelay dedup skip id=%s", msg_id)
        return False

    try:
        resp = requests.post(url, json=payload, timeout=10)
    except Exception:
        logger.exception("StockRelay request failed for type=%s", payload.get("type"))
        return False

    if resp.status_code not in (200, 201):
        logger.warning(
            "StockRelay push failed type=%s status=%s body=%s",
            payload.get("type"),
            resp.status_code,
            resp.text[:300],
        )
        return False

    if msg_id:
        _sent_ids.add(msg_id)
    logger.info("StockRelay push ok type=%s id=%s", payload.get("type"), msg_id)
    return True


def push_trigger(
    *,
    msg_id: str,
    symbol: str,
    company_name: str | None,
    current_price: float,
    direction: str,
    threshold: float | None,
    label: str,
    db: Any | None = None,
) -> bool:
    from app.db.database import SessionLocal

    with SessionLocal() as session:
        name, industry = _stock_meta(symbol, session, company_name=company_name)
        change_pct = _change_percent_today(symbol, current_price, session)

    nifty = _get_nifty()
    payload = {
        "id": msg_id,
        "type": "trigger",
        "timestamp": _now_ist().isoformat(),
        "stock": {
            "symbol": _symbol_display(symbol),
            "name": name,
            "current_price": round(current_price, 2),
            "change_percent_today": change_pct,
            "industry": industry,
        },
        "alert": {
            "direction": direction,
            "threshold": threshold,
            "label": label,
        },
        "nifty": {
            "value": nifty["value"],
            "change_percent_today": nifty["change_percent_today"],
        },
    }
    return push_message(payload)


def push_price_alert_trigger(alert: dict[str, Any], *, triggered_price: float) -> bool:
    sym = alert.get("symbol") or ""
    direction = alert.get("direction", "above")
    target = float(alert.get("target_price") or 0)
    display = _symbol_display(sym)
    verb = "moved above" if direction == "above" else "dropped below"
    label = f"{display} {verb} {_fmt_inr(target)}"
    date_key = _ist_date_str().replace("-", "")
    return push_trigger(
        msg_id=f"trigger_alert_{alert.get('id')}_{date_key}",
        symbol=sym,
        company_name=alert.get("company_name"),
        current_price=triggered_price,
        direction=direction,
        threshold=target,
        label=label,
    )


def push_resistance_approach(candidate: Any, price: float) -> bool:
    sym = candidate.symbol
    resistance = float(candidate.resistance)
    display = _symbol_display(sym)
    date_key = _ist_date_str()
    return push_trigger(
        msg_id=f"trigger_armed_{display}_{date_key}",
        symbol=sym,
        company_name=candidate.company_name,
        current_price=price,
        direction="up",
        threshold=resistance,
        label=f"{display} approaching resistance {_fmt_inr(resistance)}",
    )


def push_trade_entered(
    candidate: Any,
    price: float,
    entry_signal: str,
    *,
    entry_signal_id: str | None = None,
) -> bool:
    sym = candidate.symbol
    resistance = float(candidate.resistance)
    display = _symbol_display(sym)
    date_key = _ist_date_str()
    sig_suffix = (entry_signal_id or "")[:8] or "entry"
    return push_trigger(
        msg_id=f"trigger_entry_{display}_{date_key}_{sig_suffix}",
        symbol=sym,
        company_name=candidate.company_name,
        current_price=price,
        direction="above",
        threshold=resistance,
        label=entry_signal.strip(),
    )


def push_trade_exited(trade: dict[str, Any]) -> bool:
    sym = trade.get("symbol") or ""
    display = _symbol_display(sym)
    exit_price = float(trade.get("exit_price") or trade.get("last_price") or 0)
    pnl_pct = float(trade.get("pnl_pct") or 0)
    pnl_abs = float(trade.get("pnl_abs") or 0)
    direction = "up" if pnl_abs >= 0 else "down"
    sign = "PROFIT" if pnl_abs >= 0 else "LOSS"
    date_key = _ist_date_str()
    trade_id = trade.get("id", "unknown")
    return push_trigger(
        msg_id=f"trigger_exit_{display}_{date_key}_{trade_id}",
        symbol=sym,
        company_name=trade.get("company_name"),
        current_price=exit_price,
        direction=direction,
        threshold=None,
        label=f"{display} exited @ {_fmt_inr(exit_price)} ({sign} {pnl_pct:+.2f}%)",
    )


def _pnl_status(value: float) -> str:
    if value > 0:
        return "profit"
    if value < 0:
        return "loss"
    return "flat"


def _trade_today_pnl(trade: Any, db: Any) -> tuple[float, float]:
    """Return (today_pnl, today_value_base) for one open trade."""
    from app.db import crud

    qty = float(trade.qty or 0)
    entry = float(trade.entry_price or 0)
    lp = float(trade.last_price or entry)
    entry_day = crud._ist_date(trade.entry_time)
    today_ist = _now_ist().date()

    if entry_day == today_ist:
        today_pnl = qty * (lp - entry)
        today_base = qty * entry
    else:
        prev = crud._cached_prev_close(trade.symbol, db)
        if prev is not None:
            today_pnl = qty * (lp - prev)
            today_base = qty * prev
        else:
            today_pnl = 0.0
            today_base = qty * lp

    return today_pnl, today_base


def push_eod_from_portfolio() -> bool:
    """Build and push eod_summary aggregated across all strategy wallets."""
    from app.db import crud
    from app.db.database import SessionLocal
    from app.services.live_trading import STRATEGIES

    date_key = _ist_date_str()

    with SessionLocal() as db:
        total_invested = 0.0
        total_current = 0.0
        total_today_pnl = 0.0
        total_today_base = 0.0

        for strat in STRATEGIES:
            summary = crud.get_portfolio_summary(db, strat["key"])
            total_invested += summary["starting_capital"]
            total_current += summary["portfolio_equity"]
            total_today_pnl += summary["today_pnl"]

            open_rows = crud.list_open_live_trades(db, strat["key"])
            for trade in open_rows:
                _, base = _trade_today_pnl(trade, db)
                total_today_base += base

            from app.db.models import LiveTrade

            today_ist = _now_ist().date()
            closed_rows = (
                db.query(LiveTrade)
                .filter(
                    LiveTrade.status == "closed",
                    LiveTrade.strategy == strat["key"],
                )
                .all()
            )
            for trade in closed_rows:
                if crud._ist_date(trade.exit_time) == today_ist:
                    total_today_base += float(trade.qty or 0) * float(
                        trade.entry_price or 0
                    )

        open_trades = crud.list_open_live_trades(db)
        by_symbol: dict[str, dict[str, Any]] = {}

        for trade in open_trades:
            sym = trade.symbol
            qty = float(trade.qty or 0)
            entry = float(trade.entry_price or 0)
            lp = float(trade.last_price or entry)
            invested = qty * entry
            current = qty * lp
            today_pnl, _ = _trade_today_pnl(trade, db)

            if sym not in by_symbol:
                name, _ = _stock_meta(sym, db, company_name=trade.company_name)
                by_symbol[sym] = {
                    "symbol": _symbol_display(sym),
                    "name": name,
                    "invested": 0.0,
                    "current_value": 0.0,
                    "today_pnl": 0.0,
                    "today_base": 0.0,
                }

            row = by_symbol[sym]
            row["invested"] += invested
            row["current_value"] += current
            row["today_pnl"] += today_pnl
            _, base = _trade_today_pnl(trade, db)
            row["today_base"] += base

        stocks = []
        for row in by_symbol.values():
            today_pct = (
                round(row["today_pnl"] / row["today_base"] * 100, 2)
                if row["today_base"] > 0
                else 0.0
            )
            stocks.append(
                {
                    "symbol": row["symbol"],
                    "name": row["name"],
                    "invested": round(row["invested"], 2),
                    "current_value": round(row["current_value"], 2),
                    "today_pnl": round(row["today_pnl"], 2),
                    "today_pnl_percent": today_pct,
                    "status": _pnl_status(row["today_pnl"]),
                }
            )

    today_pnl_percent = (
        round(total_today_pnl / total_today_base * 100, 2)
        if total_today_base > 0
        else 0.0
    )

    payload = {
        "id": f"eod_{date_key}",
        "type": "eod_summary",
        "timestamp": _now_ist().isoformat(),
        "date": date_key,
        "portfolio": {
            "invested": round(total_invested, 2),
            "current_value": round(total_current, 2),
            "today_pnl": round(total_today_pnl, 2),
            "today_pnl_percent": today_pnl_percent,
        },
        "stocks": stocks,
    }
    return push_message(payload)

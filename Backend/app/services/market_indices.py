"""NIFTY, BANKNIFTY, SENSEX quotes and 1Y daily OHLCV cached in SQLite."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
import yfinance as yf

from app.db import crud
from app.db.database import SessionLocal
from app.utils.market_hours import is_nse_data_live, last_nse_close
from app.utils.network import without_proxy

logger = logging.getLogger(__name__)

# During the NSE session quotes refresh almost every poll. After close, a
# quote is stale only if it was fetched BEFORE the final 15:30 IST close —
# the first post-close request captures the true end-of-day value, and no
# further fetches happen until the next session.
QUOTE_STALE_LIVE_MINUTES = 2
BARS_STALE_HOURS = 24

MARKET_INDEX_CONFIG: dict[str, dict[str, str]] = {
    "nifty": {"display_name": "NIFTY", "yf_symbol": "^NSEI"},
    "banknifty": {"display_name": "BANKNIFTY", "yf_symbol": "^NSEBANK"},
    "sensex": {"display_name": "SENSEX", "yf_symbol": "^BSESN"},
}

INDEX_ORDER = ("nifty", "banknifty", "sensex")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_stale(dt: datetime | None, *, minutes: int = 0, hours: int = 0) -> bool:
    if dt is None:
        return True
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = timedelta(minutes=minutes, hours=hours)
    return _now() - dt > delta


def _bar_time_daily(idx) -> str:
    if hasattr(idx, "to_pydatetime"):
        dt = idx.to_pydatetime()
    else:
        dt = idx
    return dt.strftime("%Y-%m-%d")


def _history_to_bars(df: pd.DataFrame) -> list[dict[str, Any]]:
    df = df.copy()
    df.columns = [str(c).lower().replace(" ", "_") for c in df.columns]
    bars: list[dict[str, Any]] = []
    for idx, row in df.iterrows():
        try:
            o, h, l, c = (
                float(row["open"]),
                float(row["high"]),
                float(row["low"]),
                float(row["close"]),
            )
        except (KeyError, TypeError, ValueError):
            continue
        if any(pd.isna(x) for x in (o, h, l, c)):
            continue
        vol = row.get("volume")
        volume = int(vol) if vol is not None and not pd.isna(vol) else None
        bars.append(
            {
                "time": _bar_time_daily(idx),
                "open": round(o, 4),
                "high": round(h, 4),
                "low": round(l, 4),
                "close": round(c, 4),
                "volume": volume,
            }
        )
    return bars


def _quote_from_history(hist: pd.DataFrame, cfg: dict[str, str]) -> dict[str, Any]:
    latest_close = float(hist["Close"].iloc[-1])
    prev_close = (
        float(hist["Close"].iloc[-2]) if len(hist) >= 2 else latest_close
    )
    change_abs = round(latest_close - prev_close, 2)
    change_pct = (
        round((latest_close - prev_close) / prev_close * 100, 2)
        if prev_close
        else 0.0
    )
    return {
        "last_value": round(latest_close, 2),
        "change_abs": change_abs,
        "change_pct": change_pct,
    }


def _fetch_quote_upstox(index_id: str) -> dict[str, Any] | None:
    """Real-time index LTP from Upstox; change computed vs the cached prior close."""
    import json

    from app.services.vendors import upstox

    key = upstox.INDEX_KEYS.get(index_id)
    if key is None:
        return None
    prices = upstox.fetch_ltp([key])
    price = prices.get(key)
    if price is None or price <= 0:
        return None

    from app.utils.market_hours import current_session_date

    # Previous close = last bar BEFORE the session this LTP belongs to.
    # (Comparing against calendar-today breaks after midnight and whenever the
    # cached bars lag a session — change then spans two days.)
    session_cutoff = current_session_date().isoformat()
    prev_close = None
    with SessionLocal() as db:
        row = crud.get_market_index(db, index_id)
        if row is not None and row.bars_json:
            try:
                bars = [
                    b
                    for b in json.loads(row.bars_json)
                    if str(b.get("time", ""))[:10] < session_cutoff
                ]
                if bars:
                    prev_close = float(bars[-1]["close"])
            except (ValueError, KeyError, TypeError):
                prev_close = None
    if not prev_close:
        return None

    return {
        "last_value": round(price, 2),
        "change_abs": round(price - prev_close, 2),
        "change_pct": round((price - prev_close) / prev_close * 100, 2),
    }


def _fetch_quote(index_id: str) -> dict[str, Any]:
    """Light quote fetch — Upstox real-time LTP first, yfinance daily bars fallback."""
    from app.services.vendors.registry import use_upstox

    if use_upstox("market_indices"):
        try:
            quote = _fetch_quote_upstox(index_id)
            if quote is not None:
                return quote
        except Exception:
            logger.exception("Upstox index quote failed for %s — yfinance fallback", index_id)

    cfg = MARKET_INDEX_CONFIG[index_id]
    with without_proxy():
        hist = yf.Ticker(cfg["yf_symbol"]).history(
            period="5d", interval="1d", auto_adjust=True
        )
    if hist is None or hist.empty:
        raise ValueError(f"No quote data for {cfg['display_name']}")
    return _quote_from_history(hist, cfg)


def _fetch_bars(index_id: str) -> dict[str, Any]:
    """Heavy fetch — full 1y daily history for the chart cache."""
    cfg = MARKET_INDEX_CONFIG[index_id]
    with without_proxy():
        hist = yf.Ticker(cfg["yf_symbol"]).history(
            period="1y", interval="1d", auto_adjust=True
        )
    if hist is None or hist.empty:
        raise ValueError(f"No market data for {cfg['display_name']}")
    bars = _history_to_bars(hist)
    if not bars:
        raise ValueError(f"No OHLC bars for {cfg['display_name']}")
    return {"bars": bars, **_quote_from_history(hist, cfg)}


def _quote_is_stale(quote_updated_at: datetime | None) -> bool:
    if quote_updated_at is None:
        return True
    if is_nse_data_live():  # pre-open prints count as live data
        return _is_stale(quote_updated_at, minutes=QUOTE_STALE_LIVE_MINUTES)
    # Market closed: stale only if the cached quote predates the final close.
    ts = quote_updated_at
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts < last_nse_close()


def refresh_market_index(index_id: str, *, force: bool = False) -> None:
    index_id = index_id.lower()
    if index_id not in MARKET_INDEX_CONFIG:
        raise ValueError(f"Unknown index: {index_id}")
    cfg = MARKET_INDEX_CONFIG[index_id]

    with SessionLocal() as db:
        row = crud.get_market_index(db, index_id)
        quote_stale = force or _quote_is_stale(row.quote_updated_at if row else None)
        bars_stale = force or _is_stale(
            row.bars_updated_at if row else None, hours=BARS_STALE_HOURS
        )
        if row and not quote_stale and not bars_stale:
            return

    now = _now()
    try:
        if bars_stale:
            fetched = _fetch_bars(index_id)
        else:
            fetched = _fetch_quote(index_id)
    except Exception:
        logger.exception("Market index fetch failed for %s", index_id)
        raise

    with SessionLocal() as db:
        kwargs: dict[str, Any] = {
            "index_id": index_id,
            "display_name": cfg["display_name"],
            "yf_symbol": cfg["yf_symbol"],
            "last_value": fetched["last_value"],
            "change_abs": fetched["change_abs"],
            "change_pct": fetched["change_pct"],
            "quote_updated_at": now,
        }
        if "bars" in fetched:
            kwargs["bars_json"] = json.dumps(fetched["bars"])
            kwargs["bars_updated_at"] = now
        crud.upsert_market_index(db, **kwargs)


def ensure_market_indices_refreshed(*, force: bool = False) -> None:
    for index_id in INDEX_ORDER:
        try:
            refresh_market_index(index_id, force=force)
        except Exception as exc:
            logger.warning("Could not refresh %s: %s", index_id, exc)


def list_market_indices(*, refresh_if_stale: bool = True) -> list[dict[str, Any]]:
    if refresh_if_stale:
        ensure_market_indices_refreshed()

    result: list[dict[str, Any]] = []
    with SessionLocal() as db:
        for index_id in INDEX_ORDER:
            row = crud.get_market_index(db, index_id)
            if row is None:
                result.append(
                    {
                        "index_id": index_id,
                        "display_name": MARKET_INDEX_CONFIG[index_id]["display_name"],
                        "yf_symbol": MARKET_INDEX_CONFIG[index_id]["yf_symbol"],
                        "last_value": None,
                        "change_abs": None,
                        "change_pct": None,
                        "updated_at": None,
                    }
                )
                continue
            result.append(
                {
                    "index_id": row.index_id,
                    "display_name": row.display_name,
                    "yf_symbol": row.yf_symbol,
                    "last_value": row.last_value,
                    "change_abs": row.change_abs,
                    "change_pct": row.change_pct,
                    "updated_at": row.quote_updated_at.isoformat()
                    if row.quote_updated_at
                    else None,
                }
            )
    return result


def get_market_index_chart(index_id: str) -> dict[str, Any]:
    index_id = index_id.lower()
    if index_id not in MARKET_INDEX_CONFIG:
        raise ValueError(f"Unknown index: {index_id}")

    with SessionLocal() as db:
        row = crud.get_market_index(db, index_id)

    if row is None or _is_stale(row.bars_updated_at, hours=BARS_STALE_HOURS):
        refresh_market_index(index_id)
        with SessionLocal() as db:
            row = crud.get_market_index(db, index_id)

    if row is None or not row.bars_json:
        return {
            "index_id": index_id,
            "display_name": MARKET_INDEX_CONFIG[index_id]["display_name"],
            "yf_symbol": MARKET_INDEX_CONFIG[index_id]["yf_symbol"],
            "timeframe": "1Y",
            "interval": "1d",
            "bars": [],
        }

    bars = json.loads(row.bars_json)
    return {
        "index_id": index_id,
        "display_name": row.display_name,
        "yf_symbol": row.yf_symbol,
        "timeframe": "1Y",
        "interval": "1d",
        "bars": bars,
    }

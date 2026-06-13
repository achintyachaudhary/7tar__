"""Day scan: fetch daily prices + fundamentals, store time series, compute returns."""

from __future__ import annotations

import logging
import threading
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pandas as pd
import yfinance as yf

from app.config import DAY_SCAN_HISTORY_YEARS, SCAN_MAX_WORKERS_LARGE, YFINANCE_REQUEST_DELAY
from app.db import crud
from app.db.database import SessionLocal
from app.utils.network import without_proxy

logger = logging.getLogger(__name__)

FUNDAMENTALS_STALE_DAYS = 7

_job_lock = threading.Lock()
_job_state: dict[str, Any] = {
    "running": False,
    "total": 0,
    "processed": 0,
    "fetched": 0,
    "skipped": 0,
    "failed": 0,
    "current_symbol": "",
    "started_at": None,
    "completed_at": None,
    "error": None,
}

_listing_job_lock = threading.Lock()
_listing_job_state: dict[str, Any] = {
    "running": False,
    "total": 0,
    "processed": 0,
    "fetched": 0,
    "skipped": 0,
    "failed": 0,
    "current_symbol": "",
    "started_at": None,
    "completed_at": None,
    "error": None,
}


def get_job_status() -> dict[str, Any]:
    with _job_lock:
        return dict(_job_state)


def get_listing_job_status() -> dict[str, Any]:
    with _listing_job_lock:
        state = dict(_listing_job_state)
    with SessionLocal() as db:
        total = crud.count_stock_universe(db, active_only=True)
        completed = crud.count_listing_fetched(db, active_only=True)
    state["listing_total"] = total
    state["listing_completed"] = completed
    state["all_listing_done"] = total > 0 and completed >= total
    return state


def _set_job(**kwargs: Any) -> None:
    with _job_lock:
        _job_state.update(kwargs)


def _set_listing_job(**kwargs: Any) -> None:
    with _listing_job_lock:
        _listing_job_state.update(kwargs)


def _normalize_symbol(symbol: str) -> str:
    symbol = symbol.upper().strip()
    if not symbol.endswith((".NS", ".BO")):
        return f"{symbol}.NS"
    return symbol


def _today_str() -> str:
    return date.today().isoformat()


def _previous_trading_date(ref: date | None = None) -> str:
    """Last NSE trading day before ref (skips weekends)."""
    ref = ref or date.today()
    d = ref - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.isoformat()


def get_sync_status() -> dict[str, Any]:
    """Return whether day-scan prices are synced through the previous trading day."""
    expected = _previous_trading_date()
    job = get_job_status()

    with SessionLocal() as db:
        stats = crud.get_day_scan_sync_stats(db)
        universe_count = crud.count_stock_universe(db, active_only=True)

    max_through = stats["max_prices_through_date"]
    min_through = stats["min_prices_through_date"]
    snapshot_count = stats["snapshot_count"]

    # Use max date as "synced through" when most stocks are current
    sync_through_date = max_through
    needs_sync = (
        not job["running"]
        and (
            snapshot_count == 0
            or sync_through_date is None
            or sync_through_date < expected
            or snapshot_count < universe_count
        )
    )

    last_sync_at = job.get("completed_at") or stats.get("last_updated_at")

    return {
        "expected_through_date": expected,
        "sync_through_date": sync_through_date,
        "min_prices_through_date": min_through,
        "snapshot_count": snapshot_count,
        "universe_count": universe_count,
        "needs_sync": needs_sync,
        "last_sync_at": last_sync_at,
        "running": job["running"],
    }


def start_day_scan_fetch_if_needed(force: bool = False) -> dict[str, Any]:
    """Start fetch only when not running and sync is stale (unless force)."""
    sync = get_sync_status()
    if not force and not sync["needs_sync"]:
        return {"status": "up_to_date", **sync, **get_job_status()}
    return start_day_scan_fetch(force=force)


def _is_fundamentals_stale(dt: datetime | None) -> bool:
    if dt is None:
        return True
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - dt > timedelta(days=FUNDAMENTALS_STALE_DAYS)


def _extract_roce(info: dict[str, Any]) -> float | None:
    """Best-effort ROCE from yfinance info (ROCE or ROE proxy)."""
    for key in ("returnOnCapitalEmployed", "returnOnEquity"):
        val = info.get(key)
        if val is None:
            continue
        try:
            pct = float(val)
            if abs(pct) <= 1:
                pct *= 100
            return round(pct, 2)
        except (TypeError, ValueError):
            continue
    return None


def _extract_pe(info: dict[str, Any]) -> float | None:
    for key in ("trailingPE", "forwardPE"):
        val = info.get(key)
        if val is None:
            continue
        try:
            return round(float(val), 2)
        except (TypeError, ValueError):
            continue
    return None


def _df_to_bars(df: pd.DataFrame) -> list[dict[str, Any]]:
    bars: list[dict[str, Any]] = []
    for idx, row in df.iterrows():
        try:
            close = float(row["close"])
        except (KeyError, TypeError, ValueError):
            continue
        if pd.isna(close):
            continue
        trade_date = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
        bars.append(
            {
                "trade_date": trade_date,
                "open": round(float(row["open"]), 4) if "open" in row and not pd.isna(row["open"]) else None,
                "high": round(float(row["high"]), 4) if "high" in row and not pd.isna(row["high"]) else None,
                "low": round(float(row["low"]), 4) if "low" in row and not pd.isna(row["low"]) else None,
                "close": round(close, 4),
                "volume": int(row["volume"]) if "volume" in row and not pd.isna(row["volume"]) else None,
            }
        )
    return bars


def _target_history_start(today: str) -> str:
    dt = datetime.strptime(today, "%Y-%m-%d").date()
    # Approximate: 365 days/year; good enough for backfill boundary
    return (dt - timedelta(days=365 * DAY_SCAN_HISTORY_YEARS)).isoformat()


def _fetch_prices_from_api(
    symbol: str,
    *,
    start: str | None = None,
    last_date: str | None = None,
    period: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch price history from yfinance."""
    try:
        with without_proxy():
            ticker = yf.Ticker(symbol)
            if start:
                df = ticker.history(start=start, auto_adjust=True)
            elif last_date:
                inc_start = (
                    datetime.strptime(last_date, "%Y-%m-%d").date() + timedelta(days=1)
                ).isoformat()
                df = ticker.history(start=inc_start, auto_adjust=True)
            elif period:
                df = ticker.history(period=period, auto_adjust=True)
            else:
                df = ticker.history(period=f"{DAY_SCAN_HISTORY_YEARS}y", auto_adjust=True)
    except Exception:
        logger.exception("Price fetch failed for %s", symbol)
        return []
    finally:
        if YFINANCE_REQUEST_DELAY > 0:
            import time
            time.sleep(YFINANCE_REQUEST_DELAY)

    if df is None or df.empty:
        return []

    df = df.copy()
    df.columns = [str(c).lower().replace(" ", "_") for c in df.columns]
    return _df_to_bars(df)


def _get_listing_start_date(symbol: str) -> str | None:
    """Best-effort listing / first-trade date from yfinance metadata."""
    try:
        with without_proxy():
            info = yf.Ticker(symbol).info or {}
    except Exception:
        logger.warning("Listing date lookup failed for %s", symbol)
        return None
    finally:
        if YFINANCE_REQUEST_DELAY > 0:
            import time
            time.sleep(YFINANCE_REQUEST_DELAY)

    epoch = info.get("firstTradeDateEpochUtc")
    if epoch is not None:
        try:
            return datetime.fromtimestamp(int(epoch), tz=timezone.utc).strftime("%Y-%m-%d")
        except (TypeError, ValueError, OSError):
            pass

    for key in ("fundInceptionDate", "ipoExpectedDate"):
        raw = info.get(key)
        if raw is None:
            continue
        if isinstance(raw, (int, float)):
            try:
                return datetime.fromtimestamp(int(raw), tz=timezone.utc).strftime("%Y-%m-%d")
            except (TypeError, ValueError, OSError):
                continue
        if isinstance(raw, str) and len(raw) >= 10:
            return raw[:10]

    return None


def _fetch_fundamentals(symbol: str) -> dict[str, Any]:
    out: dict[str, Any] = {
        "company_name": None,
        "industry": None,
        "market_cap_cr": None,
        "pe_ratio": None,
        "roce_pct": None,
    }
    try:
        with without_proxy():
            info = yf.Ticker(symbol).info
    except Exception:
        logger.warning("Fundamentals fetch failed for %s", symbol)
        return out
    finally:
        if YFINANCE_REQUEST_DELAY > 0:
            import time
            time.sleep(YFINANCE_REQUEST_DELAY)

    out["company_name"] = info.get("longName") or info.get("shortName")
    out["industry"] = info.get("industry")
    mc = info.get("marketCap")
    if mc is not None:
        try:
            out["market_cap_cr"] = round(float(mc) / 1e7, 2)
        except (TypeError, ValueError):
            pass
    out["pe_ratio"] = _extract_pe(info)
    out["roce_pct"] = _extract_roce(info)
    return out


def _compute_returns(series: list[tuple[str, float]]) -> dict[str, float | None]:
    if not series:
        return {
            "return_1d_pct": None,
            "return_1w_pct": None,
            "return_1m_pct": None,
            "return_1y_pct": None,
            "last_price": None,
        }

    dates = [s[0] for s in series]
    closes = [s[1] for s in series]
    last_price = closes[-1]

    def pct_at_offset(trading_days: int) -> float | None:
        if len(closes) <= trading_days:
            return None
        prev = closes[-(trading_days + 1)]
        if prev == 0:
            return None
        return round((last_price - prev) / prev * 100, 2)

    return {
        "return_1d_pct": pct_at_offset(1),
        "return_1w_pct": pct_at_offset(5),
        "return_1m_pct": pct_at_offset(21),
        "return_1y_pct": pct_at_offset(252),
        "last_price": round(last_price, 2),
        "prices_through_date": dates[-1],
    }


def _needs_price_fetch(db, symbol: str, today: str) -> bool:
    latest = crud.get_latest_price_date(db, symbol)
    if latest is None:
        return True
    # Already have today's (or most recent) bar — skip third-party API
    return latest < today


def process_symbol(symbol: str, today: str | None = None, force: bool = False) -> str:
    """
    Process one symbol: fetch if needed, update snapshot.
    Returns: 'fetched' | 'skipped' | 'failed'
    """
    symbol = _normalize_symbol(symbol)
    today = today or _today_str()

    try:
        with SessionLocal() as db:
            last_date = crud.get_latest_price_date(db, symbol)
            earliest_date = crud.get_earliest_price_date(db, symbol)
            existing_snapshot = None
            from app.db.models import DayScanSnapshot
            row = db.get(DayScanSnapshot, symbol)
            if row:
                existing_snapshot = row

            fetched_prices = False
            # Ensure we eventually store at least DAY_SCAN_HISTORY_YEARS years.
            desired_start = _target_history_start(today)
            needs_backfill = earliest_date is None or earliest_date > desired_start

            if force or needs_backfill:
                new_bars = _fetch_prices_from_api(symbol, start=desired_start)
            elif _needs_price_fetch(db, symbol, today):
                new_bars = _fetch_prices_from_api(symbol, last_date=last_date)
            else:
                new_bars = []

            if new_bars:
                crud.upsert_daily_prices(db, symbol, new_bars)
                fetched_prices = True
            elif last_date is None:
                return "failed"

            fundamentals: dict[str, Any] = {}
            need_fundamentals = force or (
                existing_snapshot is None
                or _is_fundamentals_stale(existing_snapshot.fundamentals_updated_at)
            )
            if need_fundamentals:
                fundamentals = _fetch_fundamentals(symbol)
            else:
                fundamentals = {
                    "company_name": existing_snapshot.company_name,
                    "industry": existing_snapshot.industry,
                    "market_cap_cr": existing_snapshot.market_cap_cr,
                    "pe_ratio": existing_snapshot.pe_ratio,
                    "roce_pct": existing_snapshot.roce_pct,
                }

            series = crud.get_price_series(db, symbol)
            returns = _compute_returns(series)
            if not series and not fetched_prices:
                return "failed"

            snapshot_data = {
                **fundamentals,
                **returns,
                "fundamentals_updated_at": datetime.now(timezone.utc)
                if need_fundamentals
                else (existing_snapshot.fundamentals_updated_at if existing_snapshot else None),
            }
            crud.upsert_day_scan_snapshot(db, symbol, snapshot_data)

            if fetched_prices or need_fundamentals:
                return "fetched"
            return "skipped"
    except Exception:
        logger.exception("Day scan failed for %s", symbol)
        return "failed"


def process_symbol_from_listing(symbol: str) -> str:
    """
    Fetch full daily history from listing date (or max available), store in DB.
    Marks stock_universe.data_from_listing=True on success.
    """
    symbol = _normalize_symbol(symbol)

    try:
        with SessionLocal() as db:
            from app.db.models import StockUniverse

            row = db.get(StockUniverse, symbol)
            if row is not None and row.data_from_listing:
                return "skipped"

        listing_start = _get_listing_start_date(symbol)
        if listing_start:
            new_bars = _fetch_prices_from_api(symbol, start=listing_start)
        else:
            # Fallback: maximum history Yahoo provides for this ticker
            new_bars = _fetch_prices_from_api(symbol, period="max")

        if not new_bars:
            return "failed"

        effective_listing = listing_start or new_bars[0]["trade_date"]

        with SessionLocal() as db:
            crud.upsert_daily_prices(db, symbol, new_bars)

            fundamentals = _fetch_fundamentals(symbol)
            series = crud.get_price_series(db, symbol)
            returns = _compute_returns(series)

            snapshot_data = {
                **fundamentals,
                **returns,
                "fundamentals_updated_at": datetime.now(timezone.utc),
            }
            crud.upsert_day_scan_snapshot(db, symbol, snapshot_data)
            crud.mark_data_from_listing(db, symbol, listing_date=effective_listing)

        logger.info(
            "Listing fetch OK for %s: %d bars from %s",
            symbol,
            len(new_bars),
            effective_listing,
        )
        return "fetched"
    except Exception:
        logger.exception("Listing fetch failed for %s", symbol)
        return "failed"


def _run_listing_fetch_job(symbols: list[str]) -> None:
    total = len(symbols)
    _set_listing_job(
        running=True,
        total=total,
        processed=0,
        fetched=0,
        skipped=0,
        failed=0,
        current_symbol="",
        started_at=datetime.now(timezone.utc).isoformat(),
        completed_at=None,
        error=None,
    )

    fetched = skipped = failed = processed = 0

    try:
        for sym in symbols:
            result = process_symbol_from_listing(sym)
            processed += 1
            if result == "fetched":
                fetched += 1
            elif result == "skipped":
                skipped += 1
            else:
                failed += 1
            _set_listing_job(
                processed=processed,
                fetched=fetched,
                skipped=skipped,
                failed=failed,
                current_symbol=sym,
            )
    except Exception as exc:
        logger.exception("Listing fetch job failed")
        _set_listing_job(error=str(exc))
    finally:
        _set_listing_job(
            running=False,
            completed_at=datetime.now(timezone.utc).isoformat(),
            current_symbol="",
        )


def start_listing_fetch() -> dict[str, Any]:
    """Start sequential listing-date fetch for stocks not yet marked data_from_listing."""
    with _listing_job_lock:
        if _listing_job_state["running"]:
            return {"status": "already_running", **get_listing_job_status()}

    with SessionLocal() as db:
        symbols = crud.list_symbols_pending_listing_fetch(db)
        total = crud.count_stock_universe(db, active_only=True)
        completed = crud.count_listing_fetched(db, active_only=True)

    if total > 0 and completed >= total:
        return {
            "status": "all_done",
            "message": "All stocks already fetched from listing.",
            **get_listing_job_status(),
        }

    if not symbols:
        return {"status": "nothing_pending", **get_listing_job_status()}

    thread = threading.Thread(target=_run_listing_fetch_job, args=(symbols,), daemon=True)
    thread.start()
    return {"status": "started", "pending": len(symbols), **get_listing_job_status()}


def _run_fetch_job(symbols: list[str], force: bool = False) -> None:
    today = _today_str()
    total = len(symbols)
    _set_job(
        running=True,
        total=total,
        processed=0,
        fetched=0,
        skipped=0,
        failed=0,
        current_symbol="",
        started_at=datetime.now(timezone.utc).isoformat(),
        completed_at=None,
        error=None,
    )

    from concurrent.futures import ThreadPoolExecutor, as_completed

    workers = min(SCAN_MAX_WORKERS_LARGE, max(1, total))
    fetched = skipped = failed = processed = 0

    def _task(sym: str) -> tuple[str, str]:
        result = process_symbol(sym, today, force=force)
        return sym, result

    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_task, sym): sym for sym in symbols}
            for future in as_completed(futures):
                sym, result = future.result()
                processed += 1
                if result == "fetched":
                    fetched += 1
                elif result == "skipped":
                    skipped += 1
                else:
                    failed += 1
                _set_job(
                    processed=processed,
                    fetched=fetched,
                    skipped=skipped,
                    failed=failed,
                    current_symbol=sym,
                )
    except Exception as exc:
        logger.exception("Day scan job failed")
        _set_job(error=str(exc))
    finally:
        _set_job(
            running=False,
            completed_at=datetime.now(timezone.utc).isoformat(),
            current_symbol="",
        )


def start_day_scan_fetch(force: bool = False) -> dict[str, Any]:
    """Start background fetch for all stocks in universe."""
    with _job_lock:
        if _job_state["running"]:
            return {"status": "already_running", **get_job_status()}

    with SessionLocal() as db:
        symbols = crud.list_stock_universe(db, active_only=True)

    if not symbols:
        return {"status": "error", "message": "Stock universe is empty. Restart backend to populate."}

    thread = threading.Thread(target=_run_fetch_job, args=(symbols, force), daemon=True)
    thread.start()
    return {"status": "started", "total": len(symbols), **get_job_status()}


def start_volume_fetch(scope: str = "nifty50") -> dict[str, Any]:
    """
    Fetch / refresh daily prices (incl. volume) for a symbol set.

    scope = "nifty50" → just the Nifty 50 constituents (quick start).
    scope = "all"     → every active stock in the NSE universe.

    Reuses the shared day-scan fetch job so the NSE 1Day live-status bar and the
    sync WebSocket reflect progress (and it keeps running across tab changes).
    """
    with _job_lock:
        if _job_state["running"]:
            return {"status": "already_running", "scope": scope, **get_job_status()}

    scope = (scope or "nifty50").lower()
    if scope == "nifty50":
        from app.watchlists.indices import IndexId
        from app.watchlists.loader import get_watchlist

        symbols = get_watchlist(IndexId.NIFTY_50)
    else:
        scope = "all"
        with SessionLocal() as db:
            symbols = crud.list_stock_universe(db, active_only=True)

    if not symbols:
        return {"status": "error", "message": "No symbols found for the requested scope.", "scope": scope}

    thread = threading.Thread(target=_run_fetch_job, args=(symbols, False), daemon=True)
    thread.start()
    return {"status": "started", "scope": scope, "total": len(symbols), **get_job_status()}


def list_day_scan_rows() -> list[dict[str, Any]]:
    with SessionLocal() as db:
        return crud.list_day_scan_snapshots(db)


_CHART_INTERVALS = {"1d", "1wk", "1mo"}
_RESAMPLE_RULE = {"1wk": "W-FRI", "1mo": "MS"}


def _resample_daily_bars(bars: list[dict[str, Any]], interval: str) -> list[dict[str, Any]]:
    """Aggregate stored DAILY bars into weekly / monthly candles.

    All chart data is derived from the daily series in stock_prices_daily; we never
    fetch intraday data (the DB only holds daily bars).
    """
    if interval == "1d" or not bars:
        return bars

    rule = _RESAMPLE_RULE.get(interval)
    if rule is None:
        return bars

    df = pd.DataFrame(bars)
    df["dt"] = pd.to_datetime(df["time"], errors="coerce")
    df = df.dropna(subset=["dt"]).set_index("dt").sort_index()

    agg = (
        df.resample(rule)
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna(subset=["close"])
    )

    out: list[dict[str, Any]] = []
    for idx, row in agg.iterrows():
        out.append(
            {
                "time": idx.strftime("%Y-%m-%d"),
                "open": round(float(row["open"]), 2) if not pd.isna(row["open"]) else None,
                "high": round(float(row["high"]), 2) if not pd.isna(row["high"]) else None,
                "low": round(float(row["low"]), 2) if not pd.isna(row["low"]) else None,
                "close": round(float(row["close"]), 2),
                "volume": int(row["volume"]) if not pd.isna(row["volume"]) else None,
            }
        )
    return out


def get_day_scan_chart(symbol: str, interval: str = "1d") -> dict[str, Any]:
    """Return stored daily OHLCV bars for a symbol, optionally aggregated to weekly/monthly."""
    symbol = symbol.upper()
    if not symbol.endswith((".NS", ".BO")):
        symbol = f"{symbol}.NS"

    interval = interval if interval in _CHART_INTERVALS else "1d"

    with SessionLocal() as db:
        daily_bars = crud.get_daily_ohlcv_bars(db, symbol)
        snapshot_rows = crud.list_day_scan_snapshots(db)
        meta = next((r for r in snapshot_rows if r["symbol"] == symbol), None)

    if not daily_bars:
        return {
            "symbol": symbol,
            "company_name": meta["company_name"] if meta else symbol.replace(".NS", ""),
            "interval": interval,
            "bar_count": 0,
            "from_date": None,
            "to_date": None,
            "bars": [],
        }

    bars = _resample_daily_bars(daily_bars, interval)

    return {
        "symbol": symbol,
        "company_name": meta["company_name"] if meta else symbol.replace(".NS", ""),
        "interval": interval,
        "bar_count": len(bars),
        "from_date": bars[0]["time"] if bars else None,
        "to_date": bars[-1]["time"] if bars else None,
        "bars": bars,
    }

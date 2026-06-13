"""Bullish screening logic and composite scoring."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import pandas as pd

from app.config import (
    DEFAULT_MIN_SCORE,
    RSI_BULLISH_HIGH,
    RSI_BULLISH_LOW,
    RSI_OVERBOUGHT,
    RSI_RISING_LOW,
    SCAN_MAX_WORKERS_DB,
)
from app.watchlists.indices import INDEX_META, IndexId
from app.watchlists.loader import get_watchlist
from app.models import ScanResponse, StockDetail, StockSignal
from app.services.price_history import load_daily_history
from app.services.indicators import add_indicators, pct_change
from app.services.scoring import compute_overall_score
from app.db.database import SessionLocal
from app.db import crud

logger = logging.getLogger(__name__)


def _evaluate_row(df: pd.DataFrame, symbol: str) -> StockSignal | None:
    """Score latest bar; return None if indicators unavailable."""
    df = add_indicators(df)
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else latest

    if pd.isna(latest["rsi"]) or pd.isna(latest["sma_50"]):
        return None

    close = float(latest["close"])
    rsi = float(latest["rsi"])
    prev_rsi = float(prev["rsi"]) if not pd.isna(prev["rsi"]) else rsi
    macd = float(latest["macd"]) if not pd.isna(latest["macd"]) else None
    macd_signal = float(latest["macd_signal"]) if not pd.isna(latest["macd_signal"]) else None
    macd_hist = float(latest["macd_histogram"]) if not pd.isna(latest["macd_histogram"]) else None
    prev_hist = float(prev["macd_histogram"]) if not pd.isna(prev["macd_histogram"]) else None
    sma_20 = float(latest["sma_20"]) if not pd.isna(latest["sma_20"]) else None
    sma_50 = float(latest["sma_50"]) if not pd.isna(latest["sma_50"]) else None

    score = 0
    signals: list[str] = []
    warnings: list[str] = []

    if RSI_BULLISH_LOW <= rsi <= RSI_BULLISH_HIGH:
        score += 2
        signals.append("rsi_bullish")
    elif RSI_RISING_LOW <= rsi < RSI_BULLISH_LOW and rsi > prev_rsi:
        score += 1
        signals.append("rsi_rising")

    if rsi > RSI_OVERBOUGHT:
        warnings.append("rsi_overbought")

    if macd is not None and macd_signal is not None:
        if macd > macd_signal:
            score += 2
            signals.append("macd_bullish")
        if macd_hist is not None and macd_hist > 0:
            if prev_hist is not None and macd_hist > prev_hist:
                score += 1
                signals.append("macd_histogram_rising")

    if sma_20 is not None and close > sma_20:
        score += 1
        signals.append("above_sma20")
    if sma_50 is not None and close > sma_50:
        score += 1
        signals.append("above_sma50")
    if sma_20 is not None and sma_50 is not None and sma_20 > sma_50:
        score += 1
        signals.append("golden_alignment")

    change_5d = pct_change(df["close"], 5)
    change_20d = pct_change(df["close"], 20)

    if change_5d is not None and change_5d > 0:
        score += 1
        signals.append("momentum_5d_up")
    if change_20d is not None and change_20d > 0:
        score += 1
        signals.append("momentum_20d_up")

    trend = "up" if score >= DEFAULT_MIN_SCORE else "neutral"

    # Recompute from the current technical score every scan — a cached value
    # would freeze the rating at whatever the score was when first stored.
    # retail_pct comes from DB holdings (populated when insights modal is opened).
    overall_score: float | None = None
    try:
        with SessionLocal() as db:
            hrow = crud.get_holdings(db, symbol)
            retail_pct = hrow.retail_pct if hrow else None
            overall_score = compute_overall_score(score, retail_pct)
            crud.upsert_profile(db, symbol, {"overall_score": overall_score})
    except Exception:
        logger.warning("Could not compute overall score for %s", symbol, exc_info=True)
        overall_score = compute_overall_score(score, None)

    return StockSignal(
        symbol=symbol,
        price=round(close, 2),
        change_5d_pct=change_5d,
        change_20d_pct=change_20d,
        rsi=round(rsi, 2),
        macd=round(macd, 4) if macd is not None else None,
        macd_signal=round(macd_signal, 4) if macd_signal is not None else None,
        macd_histogram=round(macd_hist, 4) if macd_hist is not None else None,
        sma_20=round(sma_20, 2) if sma_20 is not None else None,
        sma_50=round(sma_50, 2) if sma_50 is not None else None,
        score=score,
        overall_score=overall_score,
        signals=signals,
        warnings=warnings,
        trend=trend,
    )


def analyze_symbol(symbol: str) -> StockSignal | None:
    symbol = symbol.upper()
    if not symbol.endswith(".NS"):
        symbol = f"{symbol}.NS"

    df = load_daily_history(symbol, period="6mo", min_rows=55)
    if df is None:
        return None
    return _evaluate_row(df, symbol)


def analyze_symbol_detail(symbol: str, history_bars: int = 30) -> StockDetail | None:
    symbol = symbol.upper()
    if not symbol.endswith(".NS"):
        symbol = f"{symbol}.NS"

    df = load_daily_history(symbol, period="6mo", min_rows=55)
    if df is None:
        return None

    signal = _evaluate_row(df, symbol)
    if signal is None:
        return None

    tail = df.tail(history_bars)
    history = [
        {"date": idx.strftime("%Y-%m-%d"), "close": round(float(row["close"]), 2)}
        for idx, row in tail.iterrows()
    ]

    return StockDetail(**signal.model_dump(), history=history)


def _scan_symbol(symbol: str, min_score: int) -> StockSignal | None:
    try:
        signal = analyze_symbol(symbol)
        if signal and signal.score >= min_score:
            return signal
    except Exception:
        logger.exception("Error analyzing %s", symbol)
    return None


def run_scan(
    min_score: int = DEFAULT_MIN_SCORE,
    limit: int | None = None,
    index: IndexId | str = IndexId.NIFTY_50,
) -> ScanResponse:
    if isinstance(index, str):
        index = IndexId(index.lower())

    watchlist = get_watchlist(index)
    from app.services.stock_lists import filter_blacklisted

    with SessionLocal() as db:
        blacklist = crud.get_blacklist_symbols(db)
        watchlist = filter_blacklisted(watchlist, blacklist)

    results: list[StockSignal] = []
    
    workers = min(SCAN_MAX_WORKERS_DB, max(1, len(watchlist)))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_scan_symbol, symbol, min_score): symbol
            for symbol in watchlist
        }
        for future in as_completed(futures):
            signal = future.result()
            if signal:
                results.append(signal)

    results.sort(
        key=lambda s: (s.score, s.change_20d_pct or 0),
        reverse=True,
    )
    if limit is not None:
        results = results[:limit]

    meta = INDEX_META[index]
    return ScanResponse(
        scanned_at=datetime.now(timezone.utc).isoformat(),
        index=index.value,
        index_label=meta["label"],
        total_scanned=len(watchlist),
        total_matched=len(results),
        min_score=min_score,
        results=results,
    )

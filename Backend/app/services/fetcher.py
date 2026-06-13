"""yfinance data fetching and normalization."""

import logging
import time

import pandas as pd
import yfinance as yf

from app.config import HISTORY_PERIOD, YFINANCE_REQUEST_DELAY
from app.utils.network import without_proxy

logger = logging.getLogger(__name__)


def fetch_history(
    symbol: str,
    period: str = HISTORY_PERIOD,
    interval: str = "1d",
    *,
    min_rows: int = 55,
) -> pd.DataFrame | None:
    """Download OHLCV history for a single symbol."""
    try:
        with without_proxy():
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval, auto_adjust=True)
        
        # Rate limiting: add delay after each request to avoid Yahoo Finance 429 errors
        if YFINANCE_REQUEST_DELAY > 0:
            time.sleep(YFINANCE_REQUEST_DELAY)
            
    except Exception:
        logger.exception("Failed to fetch %s", symbol)
        # Still apply delay even on error to avoid hammering the API
        if YFINANCE_REQUEST_DELAY > 0:
            time.sleep(YFINANCE_REQUEST_DELAY)
        return None

    if df is None or df.empty:
        logger.warning("No data for %s", symbol)
        return None

    df = df.copy()
    df.columns = [str(c).lower().replace(" ", "_") for c in df.columns]

    required = {"close", "high", "low", "open", "volume"}
    if not required.issubset(set(df.columns)):
        logger.warning("Missing columns for %s: %s", symbol, list(df.columns))
        return None

    df = df.dropna(subset=["close"])
    if len(df) < min_rows:
        logger.warning("Insufficient history for %s (%d rows)", symbol, len(df))
        return None

    return df

"""Technical indicator calculations using ta library."""

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD, SMAIndicator

from app.config import (
    MACD_FAST,
    MACD_SIGNAL,
    MACD_SLOW,
    RSI_WINDOW,
    SMA_LONG,
    SMA_SHORT,
)


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add RSI, MACD, and SMA columns to OHLCV dataframe."""
    out = df.copy()
    close = out["close"]

    out["rsi"] = RSIIndicator(close=close, window=RSI_WINDOW).rsi()
    macd = MACD(
        close=close,
        window_slow=MACD_SLOW,
        window_fast=MACD_FAST,
        window_sign=MACD_SIGNAL,
    )
    out["macd"] = macd.macd()
    out["macd_signal"] = macd.macd_signal()
    out["macd_histogram"] = macd.macd_diff()
    out["sma_20"] = SMAIndicator(close=close, window=SMA_SHORT).sma_indicator()
    out["sma_50"] = SMAIndicator(close=close, window=SMA_LONG).sma_indicator()

    return out


def pct_change(series: pd.Series, days: int) -> float | None:
    """Percent change over N trading days."""
    if len(series) <= days:
        return None
    current = series.iloc[-1]
    prior = series.iloc[-1 - days]
    if prior == 0 or pd.isna(current) or pd.isna(prior):
        return None
    return round(((current - prior) / prior) * 100, 2)

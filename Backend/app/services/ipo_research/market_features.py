"""Market regime features at IPO listing date (NIFTY / BANKNIFTY / SENSEX)."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

try:
    import ta
except ImportError:
    ta = None  # type: ignore

from app.db import crud
from app.db.database import SessionLocal
from app.services.market_indices import INDEX_ORDER, ensure_market_indices_refreshed

logger = logging.getLogger(__name__)


def _load_index_df(index_id: str) -> pd.DataFrame | None:
    with SessionLocal() as db:
        row = crud.get_market_index(db, index_id)
    if row is None or not row.bars_json:
        return None
    bars = json.loads(row.bars_json)
    if not bars:
        return None
    df = pd.DataFrame(bars)
    df["date"] = pd.to_datetime(df["time"])
    df = df.set_index("date").sort_index()
    return df


def _returns_before_listing(
    df: pd.DataFrame,
    listing_date: datetime,
    days: int,
) -> float | None:
    if df is None or df.empty:
        return None
    end = pd.Timestamp(listing_date)
    window = df[df.index < end].tail(days + 1)
    if len(window) < 2:
        return None
    start_close = float(window["close"].iloc[0])
    end_close = float(window["close"].iloc[-1])
    if start_close == 0:
        return None
    return round((end_close - start_close) / start_close * 100, 4)


def _index_ta_at_listing(df: pd.DataFrame, listing_date: datetime) -> dict[str, float | None]:
    """Technical indicators on index series using `ta` (momentum at listing)."""
    out: dict[str, float | None] = {
        "index_rsi_14": None,
        "index_macd_hist": None,
    }
    if ta is None or df is None or df.empty:
        return out

    end = pd.Timestamp(listing_date)
    window = df[df.index < end].tail(60)
    if len(window) < 20:
        return out

    close = window["close"].astype(float)
    try:
        rsi = ta.momentum.RSIIndicator(close, window=14).rsi()
        if not rsi.empty and not pd.isna(rsi.iloc[-1]):
            out["index_rsi_14"] = round(float(rsi.iloc[-1]), 4)
    except Exception:
        pass

    try:
        macd = ta.trend.MACD(close)
        hist = macd.macd_diff()
        if not hist.empty and not pd.isna(hist.iloc[-1]):
            out["index_macd_hist"] = round(float(hist.iloc[-1]), 4)
    except Exception:
        pass

    return out


def market_features_at_listing(listing_date_str: str) -> dict[str, Any]:
    """Features from cached 1Y index bars at IPO listing date."""
    ensure_market_indices_refreshed()
    listing_dt = datetime.strptime(listing_date_str, "%Y-%m-%d")

    features: dict[str, Any] = {
        "listing_month": listing_dt.month,
        "listing_year": listing_dt.year,
    }

    for index_id in INDEX_ORDER:
        df = _load_index_df(index_id)
        prefix = index_id
        features[f"{prefix}_return_1w_before"] = _returns_before_listing(df, listing_dt, 5)
        features[f"{prefix}_return_1m_before"] = _returns_before_listing(df, listing_dt, 22)
        features[f"{prefix}_return_3m_before"] = _returns_before_listing(df, listing_dt, 66)

        if index_id == "nifty":
            ta_feats = _index_ta_at_listing(df, listing_dt)
            features.update(ta_feats)

    # Aggregate market sentiment
    rets = [
        features.get("nifty_return_1m_before"),
        features.get("banknifty_return_1m_before"),
        features.get("sensex_return_1m_before"),
    ]
    valid = [r for r in rets if r is not None]
    features["market_avg_return_1m_before"] = (
        round(float(np.mean(valid)), 4) if valid else None
    )
    return features

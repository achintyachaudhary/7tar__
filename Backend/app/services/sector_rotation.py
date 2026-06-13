"""Sector rotation analysis using Relative Rotation Graph (RRG) methodology.

Implements the Julius de Kempenaer methodology adapted for Indian markets:
- Fetches 5 years of daily data for all NSE sectoral indices via yfinance
- Computes RS-Ratio (relative strength vs NIFTY 50) and RS-Momentum
- Classifies each sector into RRG quadrants: Leading, Weakening, Lagging, Improving
- Identifies rotation direction and momentum velocity
- Stores results in DB for fast retrieval

Algorithm:
  1. RS = Sector_Close / Benchmark_Close (NIFTY 50)
  2. EMA_RS = EMA(RS, span=m) where m=14 for weekly-equivalent
  3. RS_Ratio = 100 * (EMA_RS / SMA(EMA_RS, m))
  4. ROC = (RS_Ratio(t) - RS_Ratio(t-k)) / RS_Ratio(t-k), k=10
  5. EMA_ROC = EMA(ROC, span=m)
  6. RS_Momentum = 100 + 100 * EMA_ROC

Quadrants:
  - Leading:   RS_Ratio > 100, RS_Momentum > 100 (strong & accelerating)
  - Weakening: RS_Ratio > 100, RS_Momentum < 100 (strong but decelerating)
  - Lagging:   RS_Ratio < 100, RS_Momentum < 100 (weak & decelerating)
  - Improving: RS_Ratio < 100, RS_Momentum > 100 (weak but improving)
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd

from app.utils.network import without_proxy

logger = logging.getLogger(__name__)

# yfinance ticker mapping for NSE sectoral indices
SECTOR_INDICES: dict[str, str] = {
    "NIFTY AUTO": "^CNXAUTO",
    "NIFTY BANK": "^NSEBANK",
    "NIFTY ENERGY": "^CNXENERGY",
    "NIFTY FIN SERVICE": "NIFTY_FIN_SERVICE.NS",
    "NIFTY FMCG": "^CNXFMCG",
    "NIFTY IT": "^CNXIT",
    "NIFTY MEDIA": "^CNXMEDIA",
    "NIFTY METAL": "^CNXMETAL",
    "NIFTY PHARMA": "^CNXPHARMA",
    "NIFTY PSU BANK": "^CNXPSUBANK",
    "NIFTY REALTY": "^CNXREALTY",
    "NIFTY COMMODITIES": "^CNXCMDT",
    "NIFTY CONSUMPTION": "^CNXCONSUM",
    "NIFTY INFRA": "^CNXINFRA",
    "NIFTY MNC": "^CNXMNC",
}

# Additional broad market / thematic indices for charting
EXTRA_INDICES: dict[str, str] = {
    "NIFTY 50": "^NSEI",
    "SENSEX": "^BSESN",
    "NIFTY NEXT 50": "^NSMIDCP",
    "NIFTY 100": "^CNX100",
    "NIFTY 200": "^CNX200",
    "NIFTY MIDCAP 50": "^NSEMDCP50",
    "NIFTY MIDCAP 100": "NIFTY_MIDCAP_100.NS",
    "NIFTY MIDCAP 150": "NIFTYMIDCAP150.NS",
    "NIFTY PRIVATE BANK": "NIFTY_PVT_BANK.NS",
}

BENCHMARK_TICKER = "^NSEI"  # NIFTY 50

# RRG computation parameters
EMA_SPAN = 14         # EMA window for smoothing
ROC_PERIOD = 10       # Lookback for rate-of-change
TAIL_LENGTH = 12      # Number of historical points to keep for trail

# Timeframes for multi-period return analysis
RETURN_PERIODS = {
    "1W": 5,
    "1M": 21,
    "3M": 63,
    "6M": 126,
    "1Y": 252,
    "2Y": 504,
    "5Y": 1200,
}


def _fetch_yf_data(ticker: str, period: str = "5y") -> pd.Series | None:
    """Fetch adjusted close price series from yfinance."""
    try:
        import yfinance as yf

        with without_proxy():
            t = yf.Ticker(ticker)
            df = t.history(period=period, auto_adjust=True)

        if df is None or df.empty:
            logger.warning("No data returned for %s", ticker)
            return None

        return df["Close"].dropna()
    except Exception:
        logger.warning("Failed to fetch %s", ticker, exc_info=True)
        return None


def _compute_rrg(sector_series: pd.Series, benchmark_series: pd.Series) -> dict[str, Any] | None:
    """Compute RS-Ratio and RS-Momentum for a sector vs benchmark."""
    # Align on common dates
    combined = pd.DataFrame({"sector": sector_series, "bench": benchmark_series}).dropna()
    if len(combined) < EMA_SPAN * 3:
        return None

    # Step 1: Relative Strength ratio
    rs = combined["sector"] / combined["bench"]

    # Step 2: EMA of RS
    ema_rs = rs.ewm(span=EMA_SPAN, adjust=False).mean()

    # Step 3: RS-Ratio = 100 * (EMA_RS / SMA(EMA_RS, EMA_SPAN))
    sma_ema_rs = ema_rs.rolling(window=EMA_SPAN).mean()
    rs_ratio = 100.0 * (ema_rs / sma_ema_rs)

    # Step 4: Rate of Change of RS-Ratio
    rs_ratio_shifted = rs_ratio.shift(ROC_PERIOD)
    roc = (rs_ratio - rs_ratio_shifted) / rs_ratio_shifted

    # Step 5: EMA of ROC
    ema_roc = roc.ewm(span=EMA_SPAN, adjust=False).mean()

    # Step 6: RS-Momentum = 100 + 100 * EMA_ROC
    rs_momentum = 100.0 + 100.0 * ema_roc

    # Get latest values
    latest_ratio = rs_ratio.iloc[-1] if not rs_ratio.empty else None
    latest_momentum = rs_momentum.iloc[-1] if not rs_momentum.empty else None

    if pd.isna(latest_ratio) or pd.isna(latest_momentum):
        return None

    # Tail (historical trajectory for the RRG chart)
    tail_ratio = rs_ratio.iloc[-TAIL_LENGTH:].tolist()
    tail_momentum = rs_momentum.iloc[-TAIL_LENGTH:].tolist()
    tail_dates = [d.strftime("%Y-%m-%d") for d in rs_ratio.index[-TAIL_LENGTH:]]

    # Determine quadrant
    if latest_ratio >= 100 and latest_momentum >= 100:
        quadrant = "leading"
    elif latest_ratio >= 100 and latest_momentum < 100:
        quadrant = "weakening"
    elif latest_ratio < 100 and latest_momentum < 100:
        quadrant = "lagging"
    else:
        quadrant = "improving"

    # Momentum direction (is RS_Momentum rising or falling?)
    if len(tail_momentum) >= 3:
        recent_mom = tail_momentum[-3:]
        if recent_mom[-1] > recent_mom[-2] > recent_mom[-3]:
            direction = "accelerating"
        elif recent_mom[-1] < recent_mom[-2] < recent_mom[-3]:
            direction = "decelerating"
        elif recent_mom[-1] > recent_mom[-2]:
            direction = "turning_up"
        else:
            direction = "turning_down"
    else:
        direction = "unknown"

    return {
        "rs_ratio": round(float(latest_ratio), 2),
        "rs_momentum": round(float(latest_momentum), 2),
        "quadrant": quadrant,
        "direction": direction,
        "tail_ratio": [round(float(v), 2) if not pd.isna(v) else None for v in tail_ratio],
        "tail_momentum": [round(float(v), 2) if not pd.isna(v) else None for v in tail_momentum],
        "tail_dates": tail_dates,
    }


def _compute_returns(series: pd.Series) -> dict[str, float | None]:
    """Compute % returns for standard timeframes."""
    returns: dict[str, float | None] = {}
    if series is None or series.empty:
        return {k: None for k in RETURN_PERIODS}

    latest = float(series.iloc[-1])
    for label, days in RETURN_PERIODS.items():
        if len(series) > days:
            past_val = float(series.iloc[-(days + 1)])
            if past_val > 0:
                returns[label] = round((latest - past_val) / past_val * 100, 2)
            else:
                returns[label] = None
        else:
            returns[label] = None
    return returns


def compute_sector_rotation() -> dict[str, Any]:
    """Full sector rotation computation using RRG methodology.
    
    Fetches 5 years of data, computes RS-Ratio and RS-Momentum for all sectors,
    classifies into quadrants, and returns full analysis.
    """
    start = time.time()
    logger.info("Starting sector rotation computation...")

    # Fetch benchmark
    bench_data = _fetch_yf_data(BENCHMARK_TICKER, period="5y")
    if bench_data is None or len(bench_data) < 100:
        return {"status": "error", "error": "Failed to fetch NIFTY 50 benchmark data"}

    bench_returns = _compute_returns(bench_data)
    time.sleep(0.3)

    sectors: list[dict[str, Any]] = []
    failed: list[str] = []

    for name, ticker in SECTOR_INDICES.items():
        logger.info("Processing %s (%s)...", name, ticker)
        sector_data = _fetch_yf_data(ticker, period="5y")
        time.sleep(0.4)

        if sector_data is None or len(sector_data) < 100:
            failed.append(name)
            continue

        # Compute RRG
        rrg = _compute_rrg(sector_data, bench_data)
        if rrg is None:
            failed.append(name)
            continue

        # Compute multi-timeframe returns
        returns = _compute_returns(sector_data)

        # Compute relative returns vs benchmark
        rel_returns: dict[str, float | None] = {}
        for tf in RETURN_PERIODS:
            sr = returns.get(tf)
            br = bench_returns.get(tf)
            if sr is not None and br is not None:
                rel_returns[tf] = round(sr - br, 2)
            else:
                rel_returns[tf] = None

        sectors.append({
            "index_name": name,
            "ticker": ticker,
            "last_close": round(float(sector_data.iloc[-1]), 2),
            "rrg": rrg,
            "returns": returns,
            "relative_returns": rel_returns,
        })

    # Sort by RS-Ratio descending (strongest first)
    sectors.sort(key=lambda s: s["rrg"]["rs_ratio"], reverse=True)

    # Classify into quadrant groups
    quadrant_summary = {
        "leading": [s["index_name"] for s in sectors if s["rrg"]["quadrant"] == "leading"],
        "weakening": [s["index_name"] for s in sectors if s["rrg"]["quadrant"] == "weakening"],
        "lagging": [s["index_name"] for s in sectors if s["rrg"]["quadrant"] == "lagging"],
        "improving": [s["index_name"] for s in sectors if s["rrg"]["quadrant"] == "improving"],
    }

    # Rotation narrative
    rotation_narrative = _build_rotation_narrative(sectors)

    duration = time.time() - start
    logger.info("Sector rotation completed in %.1fs (%d sectors, %d failed)", duration, len(sectors), len(failed))

    return {
        "status": "ready",
        "sectors": sectors,
        "benchmark_returns": bench_returns,
        "quadrant_summary": quadrant_summary,
        "rotation_narrative": rotation_narrative,
        "failed_sectors": failed,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "duration_sec": round(duration, 1),
    }


def _build_rotation_narrative(sectors: list[dict]) -> list[str]:
    """Generate human-readable rotation insights."""
    insights: list[str] = []

    leading = [s for s in sectors if s["rrg"]["quadrant"] == "leading"]
    improving = [s for s in sectors if s["rrg"]["quadrant"] == "improving"]
    weakening = [s for s in sectors if s["rrg"]["quadrant"] == "weakening"]
    lagging = [s for s in sectors if s["rrg"]["quadrant"] == "lagging"]

    if leading:
        names = ", ".join(s["index_name"].replace("NIFTY ", "") for s in leading[:3])
        insights.append(f"Money is currently concentrated in: {names}")

    if improving:
        names = ", ".join(s["index_name"].replace("NIFTY ", "") for s in improving[:3])
        insights.append(f"Emerging sectors (money rotating in): {names}")

    if weakening:
        names = ", ".join(s["index_name"].replace("NIFTY ", "") for s in weakening[:3])
        insights.append(f"Sectors losing steam (still strong but fading): {names}")

    accelerating = [s for s in sectors if s["rrg"]["direction"] == "accelerating"]
    if accelerating:
        names = ", ".join(s["index_name"].replace("NIFTY ", "") for s in accelerating[:3])
        insights.append(f"Fastest accelerating momentum: {names}")

    # Best 1M outperformer vs benchmark
    by_rel_1m = sorted(
        [s for s in sectors if s["relative_returns"].get("1M") is not None],
        key=lambda s: s["relative_returns"]["1M"],
        reverse=True,
    )
    if by_rel_1m:
        top = by_rel_1m[0]
        insights.append(
            f"Best 1M relative performer: {top['index_name'].replace('NIFTY ', '')} "
            f"(+{top['relative_returns']['1M']}% vs NIFTY 50)"
        )
    if len(by_rel_1m) > 1:
        bottom = by_rel_1m[-1]
        insights.append(
            f"Worst 1M relative performer: {bottom['index_name'].replace('NIFTY ', '')} "
            f"({bottom['relative_returns']['1M']}% vs NIFTY 50)"
        )

    return insights


def save_rotation_to_db(data: dict[str, Any]) -> None:
    """Persist rotation analysis to database."""
    from app.db.database import SessionLocal
    from app.db.models import SectorRotationCache

    with SessionLocal() as db:
        row = SectorRotationCache(
            data_json=json.dumps(data),
            computed_at=datetime.now(timezone.utc),
        )
        db.add(row)
        db.commit()


def get_latest_rotation_from_db() -> dict[str, Any] | None:
    """Load the most recent rotation analysis from DB."""
    from app.db.database import SessionLocal
    from app.db.models import SectorRotationCache

    with SessionLocal() as db:
        row = (
            db.query(SectorRotationCache)
            .order_by(SectorRotationCache.computed_at.desc())
            .first()
        )
        if row is None:
            return None
        try:
            data = json.loads(row.data_json)
            data["computed_at"] = row.computed_at.isoformat() if row.computed_at else None
            return data
        except (json.JSONDecodeError, TypeError):
            return None


def run_sector_rotation_job() -> dict[str, Any]:
    """Entry point for scheduled job: compute and save to DB."""
    result = compute_sector_rotation()
    if result.get("status") == "ready":
        save_rotation_to_db(result)
    return result

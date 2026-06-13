"""Live paper swing-trading engine.

A dedicated background **process** (started at app startup) ticks on an interval.
Operational *mode* moves automatically between:

- ``market_off`` - outside NSE trading hours / weekend.
- ``analysis``   - off-hours user override, or market hours with stale live data.
- ``live``       - market open + fresh data: evaluate entries and manage exits.

Candidates come from persisted Year / Multi-Year scan results. Trades are paper only.
"""

from __future__ import annotations

import logging
import multiprocessing as mp
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, time as dt_time, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.db import crud
from app.db.database import SessionLocal
from app.services import notifier, stockrelay
from app.services.fetcher import fetch_history
from app.services.price_history import load_daily_history, load_minute_history

def _publish_sse(event_type: str, data: dict) -> None:
    """Push an event to the cross-process queue for the parent to broadcast."""
    global _event_queue
    try:
        if _event_queue is not None:
            _event_queue.put_nowait({"event": event_type, "data": data})
    except Exception:
        pass

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")

# NSE regular session (9:15am - 3:30pm IST).
MARKET_OPEN = dt_time(9, 15)
MARKET_CLOSE = dt_time(15, 30)

TICK_SECONDS = 30
# A quote is "fresh" (live) if its last bar is within this many minutes of now.
FRESH_MINUTES = 40
# Re-sync screener candidates at most every 5 minutes (not every tick).
CANDIDATE_REFRESH_SECONDS = 300
# Poll a small rotating slice of "watching" candidates per tick for arm promotion.
WATCHING_QUOTE_BATCH = 15
MAX_QUOTES_PER_TICK = 35
QUOTE_FETCH_WORKERS = 6

_last_candidate_refresh = 0.0
_watch_rotation_idx = 0

# ── Executed strategy: "Smart Swing" ──────────────────────────────────────────
SMART_SWING = {
    "key": "smart_swing",
    "label": "Smart Swing 5/3",
    "tp_pct": 5.0,
    "sl_pct": -3.0,
    "trail_after_pct": 3.0,
    "trail_gap_pct": 2.0,
    "time_stop_days": 15,
    "time_stop_min_pct": 1.5,
    "sma_exit": False,
}

# Alternatives simulated for the comparison summary (not actually traded).
QUICK_SCALP = {
    "key": "quick_scalp",
    "label": "Quick Scalp 3/2",
    "tp_pct": 3.0,
    "sl_pct": -2.0,
    "trail_after_pct": None,
    "trail_gap_pct": None,
    "time_stop_days": None,
    "time_stop_min_pct": None,
    "sma_exit": False,
}

FIXED_5 = {
    "key": "fixed_5",
    "label": "Fixed 5/3",
    "tp_pct": 5.0,
    "sl_pct": -3.0,
    "trail_after_pct": None,
    "trail_gap_pct": None,
    "time_stop_days": None,
    "time_stop_min_pct": None,
    "sma_exit": False,
}

BREAKOUT_MOMENTUM = {
    "key": "breakout_momentum",
    "label": "Breakout Momentum 10/4",
    "tp_pct": 10.0,
    "sl_pct": -4.0,
    "trail_after_pct": 5.0,
    "trail_gap_pct": 3.0,
    "time_stop_days": None,
    "time_stop_min_pct": None,
    "sma_exit": False,
}

TREND_RIDE = {
    "key": "trend_ride",
    "label": "Trend Ride (SMA20)",
    "tp_pct": None,
    "sl_pct": -5.0,
    "trail_after_pct": None,
    "trail_gap_pct": None,
    "time_stop_days": None,
    "time_stop_min_pct": None,
    "sma_exit": True,
    "sma_window": 20,
}

# ATR-based: adaptive stop/target computed from recent volatility
ATR_ADAPTIVE = {
    "key": "atr_adaptive",
    "label": "ATR Adaptive 2x/1.5x",
    "tp_pct": None,   # computed dynamically from ATR
    "sl_pct": None,    # computed dynamically from ATR
    "trail_after_pct": None,
    "trail_gap_pct": None,
    "time_stop_days": 10,
    "time_stop_min_pct": 0.5,
    "sma_exit": False,
    "atr_tp_mult": 2.0,     # target = entry + 2x ATR
    "atr_sl_mult": 1.5,     # stop   = entry - 1.5x ATR
    "atr_window": 14,
}

# Tight scalp for quick intraday-style flips
TIGHT_SCALP = {
    "key": "tight_scalp",
    "label": "Tight Scalp 2/1",
    "tp_pct": 2.0,
    "sl_pct": -1.0,
    "trail_after_pct": None,
    "trail_gap_pct": None,
    "time_stop_days": 3,
    "time_stop_min_pct": 0.0,
    "sma_exit": False,
}

# Risk-reward optimised: 1:3 ratio with trailing
RR_OPTIMISED = {
    "key": "rr_optimised",
    "label": "R:R 7/2 Trail",
    "tp_pct": 7.0,
    "sl_pct": -2.0,
    "trail_after_pct": 4.0,
    "trail_gap_pct": 1.5,
    "time_stop_days": 20,
    "time_stop_min_pct": 1.0,
    "sma_exit": False,
}

# Respects the screener's own trade plan: the candidate's target_price and
# stop_price (computed by the matching screener — e.g. Mean Reversion's SMA20
# target / ATR stop, Vol Squeeze's measured move / range low) replace fixed
# percentages. The tp/sl percentages below are only the fallback when a
# candidate arrives without levels.
SCREENER_LEVELS = {
    "key": "screener_levels",
    "label": "Screener Levels",
    "tp_pct": 5.0,
    "sl_pct": -3.0,
    "trail_after_pct": None,
    "trail_gap_pct": None,
    "time_stop_days": 20,
    "time_stop_min_pct": 0.0,
    "sma_exit": False,
    "use_screener_levels": True,
}

STRATEGIES = [
    SMART_SWING, QUICK_SCALP, FIXED_5, BREAKOUT_MOMENTUM, TREND_RIDE,
    ATR_ADAPTIVE, TIGHT_SCALP, RR_OPTIMISED, SCREENER_LEVELS,
]

STRATEGY_BY_KEY = {s["key"]: s for s in STRATEGIES}

# Portfolio limits (INR)
PORTFOLIO_STARTING = 1_000_000.0   # 10 lakh total capital
MAX_PER_TRADE = 100_000.0          # 1 lakh max per stock
MIN_TRADE_SIZE = 5_000.0           # skip entries below this deployable amount


def _whole_share_qty(deploy: float, price: float) -> int:
    """NSE trades whole shares only — floor deploy/price to an integer."""
    if price <= 0:
        return 0
    return int(deploy // price)


_lock = threading.Lock()
_entry_lock = threading.Lock()
_process: mp.Process | None = None
_stop_event: mp.synchronize.Event | None = None
_event_queue: mp.Queue | None = None  # cross-process event bridge

MODE_LABELS = {
    "market_off": "Market Off",
    "analysis": "Market Analysis",
    "live": "Live Trading",
    "off": "Off",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso_ist(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(IST)
    except Exception:
        return None


def _clamp_exit_time_iso(exit_time_iso: str | None) -> str | None:
    """Never return an exit timestamp in the future (IST)."""
    dt = _parse_iso_ist(exit_time_iso)
    if dt is None:
        return exit_time_iso
    now = _now().astimezone(IST)
    return (min(dt, now)).isoformat()


def _sim_exit_timestamp(exit_date: str | None, entry_time_iso: str | None = None) -> str | None:
    """Map a daily-bar exit date to IST — past days use close; today uses min(now, close)."""
    if not exit_date:
        return None
    try:
        exit_day = datetime.strptime(exit_date, "%Y-%m-%d").date()
    except ValueError:
        return None
    now = _now().astimezone(IST)
    today = now.date()
    entry_dt = _parse_iso_ist(entry_time_iso)

    if exit_day < today:
        ts = datetime.combine(exit_day, MARKET_CLOSE, tzinfo=IST)
    elif exit_day == today:
        close_today = datetime.combine(today, MARKET_CLOSE, tzinfo=IST)
        ts = min(now, close_today)
        if entry_dt and ts < entry_dt:
            ts = entry_dt
    else:
        ts = now
    return ts.isoformat()


def _as_utc(dt: datetime) -> datetime:
    """Normalize a datetime to UTC (SQLite returns naive UTC on read)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ── Market clock ───────────────────────────────────────────────────────────────

def _is_market_open(ref: datetime | None = None) -> bool:
    now_ist = (ref or _now()).astimezone(IST)
    if now_ist.weekday() >= 5:  # Sat/Sun
        return False
    return MARKET_OPEN <= now_ist.time() <= MARKET_CLOSE


# ── Live quote ──────────────────────────────────────────────────────────────────

def _symbols_for_live_quotes(open_trades, watch_rows) -> list[str]:
    """Limit yfinance calls: open positions + armed + a small watching batch."""
    global _watch_rotation_idx

    ordered: list[str] = []
    seen: set[str] = set()

    def add(sym: str | None) -> None:
        if sym and sym not in seen:
            seen.add(sym)
            ordered.append(sym)

    for trade in open_trades:
        add(trade.symbol)

    armed = [c for c in watch_rows if c.status == "armed"]
    for cand in armed:
        if len(ordered) >= MAX_QUOTES_PER_TICK:
            break
        add(cand.symbol)

    watching = [c for c in watch_rows if c.status == "watching"]
    if watching and len(ordered) < MAX_QUOTES_PER_TICK:
        n = len(watching)
        batch = min(WATCHING_QUOTE_BATCH, n, MAX_QUOTES_PER_TICK - len(ordered))
        start = _watch_rotation_idx % n
        for i in range(batch):
            add(watching[(start + i) % n].symbol)
        _watch_rotation_idx = (start + batch) % max(n, 1)

    return ordered


def _fetch_quotes_upstox(symbols: list[str]) -> dict[str, dict[str, Any]] | None:
    """One batch LTP call for every symbol — real-time prices, no per-symbol I/O."""
    from app.services.vendors import upstox

    key_to_sym: dict[str, str] = {}
    for sym in symbols:
        inst = upstox.resolve_instrument(sym)
        if inst:
            key_to_sym[inst["instrument_key"]] = sym
    if not key_to_sym:
        return None

    prices = upstox.fetch_ltp(list(key_to_sym.keys()))
    now = _now()
    quotes: dict[str, dict[str, Any]] = {}
    for key, price in prices.items():
        sym = key_to_sym.get(key)
        if sym is None or price <= 0:
            continue
        quotes[sym] = {"price": float(price), "ts": now, "fresh": _is_market_open()}
    return quotes or None


def _fetch_quotes(symbols: list[str]) -> dict[str, dict[str, Any]]:
    """Fetch latest quotes — Upstox batch LTP first, yfinance bars as fallback."""
    quotes: dict[str, dict[str, Any]] = {}
    if not symbols:
        return quotes

    from app.services.vendors.registry import use_upstox

    if use_upstox("live_quotes"):
        try:
            upstox_quotes = _fetch_quotes_upstox(symbols)
            if upstox_quotes:
                missing = [s for s in symbols if s not in upstox_quotes]
                if missing:
                    logger.debug("Upstox LTP missing %d symbols, yfinance fills", len(missing))
                else:
                    return upstox_quotes
                quotes.update(upstox_quotes)
                symbols = missing
        except Exception:
            logger.exception("Upstox batch LTP failed — falling back to yfinance")

    workers = min(QUOTE_FETCH_WORKERS, len(symbols))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_latest_quote, sym): sym for sym in symbols}
        for fut in as_completed(futures):
            sym = futures[fut]
            try:
                q = fut.result()
                if q is not None:
                    quotes[sym] = q
            except Exception:
                logger.exception("Quote fetch failed for %s", sym)
    return quotes


def _latest_quote(symbol: str) -> dict[str, Any] | None:
    """Return {'price', 'ts', 'fresh'} from the latest intraday bar, or None."""
    df = fetch_history(symbol, period="5d", interval="5m", min_rows=1)
    if df is None or df.empty:
        return None
    last = df.iloc[-1]
    ts = df.index[-1]
    try:
        ts_utc = ts.tz_convert("UTC").to_pydatetime()
    except (TypeError, AttributeError):
        try:
            ts_utc = ts.tz_localize("UTC").to_pydatetime()
        except Exception:
            ts_utc = _now()
    age_min = (_now() - ts_utc).total_seconds() / 60.0
    return {
        "price": float(last["close"]),
        "ts": ts_utc,
        "fresh": age_min <= FRESH_MINUTES,
    }


# ── Minute-level data (ephemeral, never persisted) ──────────────────────────────

def _fetch_minute_bars(symbol: str, interval: str = "1m", period: str = "1d"):
    """Fetch fine-grained intraday bars for entry/exit confirmation.
    
    Returns a pandas DataFrame or None. Data is used for computation only and
    never stored in the database.
    """
    try:
        df = fetch_history(symbol, period=period, interval=interval, min_rows=2)
        if df is None or df.empty:
            return None
        return df
    except Exception:
        logger.debug("Could not fetch %s bars for %s", interval, symbol)
        return None


def _confirm_entry_on_minute_bars(symbol: str, resistance: float) -> bool:
    """Check if the latest 1-minute candle closed above resistance.
    
    More precise than using 5m bars; avoids false breakouts from intra-bar spikes.
    """
    df = _fetch_minute_bars(symbol, interval="1m", period="1d")
    if df is None or len(df) < 2:
        return True  # fall back to existing logic if minute data unavailable
    last_close = float(df.iloc[-1]["close"])
    prev_close = float(df.iloc[-2]["close"])
    return last_close > resistance and prev_close <= resistance * 1.005


# All screener types that can feed live-trade candidates (order preserved for display).
# Keys match the scan-result cache keys in job_manager.SCAN_REGISTRY.
SCREENER_SOURCES = (
    "brst",
    "multi_year",
    "golden",
    "weekly",
    "darvas",
    "mean_reversion",
    "vol_squeeze",
    "volume_surge",
)


def _fmt_inr(value: float | None, default: str = "N/A") -> str:
    if value is None:
        return default
    try:
        return f"₹{float(value):,.2f}"
    except (TypeError, ValueError):
        return default


def _match_price(match: dict[str, Any]) -> float | None:
    """Best-effort latest price from any screener match shape."""
    for key in ("price", "price_latest", "last_price"):
        val = match.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                continue
    return None


SOURCE_LABELS = {
    "brst": "Year Breakout",
    "multi_year": "Multi-Year Breakout",
    "golden": "Golden Stocks",
    "weekly": "Weekly Stocks",
    "darvas": "Darvas Box",
    "mean_reversion": "Mean Reversion",
    "vol_squeeze": "Volatility Squeeze",
    "volume_surge": "Volume Surge",
}


def _candidate_selection_info(
    match: dict[str, Any],
    source: str,
    resistance: float,
    target: float,
    stop: float,
    volume_confirmed: bool,
) -> dict[str, Any]:
    """Structured entry point and bullet reasons for UI and consolidated email."""
    label = SOURCE_LABELS.get(source, source)
    bullets: list[str] = []

    if source in ("brst", "multi_year"):
        tests = match.get("tests_count")
        vr = match.get("volume_ratio")
        bullets.append(f"Selected from {label} screener (saved scan results)")
        if tests is not None:
            bullets.append(f"Resistance {_fmt_inr(resistance)} tested {tests} time(s)")
        if volume_confirmed:
            bullets.append(
                f"Volume confirmed ({vr}x 50-day avg)" if vr else "Volume confirmation met"
            )
        else:
            bullets.append("Volume confirmation required before live entry")
        entry_point = (
            f"Buy when price closes above {_fmt_inr(resistance)} with volume confirmation"
        )
    elif source == "darvas":
        box_bottom = match.get("box_bottom")
        box_range = match.get("box_range_pct")
        vr = match.get("volume_ratio")
        bullets.append("Darvas Box breakout detected")
        bullets.append(
            f"Box range: {_fmt_inr(box_bottom)} – {_fmt_inr(resistance)}"
            f" ({box_range}% range)" if box_range else f"Box top: {_fmt_inr(resistance)}"
        )
        if volume_confirmed:
            bullets.append(
                f"Volume confirmed ({vr}x 50-day avg)" if vr else "Volume confirmation met"
            )
        else:
            bullets.append("Needs volume surge for strong entry")
        entry_point = (
            f"Buy on Darvas Box breakout above {_fmt_inr(resistance)} with volume"
        )
    elif source == "golden":
        rank = match.get("rank_score")
        if rank is not None:
            bullets.append(f"Golden rank score {float(rank):.1f} (holdings + financials)")
        bullets.append("QoQ/YoY growth in price, revenue, and profit")
        bullets.append("Momentum continuation candidate from Golden Stocks scan")
        entry_point = (
            f"Enter on breakout above {_fmt_inr(resistance)} "
            f"(current reference {_fmt_inr(_match_price(match))})"
        )
    elif source == "weekly":
        bullets.append("Weekly price momentum with growing financials")
        bullets.append("Selected from Weekly Stocks screener")
        entry_point = (
            f"Enter on momentum break above {_fmt_inr(resistance)} "
            f"(reference price {_fmt_inr(_match_price(match))})"
        )
    elif source == "mean_reversion":
        rsi = match.get("rsi")
        pullback = match.get("pullback_pct")
        rr = match.get("reward_risk")
        bullets.append("Uptrend pullback — mean-reversion buy zone")
        if rsi is not None:
            bullets.append(f"RSI {rsi} (oversold in an uptrend)")
        if pullback is not None:
            bullets.append(f"Pulled back {pullback}% from 20-day high")
        if rr is not None:
            bullets.append(f"Reward/risk {rr}")
        entry_point = f"Buy the pullback near {_fmt_inr(resistance)}"
    elif source == "vol_squeeze":
        range_pct = match.get("range_pct")
        range_days = match.get("range_days")
        atr_ratio = match.get("atr_ratio")
        bullets.append("Volatility squeeze — tight pre-breakout range")
        if range_pct is not None and range_days:
            bullets.append(f"{range_pct}% range over {range_days} days")
        if atr_ratio is not None:
            bullets.append(f"ATR contraction ratio {atr_ratio}")
        entry_point = f"Buy on range breakout above {_fmt_inr(match.get('range_high') or resistance)}"
    elif source == "volume_surge":
        mult = match.get("volume_multiple")
        day_pct = match.get("day_change_pct")
        bullets.append("Unusual volume surge with strong close")
        if mult is not None:
            bullets.append(f"Volume {mult}x the 50-day average")
        if day_pct is not None:
            bullets.append(f"Day move {day_pct}%")
        entry_point = f"Buy above surge high {_fmt_inr(resistance)} on continued volume"
    else:
        bullets.append(f"Imported from {label}")
        entry_point = f"Enter above {_fmt_inr(resistance)}"

    bullets.append(f"Smart Swing target {_fmt_inr(target)}, stop {_fmt_inr(stop)} (₹1L per trade)")

    return {"entry_point": entry_point, "bullets": bullets}


def _build_rationale(match: dict[str, Any], source: str) -> str:
    source_labels = {
        "brst": "Year breakout",
        "multi_year": "Multi-year breakout",
        "golden": "Golden Stock",
        "weekly": "Weekly Stock",
        "darvas": "Darvas Box",
        "mean_reversion": "Mean Reversion",
        "vol_squeeze": "Volatility Squeeze",
        "volume_surge": "Volume Surge",
    }
    label = source_labels.get(source, source)

    if source in ("brst", "multi_year"):
        resistance = match.get("highest_high")
        tests = match.get("tests_count")
        vr = match.get("volume_ratio")
        res_txt = _fmt_inr(resistance) if resistance is not None else "N/A"
        vol = (
            f" Volume on the breakout is {vr}x the 50-day average, which signals "
            f"institutional buying rather than retail noise."
            if vr
            else ""
        )
        return (
            f"{label}: price is pressing against resistance {res_txt} "
            f"(tested {tests or 0} time(s)). Entry triggers when price crosses ABOVE this "
            f"level with volume confirmation.{vol} Executed via Smart Swing: +8% target, "
            f"-4% stop, trailing stop once +4% is reached, time-stop after 15 days if flat."
        )
    elif source == "golden":
        rank = match.get("rank_score")
        rank_txt = f"{float(rank):.1f}" if rank is not None else "—"
        price_txt = _fmt_inr(_match_price(match))
        return (
            f"{label} screener (rank {rank_txt}): QoQ/YoY growth in price, revenue, and profit. "
            f"Current price {price_txt}. Added as candidate for momentum continuation."
        )
    elif source == "darvas":
        box_top = match.get("box_top")
        box_bottom = match.get("box_bottom")
        vr = match.get("volume_ratio")
        vol = (
            f" Volume is {vr}x the 50-day average, confirming institutional participation."
            if vr
            else ""
        )
        return (
            f"{label}: Price broke above box top {_fmt_inr(box_top)} "
            f"(box range {_fmt_inr(box_bottom)} – {_fmt_inr(box_top)}).{vol} "
            f"Executed via Smart Swing: +8% target, -4% stop, trailing stop once +4% is reached."
        )
    elif source == "weekly":
        price_txt = _fmt_inr(_match_price(match))
        return (
            f"{label} screener: Weekly momentum growth with strong financials. "
            f"Current price {price_txt}. Added as candidate for short-term momentum play."
        )
    elif source == "mean_reversion":
        rsi = match.get("rsi")
        pullback = match.get("pullback_pct")
        return (
            f"{label}: uptrend stock pulled back {pullback if pullback is not None else '—'}% "
            f"from its 20-day high with RSI {rsi if rsi is not None else '—'}. "
            f"Buying the dip near {_fmt_inr(match.get('entry_price'))} for a bounce back "
            f"toward the recent high."
        )
    elif source == "vol_squeeze":
        range_pct = match.get("range_pct")
        range_days = match.get("range_days")
        return (
            f"{label}: price compressed into a {range_pct if range_pct is not None else '—'}% "
            f"range over {range_days or '—'} days with contracting volatility. Entry triggers "
            f"on a breakout above {_fmt_inr(match.get('range_high'))} — tight ranges often "
            f"precede expansion moves."
        )
    elif source == "volume_surge":
        mult = match.get("volume_multiple")
        day_pct = match.get("day_change_pct")
        return (
            f"{label}: traded {mult if mult is not None else '—'}x its 50-day average volume "
            f"with a {day_pct if day_pct is not None else '—'}% move and a strong close. "
            f"Entry triggers above the surge high {_fmt_inr(match.get('surge_high'))} — "
            f"institutional volume often continues."
        )
    return f"{label}: Added from {source} scan."


def _extract_resistance(match: dict[str, Any], source: str) -> float | None:
    """Extract the price level to use as resistance from different scan result formats."""
    if source in ("brst", "multi_year"):
        val = match.get("highest_high")
    elif source == "darvas":
        val = match.get("box_top")
    elif source in ("golden", "weekly"):
        val = _match_price(match)
    elif source in ("mean_reversion", "vol_squeeze", "volume_surge"):
        # These screeners compute their own trigger level (pullback close,
        # range high, surge high respectively).
        val = match.get("entry_price") or _match_price(match)
    else:
        val = None
    if val is None:
        return None
    try:
        p = float(val)
        return p if p > 0 else None
    except (TypeError, ValueError):
        return None


def _discover_available_screener_sources(db) -> list[str]:
    """Return screener cache keys that exist and have at least one match."""
    available: list[str] = []
    for source in SCREENER_SOURCES:
        cache = crud.get_scan_result_cache(db, source)
        if cache and cache.get("matches"):
            available.append(source)
    return available


# ── Quality filters for candidate selection ──────────────────────────────────────

# Minimum thresholds — stocks below these are skipped during candidate import
MIN_PRICE = 20.0             # skip penny stocks below ₹20
MIN_AVG_VOLUME = 50_000      # skip illiquid stocks (50k shares/day average)
MIN_VOLUME_RATIO = 1.2       # at least 1.2x recent volume vs 50-day avg
MIN_UPTREND_SLOPE_PCT = 0.0  # SMA50 should be flat or rising vs SMA200


def _quality_score(match: dict[str, Any], source: str) -> dict[str, Any]:
    """
    Evaluate a screener match for quality. Returns:
      - passed: bool (True = candidate should be added)
      - score: 0-100 quality score
      - reasons: list of rejection reasons if failed
      - quality_flags: list of positive attributes
    """
    reasons: list[str] = []
    flags: list[str] = []
    score = 50  # baseline

    price = match.get("price") or match.get("price_latest") or match.get("last_price")
    if price is not None:
        price = float(price)
        if price < MIN_PRICE:
            reasons.append(f"Price ₹{price:.0f} < min ₹{MIN_PRICE:.0f}")
        elif price >= 100:
            score += 5
            flags.append("price > ₹100")

    avg_vol = match.get("avg_volume")
    if avg_vol is not None:
        avg_vol = float(avg_vol)
        if avg_vol < MIN_AVG_VOLUME:
            reasons.append(f"Avg volume {avg_vol:,.0f} < min {MIN_AVG_VOLUME:,.0f}")
        elif avg_vol >= 200_000:
            score += 10
            flags.append("high liquidity")
        elif avg_vol >= 100_000:
            score += 5
            flags.append("moderate liquidity")

    vol_ratio = match.get("volume_ratio")
    if vol_ratio is not None:
        vol_ratio = float(vol_ratio)
        # Quiet volume is part of the setup for pullback/squeeze entries —
        # only breakout-style sources require expanding volume.
        if vol_ratio < MIN_VOLUME_RATIO and source not in ("mean_reversion", "vol_squeeze"):
            reasons.append(f"Volume ratio {vol_ratio:.1f}x < min {MIN_VOLUME_RATIO:.1f}x")
        elif vol_ratio >= 2.0:
            score += 15
            flags.append(f"strong volume surge ({vol_ratio:.1f}x)")
        elif vol_ratio >= 1.5:
            score += 10
            flags.append(f"good volume ({vol_ratio:.1f}x)")

    vol_confirmed = match.get("volume_confirmed", False)
    if vol_confirmed:
        score += 10
        flags.append("volume confirmed")

    tests_count = match.get("tests_count")
    if tests_count is not None:
        if tests_count >= 4:
            score += 15
            flags.append(f"strong resistance ({tests_count} tests)")
        elif tests_count >= 3:
            score += 10
            flags.append(f"solid resistance ({tests_count} tests)")

    distance_pct = match.get("distance_pct")
    if distance_pct is not None:
        if float(distance_pct) <= 1.0:
            score += 10
            flags.append("very close to breakout")
        elif float(distance_pct) <= 2.0:
            score += 5
            flags.append("near breakout zone")

    # Bars-based trend check: compute SMA20 vs SMA50 from bars data
    bars = match.get("bars", [])
    if len(bars) >= 50:
        closes = [b["close"] for b in bars]
        sma20 = sum(closes[-20:]) / 20
        sma50 = sum(closes[-50:]) / 50
        if sma20 > sma50:
            score += 10
            flags.append("SMA20 > SMA50 (uptrend)")
        else:
            score -= 5

    score = max(0, min(100, score))
    passed = len(reasons) == 0

    return {
        "passed": passed,
        "score": score,
        "reasons": reasons,
        "quality_flags": flags,
    }


# ── Candidate refresh from saved scans ───────────────────────────────────────────

def _candidate_key(symbol: str, source: str) -> tuple[str, str]:
    return (symbol, source)


def _refresh_candidates(
    db,
    sources: list[str] | None = None,
    *,
    exclude_keys: set[tuple[str, str]] | None = None,
    send_consolidated_email: bool = False,
) -> tuple[int, list[dict[str, Any]]]:
    """Import candidates from scan caches. Returns (created_count, newly_created payloads)."""
    if sources is None:
        sources = _discover_available_screener_sources(db) or ["brst", "multi_year"]
    exclude = exclude_keys or set()
    created_count = 0
    newly_created: list[dict[str, Any]] = []

    for source in sources:
        cache = crud.get_scan_result_cache(db, source)
        if not cache:
            continue
        seen_symbols: set[str] = set()
        for match in cache.get("matches", []):
            symbol = match.get("symbol")
            if not symbol or symbol in seen_symbols:
                continue
            seen_symbols.add(symbol)
            if _candidate_key(symbol, source) in exclude:
                continue
            resistance = _extract_resistance(match, source)
            if not resistance:
                continue

            # Quality gate: skip low-quality candidates
            quality = _quality_score(match, source)
            if not quality["passed"]:
                logger.debug("Skipping %s (%s): %s", symbol, source, "; ".join(quality["reasons"]))
                continue

            target = round(resistance * (1 + SMART_SWING["tp_pct"] / 100), 2)
            stop = round(resistance * (1 + SMART_SWING["sl_pct"] / 100), 2)
            vol_confirmed = bool(match.get("volume_confirmed", source in ("brst", "multi_year", "volume_surge")))
            info = _candidate_selection_info(match, source, resistance, target, stop, vol_confirmed)
            rationale = _build_rationale(match, source)
            if quality["quality_flags"]:
                rationale += " Quality: " + ", ".join(quality["quality_flags"]) + f" (score: {quality['score']})"

            existing = crud.get_live_candidate(db, symbol, source)
            fields: dict[str, Any] = {
                "company_name": match.get("company_name"),
                "resistance": resistance,
                "target_price": target,
                "stop_price": stop,
                "volume_ratio": match.get("volume_ratio"),
                "volume_confirmed": vol_confirmed,
                "rationale": rationale,
            }
            price = _match_price(match)
            if existing is None:
                fields["last_price"] = price
                fields["status"] = "watching"
            elif price is not None and existing.status in ("watching", "armed"):
                fields["last_price"] = price
            row, created = crud.upsert_live_candidate(db, symbol, source, **fields)

            if created:
                created_count += 1
                newly_created.append({
                    "symbol": symbol,
                    "source": source,
                    "company_name": match.get("company_name"),
                    "resistance": resistance,
                    "target_price": target,
                    "stop_price": stop,
                    "entry_point": info["entry_point"],
                    "bullets": info["bullets"],
                    "rationale": rationale,
                })

    if send_consolidated_email and newly_created:
        if notifier.notify_candidates_bulk(newly_created):
            for item in newly_created:
                crud.upsert_live_candidate(db, item["symbol"], item["source"], notified=True)

    return created_count, newly_created


def _load_sync_prefs(db) -> tuple[list[str] | None, set[tuple[str, str]]]:
    """Read user screener sync selection from live-trading state."""
    import json as _json

    from app.db.models import LiveTradingState

    row = db.get(LiveTradingState, 1)
    sync_sources: list[str] | None = None
    sync_excluded: set[tuple[str, str]] = set()
    if row and row.sync_screeners_json:
        try:
            sync_sources = _json.loads(row.sync_screeners_json)
        except Exception:
            sync_sources = None
    if row and row.sync_excluded_json:
        try:
            for item in _json.loads(row.sync_excluded_json):
                sym = item.get("symbol")
                src = item.get("source")
                if sym and src:
                    sync_excluded.add(_candidate_key(sym, src))
        except Exception:
            pass
    return sync_sources, sync_excluded


def _publish_candidates_sse(db) -> None:
    """Push the latest candidate list to SSE subscribers."""
    try:
        from app.db.models import LiveTradeCandidate

        candidates = [
            _enrich_candidate_for_ui(_candidate_to_dict(c))
            for c in db.query(LiveTradeCandidate).all()
        ]
        _publish_sse("candidates", {"candidates": candidates})
    except Exception:
        logger.exception("Failed to publish candidates SSE")


def refresh_candidates_after_scan(scan_type: str) -> dict[str, Any]:
    """Import live-trade candidates when a screener scan finishes."""
    global _last_candidate_refresh

    if scan_type not in SCREENER_SOURCES:
        return {"status": "skipped", "reason": "not a live-trading screener"}

    with SessionLocal() as db:
        sync_sources, sync_excluded = _load_sync_prefs(db)
        if sync_sources is not None and scan_type not in sync_sources:
            logger.info(
                "Skip candidate refresh for %s — not in user sync selection %s",
                scan_type,
                sync_sources,
            )
            return {"status": "skipped", "reason": "screener not selected for sync"}

        added, newly = _refresh_candidates(
            db,
            sources=[scan_type],
            exclude_keys=sync_excluded or None,
            send_consolidated_email=False,
        )
        _publish_candidates_sse(db)

    _last_candidate_refresh = time.monotonic()
    logger.info(
        "Live-trade candidates refreshed after %s scan (%d new)",
        scan_type,
        added,
    )
    return {
        "status": "ok",
        "source": scan_type,
        "candidates_added": added,
        "new_symbols": [n["symbol"] for n in newly],
    }


def _remove_excluded_candidates(db, exclude_keys: set[tuple[str, str]]) -> int:
    """Delete watching/armed candidates the user deselected."""
    removed = 0
    for symbol, source in exclude_keys:
        if crud.delete_live_candidate(db, symbol, source):
            removed += 1
    return removed


def _remove_candidates_for_sources(db, sources: list[str]) -> int:
    """Remove all non-active-trade candidates belonging to the given screener sources."""
    if not sources:
        return 0
    from app.db.models import LiveTradeCandidate

    rows = (
        db.query(LiveTradeCandidate)
        .filter(
            LiveTradeCandidate.source.in_(sources),
            LiveTradeCandidate.status != "in_trade",
        )
        .all()
    )
    for row in rows:
        db.delete(row)
    if rows:
        db.commit()
    return len(rows)


def _valid_symbols_for_source(db, source: str) -> set[str]:
    """Symbols currently in a screener cache with a usable resistance level."""
    cache = crud.get_scan_result_cache(db, source)
    if not cache:
        return set()
    valid: set[str] = set()
    seen: set[str] = set()
    for match in cache.get("matches", []):
        symbol = match.get("symbol")
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        if _extract_resistance(match, source):
            valid.add(symbol)
    return valid


def _prune_stale_candidates_for_sources(
    db,
    sources: list[str],
    exclude_keys: set[tuple[str, str]] | None = None,
) -> int:
    """Drop watchlist rows no longer present in the screener scan cache."""
    if not sources:
        return 0
    from app.db.models import LiveTradeCandidate

    exclude = exclude_keys or set()
    removed = 0
    for source in sources:
        valid = _valid_symbols_for_source(db, source)
        rows = (
            db.query(LiveTradeCandidate)
            .filter(LiveTradeCandidate.source == source)
            .all()
        )
        for row in rows:
            if row.symbol in valid:
                continue
            if row.status == "in_trade":
                continue
            if crud.has_open_live_trade(db, row.symbol):
                continue
            if _candidate_key(row.symbol, row.source) in exclude:
                continue
            db.delete(row)
            removed += 1
    if removed:
        db.commit()
    return removed


def get_sync_preview() -> dict[str, Any]:
    """List stocks available from each screener cache for the sync picker UI."""
    with SessionLocal() as db:
        from app.db.models import LiveTradeCandidate

        sources = _discover_available_screener_sources(db)
        sections: list[dict[str, Any]] = []
        total = 0
        watchlist_count = db.query(LiveTradeCandidate).count()
        watchlist_by_source: dict[str, int] = {}
        for row in db.query(LiveTradeCandidate).all():
            watchlist_by_source[row.source] = watchlist_by_source.get(row.source, 0) + 1

        for source in sources:
            cache = crud.get_scan_result_cache(db, source)
            if not cache:
                continue
            items: list[dict[str, Any]] = []
            seen: set[str] = set()
            for match in cache.get("matches", []):
                symbol = match.get("symbol")
                if not symbol or symbol in seen:
                    continue
                seen.add(symbol)
                resistance = _extract_resistance(match, source)
                if not resistance:
                    continue
                target = round(resistance * (1 + SMART_SWING["tp_pct"] / 100), 2)
                stop = round(resistance * (1 + SMART_SWING["sl_pct"] / 100), 2)
                vol_confirmed = bool(match.get("volume_confirmed", source in ("brst", "multi_year", "volume_surge")))
                info = _candidate_selection_info(match, source, resistance, target, stop, vol_confirmed)
                quality = _quality_score(match, source)
                existing = crud.get_live_candidate(db, symbol, source)
                items.append({
                    "symbol": symbol,
                    "source": source,
                    "company_name": match.get("company_name") or symbol,
                    "price": _match_price(match),
                    "resistance": resistance,
                    "target_price": target,
                    "stop_price": stop,
                    "entry_point": info["entry_point"],
                    "bullets": info["bullets"],
                    "is_candidate": existing is not None,
                    "selected": quality["passed"],
                    "quality_score": quality["score"],
                    "quality_flags": quality["quality_flags"],
                    "quality_issues": quality["reasons"],
                })
                total += 1
            if items:
                sections.append({
                    "source": source,
                    "label": SOURCE_LABELS.get(source, source),
                    "count": len(items),
                    "watchlist_count": watchlist_by_source.get(source, 0),
                    "items": items,
                })

        return {
            "sections": sections,
            "total": total,
            "watchlist_count": watchlist_count,
        }


def sync_candidates_from_screeners(
    scan_types: list[str] | None = None,
    excluded: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Import candidates from screener scan caches.

    If scan_types is omitted or empty, syncs every screener that has cached results in DB.
    excluded: list of {symbol, source} to skip and remove from candidates if present.
    Sends one consolidated email when new candidates are added (not per-stock).
    """
    import json as _json

    valid_types = set(SCREENER_SOURCES)
    exclude_keys: set[tuple[str, str]] = set()
    for item in excluded or []:
        sym = item.get("symbol")
        src = item.get("source")
        if sym and src:
            exclude_keys.add(_candidate_key(sym, src))

    with SessionLocal() as db:
        if scan_types:
            selected = [s for s in scan_types if s in valid_types]
            if not selected:
                return {"status": "error", "message": "No valid scan types provided"}
            # Drop candidates from screeners the user turned off
            deselected_sources = [s for s in SCREENER_SOURCES if s not in selected]
            removed_from_sources = _remove_candidates_for_sources(db, deselected_sources)
        else:
            selected = _discover_available_screener_sources(db)
            removed_from_sources = 0

        if not selected:
            return {
                "status": "ok",
                "synced_from": [],
                "candidates_added": 0,
                "candidates_removed": removed_from_sources,
                "message": "No screener results in database. Run a scan first.",
            }

        removed = removed_from_sources + _remove_excluded_candidates(db, exclude_keys)
        pruned = _prune_stale_candidates_for_sources(db, selected, exclude_keys)
        removed += pruned
        count, _ = _refresh_candidates(
            db,
            sources=selected,
            exclude_keys=exclude_keys,
            send_consolidated_email=True,
        )

        # Persist sync config so the background tick respects user selection
        excluded_list = [{"symbol": s, "source": src} for s, src in exclude_keys]
        crud.update_live_trading_state(
            db,
            sync_screeners_json=_json.dumps(selected),
            sync_excluded_json=_json.dumps(excluded_list),
        )

    return {
        "status": "ok",
        "synced_from": selected,
        "candidates_added": count,
        "candidates_removed": removed,
    }


def remove_candidate(symbol: str, source: str) -> dict[str, Any]:
    """Remove a single candidate from the watchlist (not allowed if in_trade)."""
    with SessionLocal() as db:
        if crud.delete_live_candidate(db, symbol, source):
            return {"status": "ok", "removed": True}
        row = crud.get_live_candidate(db, symbol, source)
        if row is None:
            return {"status": "ok", "removed": False, "message": "Candidate not found"}
        return {"status": "error", "message": "Cannot remove while trade is open"}


# ── Trade lifecycle ──────────────────────────────────────────────────────────────

def _strategy_entry_levels(
    price: float,
    strat: dict[str, Any],
    symbol: str | None = None,
) -> tuple[float | None, float | None]:
    """Target/stop at entry for a strategy (ATR-adaptive uses recent daily bars)."""
    stop = (
        round(price * (1 + strat["sl_pct"] / 100), 2)
        if strat.get("sl_pct") is not None
        else None
    )
    target = (
        round(price * (1 + strat["tp_pct"] / 100), 2)
        if strat.get("tp_pct") is not None
        else None
    )
    if strat.get("atr_tp_mult") is not None and symbol:
        rows = _load_daily_bars(symbol)
        if rows:
            seed = [b["close"] for b in rows[-25:]]
            seed_bars = [
                {"high": c * 1.005, "low": c * 0.995, "close": c} for c in seed
            ]
            atr_window = strat.get("atr_window", 14)
            atr = (
                _compute_atr(seed_bars, atr_window)
                if len(seed_bars) >= 2
                else price * 0.02
            )
            if atr < price * 0.005:
                atr = price * 0.02
            target = round(price + atr * strat["atr_tp_mult"], 2)
            stop = round(price - atr * strat["atr_sl_mult"], 2)
    return target, stop


def _open_trades_for_signal(db, candidate, price: float) -> None:
    """
    Open one paper trade per strategy when entry conditions are met.
    Each strategy uses its own ₹10L wallet (max ₹1L/stock, 10 positions).
    """
    if price <= 0:
        return

    with _entry_lock:
        if crud.has_open_live_trade_for_symbol(db, candidate.symbol):
            logger.info(
                "Skip duplicate entry for %s — open trade already exists",
                candidate.symbol,
            )
            return

        fresh = crud.get_live_candidate(db, candidate.symbol, candidate.source)
        if fresh is None or fresh.status not in ("watching", "armed"):
            return

        entry_signal_id = str(uuid.uuid4())
        entry_time = _now()
        candidate_added_at = fresh.added_at or entry_time
        opened_any = False

        entry_signal = (
            f"BREAKOUT: Price ₹{price:.2f} broke above resistance ₹{fresh.resistance:.2f} "
            f"({((price / fresh.resistance - 1) * 100):.1f}% above) "
        )
        if fresh.volume_confirmed:
            entry_signal += "with volume confirmation. "
        entry_signal += f"Source: {fresh.source.replace('_', ' ').title()}."

        for strat in STRATEGIES:
            strategy_key = strat["key"]
            if crud.has_open_live_trade(db, fresh.symbol, strategy_key):
                continue

            portfolio = crud.get_portfolio_summary(db, strategy_key)
            deploy = min(
                portfolio["trade_budget"],
                portfolio.get("max_per_trade") or MAX_PER_TRADE,
                MAX_PER_TRADE,
            )
            if deploy < MIN_TRADE_SIZE:
                logger.debug(
                    "Skip %s entry for %s — only ₹%.0f deployable",
                    strategy_key,
                    fresh.symbol,
                    portfolio["available_cash"],
                )
                continue

            qty = _whole_share_qty(deploy, price)
            if qty < 1:
                continue

            notional = round(qty * price, 2)
            target, stop = _strategy_entry_levels(price, strat, fresh.symbol)
            if strat.get("use_screener_levels"):
                # The screener's plan wins — only sane levels (target above
                # entry, stop below) are honored; otherwise the fallback stays.
                cand_target = float(fresh.target_price or 0)
                cand_stop = float(fresh.stop_price or 0)
                if cand_target > price:
                    target = round(cand_target, 2)
                if 0 < cand_stop < price:
                    stop = round(cand_stop, 2)
            rationale = (
                f"{entry_signal} Strategy: {strat['label']}. "
                f"Investment: ₹{notional:,.0f} (max ₹{MAX_PER_TRADE:,.0f}/stock, "
                f"wallet ₹{portfolio['available_cash']:,.0f} free)"
            )

            try:
                trade = crud.create_live_trade(
                    db,
                    symbol=fresh.symbol,
                    source=fresh.source,
                    company_name=fresh.company_name,
                    strategy=strategy_key,
                    entry_signal_id=entry_signal_id,
                    entry_price=round(price, 2),
                    entry_time=entry_time,
                    candidate_added_at=candidate_added_at,
                    resistance=fresh.resistance,
                    target_price=target,
                    stop_price=stop,
                    qty=qty,
                    notional=notional,
                    peak_price=round(price, 2),
                    trough_price=round(price, 2),
                    last_price=round(price, 2),
                    status="open",
                    rationale=rationale,
                )
            except Exception as exc:
                from sqlalchemy.exc import IntegrityError

                if isinstance(exc, IntegrityError):
                    logger.warning(
                        "Duplicate open trade blocked for %s (%s)",
                        fresh.symbol,
                        strategy_key,
                    )
                    db.rollback()
                    continue
                raise

            opened_any = True
            notifier.notify_trade_entered(crud._serialize_trade(trade))
            preview = crud.get_preview_strategy_key(db)
            if strategy_key == preview:
                _publish_sse("trade_opened", crud._serialize_trade(trade))

        if opened_any:
            crud.upsert_live_candidate(db, fresh.symbol, fresh.source, status="in_trade")
            try:
                stockrelay.push_trade_entered(
                    fresh,
                    price,
                    entry_signal,
                    entry_signal_id=entry_signal_id,
                )
            except Exception:
                logger.exception("StockRelay trade-entry push failed for %s", fresh.symbol)
            logger.info(
                "Opened parallel paper trades for %s @ %.2f (signal %s)",
                fresh.symbol,
                price,
                entry_signal_id,
            )


def _broadcast_live_event(event_type: str, data: dict[str, Any]) -> None:
    """Push live-trading events to SSE + WS from the API or engine process."""
    try:
        from app.api.sse_routes import publish_sse_event
        from app.api.ws_hub import broadcast_sync

        publish_sse_event(event_type, data)
        broadcast_sync({"channel": f"live-trading:{event_type}", **data})
    except Exception:
        logger.exception("Failed to broadcast live-trading event %s", event_type)


def _close_trade(db, trade, price: float, reason: str, *, notify: bool = True) -> dict[str, Any]:
    exit_price = round(price, 2)
    entry = float(trade.entry_price)
    qty, _ = crud.normalize_trade_position(float(trade.qty), entry)
    pnl_pct = round((exit_price / entry - 1) * 100, 2) if entry else 0.0
    pnl_abs = round(qty * (exit_price - entry), 2)
    days_held = max(0, (_now() - _as_utc(trade.entry_time)).days)
    trade.exit_price = exit_price
    trade.exit_time = _now()
    trade.exit_reason = reason
    trade.pnl_pct = pnl_pct
    trade.pnl_abs = pnl_abs
    trade.days_held = days_held
    trade.last_price = exit_price
    trade.status = "closed"
    db.commit()
    symbol_fully_closed = not crud.has_open_live_trade_for_symbol(db, trade.symbol)
    if symbol_fully_closed:
        crud.upsert_live_candidate(db, trade.symbol, trade.source, status="closed")
    notifier.notify_trade_exited(crud._serialize_trade(trade))
    trade_dict = crud._serialize_trade(trade)
    if symbol_fully_closed:
        try:
            stockrelay.push_trade_exited(trade_dict)
        except Exception:
            logger.exception("StockRelay trade-exit push failed for %s", trade.symbol)
    if notify:
        preview = crud.get_preview_strategy_key(db)
        if trade.strategy == preview:
            _publish_sse("trade_closed", trade_dict)
    logger.info("Closed paper trade %s @ %.2f (%s, %+.2f%%)", trade.symbol, price, reason, pnl_pct)
    return trade_dict


def _manage_open_trade(db, trade, price: float) -> None:
    """Apply strategy-specific exit rules to one open trade given a fresh price."""
    strat = STRATEGY_BY_KEY.get(trade.strategy, SMART_SWING)
    entry = trade.entry_price
    peak = max(trade.peak_price or entry, price)
    trough = min(trade.trough_price or entry, price)
    trade.peak_price = round(peak, 2)
    trade.trough_price = round(trough, 2)
    trade.last_price = round(price, 2)
    db.commit()

    if trade.stop_price is not None and price <= trade.stop_price:
        _close_trade(db, trade, trade.stop_price, "stop_loss")
        return
    if trade.target_price is not None and price >= trade.target_price:
        _close_trade(db, trade, trade.target_price, "target")
        return

    peak_gain = (peak / entry - 1) * 100
    if (
        strat.get("trail_after_pct") is not None
        and peak_gain >= strat["trail_after_pct"]
    ):
        trail_level = peak * (1 - strat["trail_gap_pct"] / 100)
        if price <= trail_level:
            _close_trade(db, trade, trail_level, "trailing_stop")
            return

    if strat.get("sma_exit"):
        rows = _load_daily_bars(trade.symbol)
        if rows:
            sma_window = strat.get("sma_window", 20)
            closes = [b["close"] for b in rows]
            if len(closes) >= sma_window:
                sma = sum(closes[-sma_window:]) / sma_window
                if price < sma:
                    _close_trade(db, trade, price, "sma_exit")
                    return

    days_held = (_now() - _as_utc(trade.entry_time)).days
    gain_pct = (price / entry - 1) * 100
    if (
        strat.get("time_stop_days") is not None
        and days_held >= strat["time_stop_days"]
        and gain_pct < (strat.get("time_stop_min_pct") or 0)
    ):
        _close_trade(db, trade, price, "time_stop")


# ── Tick ─────────────────────────────────────────────────────────────────────────

def _tick() -> None:
    global _last_candidate_refresh

    with SessionLocal() as db:
        from app.db.models import LiveTradingState

        row = db.get(LiveTradingState, 1)
        if row is None:
            row = LiveTradingState(id=1, enabled=True)
            db.add(row)
            db.commit()

        market_open = _is_market_open()

        # When market opens, drop the off-hours analysis override (auto → live path).
        if market_open and row.analysis_override:
            row.analysis_override = False
            db.commit()

        # Refresh candidates periodically (full screener sync is expensive).
        now_mono = time.monotonic()
        if now_mono - _last_candidate_refresh >= CANDIDATE_REFRESH_SECONDS:
            try:
                sync_sources, sync_excluded = _load_sync_prefs(db)
                _refresh_candidates(
                    db,
                    sources=sync_sources or None,
                    exclude_keys=sync_excluded or None,
                )
                if sync_sources is not None:
                    pruned_sources = [s for s in SCREENER_SOURCES if s not in sync_sources]
                    _remove_candidates_for_sources(db, pruned_sources)
                if sync_excluded:
                    _remove_excluded_candidates(db, sync_excluded)
                if sync_sources:
                    _prune_stale_candidates_for_sources(db, sync_sources, sync_excluded)
                _publish_candidates_sse(db)
            except Exception:
                logger.exception("Candidate refresh failed")
            _last_candidate_refresh = now_mono

        if not market_open:
            mode = "analysis" if row.analysis_override else "market_off"
            crud.update_live_trading_state(db, mode=mode, enabled=True, last_tick_at=_now())
            _emit_sse_state(db, mode=mode, market_open=False)

            # Auto-send EOD report after market close
            try:
                from app.services.report_generator import should_send_eod_report, send_eod_report
                if should_send_eod_report():
                    logger.info("Auto-triggering EOD report at 3:45 PM IST")
                    send_eod_report()
            except Exception:
                logger.exception("EOD report auto-send failed")

            return

        # Market is open: gather symbols we care about (open trades + candidates
        # that are watching/armed) and try to get fresh quotes.
        open_trades = crud.list_open_live_trades(db)

        from app.db.models import LiveTradeCandidate

        watch_rows = (
            db.query(LiveTradeCandidate)
            .filter(LiveTradeCandidate.status.in_(["watching", "armed"]))
            .all()
        )

        quote_symbols = _symbols_for_live_quotes(open_trades, watch_rows)
        quotes = _fetch_quotes(quote_symbols)
        any_fresh = False
        last_data_ts = None
        for q in quotes.values():
            if q["fresh"]:
                any_fresh = True
                last_data_ts = q["ts"]

        # Open positions must have at least one fresh quote to stay in live mode.
        open_fresh = any(
            quotes.get(t.symbol, {}).get("fresh")
            for t in open_trades
        )
        if open_trades and not open_fresh:
            any_fresh = False

        if not any_fresh:
            # Data missing/stale -> analysis mode, no live entries/exits.
            crud.update_live_trading_state(db, mode="analysis", enabled=True, last_tick_at=_now())
            _emit_sse_state(db, mode="analysis", market_open=True)
            return

        # Live trading.
        for trade in open_trades:
            q = quotes.get(trade.symbol)
            if q and q["fresh"]:
                try:
                    _manage_open_trade(db, trade, q["price"])
                except Exception:
                    logger.exception("Manage open trade failed for %s", trade.symbol)

        entries_paused = bool(getattr(row, "entries_paused", False))

        for cand in watch_rows:
            q = quotes.get(cand.symbol)
            if not q or not q["fresh"]:
                continue
            price = q["price"]
            # Update last price for display.
            crud.upsert_live_candidate(db, cand.symbol, cand.source, last_price=round(price, 2))
            if crud.has_open_live_trade_for_symbol(db, cand.symbol):
                continue
            if cand.status not in ("watching", "armed"):
                continue
            if entries_paused:
                continue
            # Entry logic: Price breaks above resistance + volume + minute-bar confirmation
            if price > cand.resistance and cand.volume_confirmed and _confirm_entry_on_minute_bars(cand.symbol, cand.resistance):
                try:
                    _open_trades_for_signal(db, cand, price)
                except Exception:
                    logger.exception("Open trade failed for %s", cand.symbol)
            elif price >= cand.resistance * 0.99 and cand.status == "watching":
                crud.upsert_live_candidate(db, cand.symbol, cand.source, status="armed")
                try:
                    stockrelay.push_resistance_approach(cand, price)
                except Exception:
                    logger.exception(
                        "StockRelay resistance-approach push failed for %s",
                        cand.symbol,
                    )

        crud.update_live_trading_state(
            db, mode="live", enabled=True, last_tick_at=_now(), last_data_at=last_data_ts
        )

        # Push SSE events to connected browsers
        _emit_sse_state(db, mode="live", market_open=True)


def _emit_sse_state(db, mode: str = "live", market_open: bool = True) -> None:
    """Publish the full live-trading snapshot to SSE subscribers."""
    try:
        from app.db.models import LiveTradeCandidate

        state = crud.get_full_live_trading_state(
            db, market_open=market_open, mode=mode
        )
        _publish_sse("state", state)

        candidates = [
            _enrich_candidate_for_ui(_candidate_to_dict(c))
            for c in db.query(LiveTradeCandidate).all()
        ]
        _publish_sse("candidates", {"candidates": candidates})

        preview = crud.get_preview_strategy_key(db)
        # list_live_trades already returns fully serialized dicts
        all_trades = crud.list_live_trades(db, status="all", strategy=preview)
        _publish_sse("trades", {"trades": all_trades, "status": "all"})
    except Exception:
        logger.exception("Failed to emit SSE state")


def _candidate_to_dict(c) -> dict:
    return {
        "id": c.id,
        "symbol": c.symbol,
        "source": c.source,
        "company_name": c.company_name,
        "resistance": c.resistance,
        "last_price": c.last_price,
        "target_price": c.target_price,
        "stop_price": c.stop_price,
        "volume_ratio": c.volume_ratio,
        "volume_confirmed": bool(c.volume_confirmed),
        "rationale": c.rationale,
        "status": c.status,
        "notified": bool(c.notified),
        "added_at": c.added_at.isoformat() if c.added_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _worker_entry(stop: mp.synchronize.Event, event_q: mp.Queue) -> None:
    """Process entrypoint — re-init network settings in the child process."""
    global _event_queue
    _event_queue = event_q

    from app.utils.network import configure_market_data_network
    from app.utils.yfinance_quiet import configure_yfinance_logging

    configure_market_data_network()
    configure_yfinance_logging()
    logger.info("Live-trading engine process started (pid=%s)", mp.current_process().pid)
    while not stop.is_set():
        try:
            _tick()
        except Exception:
            logger.exception("Live-trading tick failed")
        stop.wait(TICK_SECONDS)


# ── Public API ───────────────────────────────────────────────────────────────────

def ensure_engine_running() -> mp.Queue | None:
    """Start the engine if the background process died (e.g. after uvicorn reload)."""
    global _process
    with _lock:
        if _process is not None and _process.is_alive():
            return _event_queue
    return start_engine()


def start_engine() -> mp.Queue | None:
    """Start the engine background process once (idempotent). Called at app startup.
    
    Returns the event queue that the parent process should consume from.
    """
    global _process, _stop_event, _event_queue
    with _lock:
        if _process is not None and _process.is_alive():
            return _event_queue
        if _process is not None and not _process.is_alive():
            logger.warning("Live-trading engine process died — restarting")
            _process = None
        _stop_event = mp.Event()
        _event_queue = mp.Queue(maxsize=500)
        _process = mp.Process(
            target=_worker_entry,
            args=(_stop_event, _event_queue),
            name="live-trading-engine",
            daemon=True,
        )
        _process.start()
        logger.info("Live-trading background process launched")
        return _event_queue


def get_state() -> dict[str, Any]:
    ensure_engine_running()
    with SessionLocal() as db:
        state = crud.get_full_live_trading_state(db)
    state["market_open"] = _is_market_open()
    return state


def set_analysis_override(enabled: bool) -> dict[str, Any]:
    """Toggle off-hours analysis mode. Only meaningful when market is closed."""
    with SessionLocal() as db:
        if _is_market_open() and enabled:
            # During market hours the engine picks analysis/live automatically.
            state = crud.get_live_trading_state(db)
            state["market_open"] = True
            return state
        state = crud.update_live_trading_state(
            db,
            analysis_override=enabled,
            enabled=True,
            mode="analysis" if enabled else "market_off",
        )
    start_engine()
    state["market_open"] = _is_market_open()
    return state


def set_entries_paused(paused: bool) -> dict[str, Any]:
    """Kill switch: pause new entries; open trades keep running."""
    with SessionLocal() as db:
        crud.update_live_trading_state(db, entries_paused=paused)
        state = crud.get_full_live_trading_state(db)
    state["market_open"] = _is_market_open()
    _broadcast_live_event("state", state)
    return state


def manual_exit_trade(trade_id: int) -> dict[str, Any]:
    """Close an open trade immediately at the last known price."""
    with SessionLocal() as db:
        from app.db.models import LiveTrade

        trade = db.get(LiveTrade, trade_id)
        if trade is None:
            return {"status": "error", "message": "Trade not found"}
        if trade.status != "open":
            return {"status": "error", "message": "Trade is not open"}

        price = float(trade.last_price or trade.entry_price)
        trade_dict = _close_trade(db, trade, price, "manual_exit", notify=False)
        state = crud.get_full_live_trading_state(db)
        state["market_open"] = _is_market_open()
        preview = crud.get_preview_strategy_key(db)

    if trade_dict.get("strategy") == preview:
        _broadcast_live_event("trade_closed", trade_dict)
    _broadcast_live_event("state", state)
    return {
        "status": "ok",
        "trade": trade_dict,
        "message": f"Manually exited {trade_dict['symbol']}",
    }


def _enrich_candidate_for_ui(c: dict[str, Any]) -> dict[str, Any]:
    """Add entry_point and bullets for the candidate card UI."""
    source = c.get("source", "")
    resistance = c.get("resistance")
    target = c.get("target_price")
    stop = c.get("stop_price")
    vol = c.get("volume_confirmed")
    label = SOURCE_LABELS.get(source, source)
    bullets: list[str] = [f"Watching via {label} screener"]

    if source in ("brst", "multi_year"):
        entry_point = f"Enter when price closes above {_fmt_inr(resistance)} with volume confirmation"
        if vol:
            bullets.append("Volume confirmation met (≥1.5× 50-day average)")
        else:
            bullets.append("Needs volume confirmation before entry")
        if c.get("volume_ratio"):
            bullets.append(f"Volume ratio {c['volume_ratio']}× vs 50-day avg")
    elif source == "darvas":
        entry_point = f"Enter on Darvas Box breakout above {_fmt_inr(resistance)}"
        if vol:
            bullets.append("Volume confirmed on box breakout")
        else:
            bullets.append("Awaiting volume confirmation")
    elif source == "golden":
        entry_point = f"Enter on momentum break above {_fmt_inr(resistance)}"
        bullets.append("Strong QoQ/YoY price, revenue, and profit growth")
    elif source == "weekly":
        entry_point = f"Enter on weekly momentum above {_fmt_inr(resistance)}"
        bullets.append("Weekly price momentum with growing financials")
    elif source == "mean_reversion":
        entry_point = f"Buy the pullback near {_fmt_inr(resistance)}"
        bullets.append("Uptrend pullback — mean-reversion bounce candidate")
    elif source == "vol_squeeze":
        entry_point = f"Enter on range breakout above {_fmt_inr(resistance)}"
        bullets.append("Tight pre-breakout range with contracting volatility")
    elif source == "volume_surge":
        entry_point = f"Enter above surge high {_fmt_inr(resistance)} on continued volume"
        bullets.append("Unusual volume surge with strong close")
    else:
        entry_point = f"Enter above {_fmt_inr(resistance)}"

    if target and stop:
        bullets.append(f"Smart Swing: target {_fmt_inr(target)}, stop {_fmt_inr(stop)}")
    bullets.append("Paper trade size: ₹1,00,000 per position")

    return {**c, "entry_point": entry_point, "bullets": bullets}


def list_candidates() -> list[dict[str, Any]]:
    with SessionLocal() as db:
        rows = crud.list_live_candidates(db)
    return [_enrich_candidate_for_ui(c) for c in rows]


def list_trades(status: str = "all", strategy: str | None = None) -> list[dict[str, Any]]:
    with SessionLocal() as db:
        if strategy is None:
            strategy = crud.get_preview_strategy_key(db)
        return crud.list_live_trades(db, status=status, strategy=strategy)


def set_preview_strategy(strategy_key: str) -> dict[str, Any]:
    """Set which strategy wallet drives the main dashboard."""
    with SessionLocal() as db:
        try:
            crud.set_preview_strategy(db, strategy_key)
        except ValueError as exc:
            return {"status": "error", "message": str(exc)}
        state = crud.get_full_live_trading_state(db)
    state["market_open"] = _is_market_open()
    _broadcast_live_event("state", state)
    with SessionLocal() as db:
        preview = crud.get_preview_strategy_key(db)
        trades = crud.list_live_trades(db, status="all", strategy=preview)
    _broadcast_live_event("trades", {"trades": trades, "status": "all"})
    return state


def force_reset_portfolio() -> dict[str, Any]:
    """Clear all trades/candidates and restore 8 × ₹10L strategy wallets."""
    from sqlalchemy import inspect, text

    from app.db.database import engine
    from app.db.models import LiveStrategyPortfolio

    insp = inspect(engine)
    with engine.begin() as conn:
        if "live_trades" in insp.get_table_names():
            conn.execute(text("DELETE FROM live_trades"))
        if "live_trade_candidates" in insp.get_table_names():
            conn.execute(text("DELETE FROM live_trade_candidates"))
        if "live_trading_state" in insp.get_table_names():
            cols = {c["name"] for c in insp.get_columns("live_trading_state")}
            updates = [
                "starting_capital = 1000000.0",
                "capital_per_trade = 100000.0",
                "entries_paused = FALSE",
            ]
            if "preview_strategy" in cols:
                updates.append("preview_strategy = 'smart_swing'")
            conn.execute(
                text(
                    f"UPDATE live_trading_state SET {', '.join(updates)} WHERE id = 1"
                )
            )

    with SessionLocal() as db:
        for row in db.query(LiveStrategyPortfolio).all():
            row.starting_capital = 1_000_000.0
            row.capital_per_trade = 100_000.0
            row.is_preview = row.strategy_key == "smart_swing"
        db.commit()
        state = crud.get_full_live_trading_state(db)

    state["market_open"] = _is_market_open()
    _broadcast_live_event("state", state)
    _broadcast_live_event("trades", {"trades": [], "status": "all"})
    _broadcast_live_event("candidates", {"candidates": []})
    return {
        "status": "ok",
        "message": "All trades and candidates cleared; 8 wallets reset to ₹10L.",
        "state": state,
    }


def _fmt_ist(iso: str | None) -> str:
    if not iso:
        return "-"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.astimezone(IST).strftime("%d %b %Y, %I:%M %p IST")
    except Exception:
        return iso or "-"


def send_client_report() -> dict[str, Any]:
    """Email the comprehensive EOD insight report to the configured client address."""
    from app.services.report_generator import send_eod_report
    return send_eod_report()


# ── Strategy comparison ────────────────────────────────────────────────────────

def _compute_atr(bars: list[dict[str, Any]], window: int = 14) -> float:
    """Compute Average True Range from bars (needs at least `window` bars)."""
    if len(bars) < 2:
        return 0.0
    trs: list[float] = []
    for i in range(1, len(bars)):
        prev_close = bars[i - 1]["close"]
        h, l = bars[i]["high"], bars[i]["low"]
        tr = max(h - l, abs(h - prev_close), abs(l - prev_close))
        trs.append(tr)
    if len(trs) < window:
        return sum(trs) / len(trs) if trs else 0.0
    return sum(trs[-window:]) / window


def _simulate(
    entry_price: float,
    bars: list[dict[str, Any]],
    seed_closes: list[float],
    strat: dict[str, Any],
    entry_time_iso: str | None = None,
) -> dict[str, Any]:
    """Simulate one exit strategy over daily bars starting at entry."""
    peak = entry_price
    trough = entry_price
    closes: list[float] = list(seed_closes)
    sma_window = strat.get("sma_window", 20)
    stop_level = entry_price * (1 + strat["sl_pct"] / 100) if strat["sl_pct"] is not None else None
    tgt_level = entry_price * (1 + strat["tp_pct"] / 100) if strat["tp_pct"] is not None else None

    # ATR-adaptive: compute levels from seed bars' ATR
    if strat.get("atr_tp_mult") is not None:
        atr_window = strat.get("atr_window", 14)
        # Build pseudo-bars from seed_closes for ATR (approximate h/l as close)
        seed_bars = [{"high": c * 1.005, "low": c * 0.995, "close": c} for c in seed_closes]
        atr = _compute_atr(seed_bars, atr_window) if len(seed_bars) >= 2 else entry_price * 0.02
        if atr < entry_price * 0.005:
            atr = entry_price * 0.02
        tgt_level = entry_price + atr * strat["atr_tp_mult"]
        stop_level = entry_price - atr * strat["atr_sl_mult"]

    for i, bar in enumerate(bars):
        high = bar["high"]
        low = bar["low"]
        close = bar["close"]
        closes.append(close)
        days = i + 1
        peak = max(peak, high)
        trough = min(trough, low)

        bar_date = bar.get("date")
        if stop_level is not None and low <= stop_level:
            return _sim_exit(entry_price, stop_level, "stop_loss", days, peak, trough, bar_date, entry_time_iso)
        if tgt_level is not None and high >= tgt_level:
            return _sim_exit(entry_price, tgt_level, "target", days, peak, trough, bar_date, entry_time_iso)
        if strat.get("trail_after_pct") is not None and (peak / entry_price - 1) * 100 >= strat["trail_after_pct"]:
            trail_level = peak * (1 - strat["trail_gap_pct"] / 100)
            if low <= trail_level:
                return _sim_exit(entry_price, trail_level, "trailing_stop", days, peak, trough, bar_date, entry_time_iso)
        if strat.get("sma_exit") and len(closes) >= sma_window:
            sma = sum(closes[-sma_window:]) / sma_window
            if close < sma:
                return _sim_exit(entry_price, close, "sma_exit", days, peak, trough, bar_date, entry_time_iso)
        if strat.get("time_stop_days") is not None and days >= strat["time_stop_days"]:
            if (close / entry_price - 1) * 100 < strat["time_stop_min_pct"]:
                return _sim_exit(entry_price, close, "time_stop", days, peak, trough, bar_date, entry_time_iso)

    last = closes[-1] if closes else entry_price
    last_date = bars[-1].get("date") if bars else None
    result = _sim_exit(entry_price, last, "open", len(bars), peak, trough, last_date, entry_time_iso)
    result["open"] = True
    return result


def _sim_exit(entry: float, exit_price: float, reason: str, days: int,
              peak: float = 0, trough: float = 0,
              exit_date: str | None = None,
              entry_time_iso: str | None = None) -> dict[str, Any]:
    pnl_pct = (exit_price / entry - 1) * 100
    exit_time = _sim_exit_timestamp(exit_date, entry_time_iso)
    return {
        "exit_price": round(exit_price, 2),
        "exit_reason": reason,
        "exit_time": exit_time,
        "pnl_pct": round(pnl_pct, 2),
        "days_held": days,
        "peak_price": round(peak, 2),
        "trough_price": round(trough, 2),
        "open": False,
    }


def _trade_actual_pnl(trade: dict[str, Any]) -> tuple[float, float]:
    """Realized or mark-to-market P&L for an executed live trade."""
    if trade.get("status") == "closed":
        return float(trade.get("pnl_abs") or 0), float(trade.get("pnl_pct") or 0)
    entry = float(trade["entry_price"])
    last = float(trade.get("last_price") or entry)
    qty = float(trade["qty"])
    pnl_abs = round(qty * (last - entry), 2)
    pnl_pct = round((last / entry - 1) * 100, 2) if entry else 0.0
    return pnl_abs, pnl_pct


def _trade_to_strategy_row(trade: dict[str, Any]) -> dict[str, Any]:
    """Map a live trade to the strategy drill-down row format (actual execution)."""
    closed = trade.get("status") == "closed"
    pnl_abs, pnl_pct = _trade_actual_pnl(trade)
    entry_price = float(trade["entry_price"])
    exit_px = (
        float(trade["exit_price"])
        if closed and trade.get("exit_price") is not None
        else float(trade.get("last_price") or entry_price)
    )
    return {
        "symbol": trade["symbol"],
        "company_name": trade.get("company_name"),
        "source": trade.get("source"),
        "entry_price": entry_price,
        "entry_time": trade.get("entry_time"),
        "exit_price": exit_px,
        "exit_time": trade.get("exit_time"),
        "exit_reason": trade.get("exit_reason") or ("open" if not closed else "-"),
        "pnl_pct": pnl_pct,
        "pnl_abs": pnl_abs,
        "days_held": trade.get("days_held") or 0,
        "peak_price": trade.get("peak_price"),
        "trough_price": trade.get("trough_price"),
        "qty": trade["qty"],
        "notional": trade.get("notional") or round(float(trade["qty"]) * entry_price, 2),
        "is_open": not closed,
    }


def _executed_strategy_summary_row(
    trades: list[dict[str, Any]],
    strat: dict[str, Any],
    *,
    is_preview: bool = False,
) -> dict[str, Any]:
    """Aggregate stats from real DB trades for one strategy wallet."""
    pnls_pct: list[float] = []
    pnls_abs: list[float] = []
    wins = 0
    for trade in trades:
        pnl_abs, pnl_pct = _trade_actual_pnl(trade)
        pnls_abs.append(pnl_abs)
        pnls_pct.append(pnl_pct)
        if pnl_abs >= 0:
            wins += 1
    n = len(trades)
    total_pnl_abs = round(sum(pnls_abs), 2)
    total_invested = sum(float(t.get("notional") or 0) for t in trades)
    total_pct = round(total_pnl_abs / total_invested * 100, 2) if total_invested else 0.0
    avg_pct = round(sum(pnls_pct) / n, 2) if n else 0.0
    return {
        "key": strat["key"],
        "label": strat["label"],
        "executed": True,
        "is_preview": is_preview,
        "trades": n,
        "wins": wins,
        "win_rate": round(wins / n * 100, 1) if n else 0.0,
        "avg_pct": avg_pct,
        "total_pnl_abs": total_pnl_abs,
        "total_pct": total_pct,
        "total_invested": round(total_invested, 2),
        # Open-position marks so the UI can re-value the row from streamed
        # live ticks between engine refreshes.
        "open_trades": [
            {
                "symbol": t["symbol"],
                "qty": t["qty"],
                "entry_price": t["entry_price"],
                "last_price": t.get("last_price"),
            }
            for t in trades
            if t.get("status") == "open"
        ],
    }


def _load_daily_bars(symbol: str) -> list[dict[str, Any]] | None:
    df = load_daily_history(symbol, period="1y", min_rows=20)
    if df is None or df.empty:
        return None
    return [
        {
            "date": idx.strftime("%Y-%m-%d"),
            "high": float(r["high"]) if r["high"] is not None else float(r["close"]),
            "low": float(r["low"]) if r["low"] is not None else float(r["close"]),
            "close": float(r["close"]),
        }
        for idx, r in df.iterrows()
    ]


def strategy_summary() -> dict[str, Any]:
    """Per-strategy aggregates from real parallel paper trades."""
    with SessionLocal() as db:
        preview = crud.get_preview_strategy_key(db)
        summaries = []
        trade_counts: list[int] = []
        capital = 100_000.0
        for strat in STRATEGIES:
            portfolio = crud.get_strategy_portfolio(db, strat["key"])
            if portfolio:
                capital = float(portfolio.capital_per_trade)
            trades = crud.list_live_trades(db, status="all", strategy=strat["key"])
            trade_counts.append(len(trades))
            summaries.append(
                _executed_strategy_summary_row(
                    trades,
                    strat,
                    is_preview=strat["key"] == preview,
                )
            )

    return {
        "capital_per_trade": capital,
        "trade_count": max(trade_counts) if trade_counts else 0,
        "preview_strategy": preview,
        "strategies": summaries,
    }


def _simulate_strategy_trade(
    trade: dict[str, Any],
    strat: dict[str, Any],
    capital: float,
    daily_cache: dict[str, list[dict[str, Any]] | None] | None = None,
    minute_cache: dict[str, list[dict[str, Any]] | None] | None = None,
) -> dict[str, Any] | None:
    """Simulate one strategy on a trade; minute bars only for same-day entries."""
    symbol = trade["symbol"]
    entry_price = trade["entry_price"]
    entry_time_iso = trade.get("entry_time")
    entry_date = (entry_time_iso or "")[:10]
    entry_dt = _parse_iso_ist(entry_time_iso)
    now_ist = _now().astimezone(IST)

    # Minute-level sim only for today's entries (fast + accurate exit time).
    if entry_dt and entry_dt.date() == now_ist.date():
        if minute_cache is not None and symbol in minute_cache:
            df_min = minute_cache[symbol]
        else:
            df_min = load_minute_history(symbol, period="1d")
            if minute_cache is not None:
                minute_cache[symbol] = df_min
        if df_min is not None and not getattr(df_min, "empty", True):
            entry_utc = entry_dt.astimezone(timezone.utc)
            post_min: list[dict[str, Any]] = []
            for idx, r in df_min.iterrows():
                bar_time = idx.isoformat() if hasattr(idx, "isoformat") else str(idx)
                try:
                    bt = datetime.fromisoformat(bar_time.replace("Z", "+00:00"))
                    if bt.tzinfo is None:
                        bt = bt.replace(tzinfo=timezone.utc)
                    if bt >= entry_utc:
                        post_min.append({
                            "time": bar_time,
                            "high": float(r["high"]) if r["high"] is not None else float(r["close"]),
                            "low": float(r["low"]) if r["low"] is not None else float(r["close"]),
                            "close": float(r["close"]),
                            "volume": float(r.get("volume", 0)),
                        })
                except Exception:
                    continue
            if post_min:
                sim = _simulate_minute(entry_price, post_min, strat)
                qty = _whole_share_qty(capital, entry_price)
                if qty < 1:
                    return None
                pnl_abs = round(qty * (sim["exit_price"] - entry_price), 2)
                exit_time = _clamp_exit_time_iso(sim.get("exit_time"))
                days_held = max(1, (now_ist.date() - entry_dt.date()).days + 1) if not sim.get("open") else 0
                if sim.get("open"):
                    days_held = max(1, (now_ist.date() - entry_dt.date()).days + 1)
                return {
                    "symbol": symbol,
                    "company_name": trade.get("company_name"),
                    "source": trade.get("source"),
                    "entry_price": entry_price,
                    "entry_time": entry_time_iso,
                    "exit_price": sim["exit_price"],
                    "exit_time": exit_time,
                    "exit_reason": sim["exit_reason"],
                    "pnl_pct": sim["pnl_pct"],
                    "pnl_abs": pnl_abs,
                    "days_held": days_held,
                    "peak_price": sim.get("peak_price"),
                    "trough_price": sim.get("trough_price"),
                    "qty": qty,
                    "notional": round(qty * entry_price, 2),
                    "is_open": sim.get("open", False),
                }

    if daily_cache is not None:
        if symbol not in daily_cache:
            daily_cache[symbol] = _load_daily_bars(symbol)
        rows = daily_cache[symbol]
    else:
        rows = _load_daily_bars(symbol)
    if not rows:
        return None
    post = [b for b in rows if b["date"] >= entry_date]
    seed = [b["close"] for b in rows if b["date"] < entry_date][-25:]
    if not post:
        return None
    sim = _simulate(entry_price, post, seed, strat, entry_time_iso=entry_time_iso)
    qty = _whole_share_qty(capital, entry_price)
    if qty < 1:
        return None
    pnl_abs = round(qty * (sim["exit_price"] - entry_price), 2)
    exit_time = _clamp_exit_time_iso(sim.get("exit_time"))
    if not sim.get("open") and not exit_time and trade.get("exit_time"):
        exit_time = _clamp_exit_time_iso(trade.get("exit_time"))
    return {
        "symbol": symbol,
        "company_name": trade.get("company_name"),
        "source": trade.get("source"),
        "entry_price": entry_price,
        "entry_time": entry_time_iso,
        "exit_price": sim["exit_price"],
        "exit_time": exit_time,
        "exit_reason": sim["exit_reason"],
        "pnl_pct": sim["pnl_pct"],
        "pnl_abs": pnl_abs,
        "days_held": sim["days_held"],
        "peak_price": sim.get("peak_price"),
        "trough_price": sim.get("trough_price"),
        "qty": qty,
        "notional": round(qty * entry_price, 2),
        "is_open": sim.get("open", False),
    }


def strategy_trades(strategy_key: str) -> dict[str, Any]:
    """Return per-trade results for one strategy from DB."""
    strat = STRATEGY_BY_KEY.get(strategy_key)
    if strat is None:
        return {"error": f"Unknown strategy: {strategy_key}", "trades": []}

    with SessionLocal() as db:
        portfolio = crud.get_strategy_portfolio(db, strategy_key)
        capital = float(portfolio.capital_per_trade) if portfolio else 100_000.0
        trades = crud.list_live_trades(db, status="all", strategy=strategy_key)

    return {
        "strategy_key": strategy_key,
        "strategy_label": strat["label"],
        "capital_per_trade": capital,
        "trades": [_trade_to_strategy_row(t) for t in trades],
    }


# ── Minute-level intraday backtest ────────────────────────────────────────────

def _simulate_minute(entry_price: float, bars: list[dict[str, Any]],
                     strat: dict[str, Any]) -> dict[str, Any]:
    """Simulate a strategy on minute-level bars. Returns per-trade result dict."""
    peak = entry_price
    trough = entry_price
    stop_level = entry_price * (1 + strat["sl_pct"] / 100) if strat["sl_pct"] is not None else None
    tgt_level = entry_price * (1 + strat["tp_pct"] / 100) if strat["tp_pct"] is not None else None
    closes: list[float] = []
    sma_window = strat.get("sma_window", 20)

    # ATR-adaptive: approximate ATR from first 14 bars
    if strat.get("atr_tp_mult") is not None:
        atr_window = strat.get("atr_window", 14)
        seed_bars = bars[:atr_window] if len(bars) > atr_window else bars[:max(2, len(bars))]
        atr = _compute_atr(seed_bars, atr_window) if len(seed_bars) >= 2 else entry_price * 0.005
        if atr < entry_price * 0.001:
            atr = entry_price * 0.005
        tgt_level = entry_price + atr * strat["atr_tp_mult"]
        stop_level = entry_price - atr * strat["atr_sl_mult"]

    exit_time = None
    for i, bar in enumerate(bars):
        high = bar["high"]
        low = bar["low"]
        close = bar["close"]
        closes.append(close)
        minutes = i + 1
        peak = max(peak, high)
        trough = min(trough, low)

        if stop_level is not None and low <= stop_level:
            return _sim_exit_minute(entry_price, stop_level, "stop_loss", minutes, peak, trough, bar.get("time"))
        if tgt_level is not None and high >= tgt_level:
            return _sim_exit_minute(entry_price, tgt_level, "target", minutes, peak, trough, bar.get("time"))
        if strat.get("trail_after_pct") is not None and (peak / entry_price - 1) * 100 >= strat["trail_after_pct"]:
            trail_level = peak * (1 - strat["trail_gap_pct"] / 100)
            if low <= trail_level:
                return _sim_exit_minute(entry_price, trail_level, "trailing_stop", minutes, peak, trough, bar.get("time"))
        if strat.get("sma_exit") and len(closes) >= sma_window:
            sma = sum(closes[-sma_window:]) / sma_window
            if close < sma:
                return _sim_exit_minute(entry_price, close, "sma_exit", minutes, peak, trough, bar.get("time"))

    last = closes[-1] if closes else entry_price
    result = _sim_exit_minute(entry_price, last, "open", len(bars), peak, trough,
                               bars[-1].get("time") if bars else None)
    result["open"] = True
    return result


def _sim_exit_minute(entry: float, exit_price: float, reason: str, minutes: int,
                     peak: float, trough: float, exit_time: str | None = None) -> dict[str, Any]:
    pnl_pct = (exit_price / entry - 1) * 100
    return {
        "exit_price": round(exit_price, 2),
        "exit_reason": reason,
        "pnl_pct": round(pnl_pct, 2),
        "minutes_held": minutes,
        "peak_price": round(peak, 2),
        "trough_price": round(trough, 2),
        "exit_time": _clamp_exit_time_iso(exit_time),
        "open": False,
    }


def backtest_intraday() -> dict[str, Any]:
    """
    Run all strategies on each traded stock using minute-level yfinance data
    (last 7 days). Entry is assumed at the actual entry_price from the trade.
    """
    with SessionLocal() as db:
        state = crud.get_live_trading_state(db)
        trades = crud.list_live_trades(db, status="all")
    capital = state["capital_per_trade"] or 100000.0

    per_strategy: dict[str, list[dict[str, Any]]] = {s["key"]: [] for s in STRATEGIES}
    symbols_processed: list[str] = []
    errors: list[str] = []

    for trade in trades:
        symbol = trade["symbol"]
        entry_price = trade["entry_price"]

        df = load_minute_history(symbol, period="7d")
        if df is None or df.empty:
            errors.append(f"{symbol}: no minute data")
            continue

        bars = [
            {
                "time": idx.isoformat() if hasattr(idx, "isoformat") else str(idx),
                "high": float(r["high"]) if r["high"] is not None else float(r["close"]),
                "low": float(r["low"]) if r["low"] is not None else float(r["close"]),
                "close": float(r["close"]),
                "volume": float(r.get("volume", 0)),
            }
            for idx, r in df.iterrows()
        ]
        if not bars:
            continue

        symbols_processed.append(symbol)

        for strat in STRATEGIES:
            sim = _simulate_minute(entry_price, bars, strat)
            qty = _whole_share_qty(capital, entry_price)
            if qty < 1:
                continue
            pnl_abs = round(qty * (sim["exit_price"] - entry_price), 2)
            per_strategy[strat["key"]].append({
                "symbol": symbol,
                "company_name": trade.get("company_name"),
                "entry_price": entry_price,
                "exit_price": sim["exit_price"],
                "exit_reason": sim["exit_reason"],
                "exit_time": sim.get("exit_time"),
                "pnl_pct": sim["pnl_pct"],
                "pnl_abs": pnl_abs,
                "minutes_held": sim["minutes_held"],
                "peak_price": sim.get("peak_price"),
                "trough_price": sim.get("trough_price"),
                "qty": qty,
                "notional": round(qty * entry_price, 2),
                "is_open": sim.get("open", False),
            })

    strategy_results: list[dict[str, Any]] = []
    for strat in STRATEGIES:
        strat_trades = per_strategy[strat["key"]]
        n = len(strat_trades)
        pnls = [t["pnl_pct"] for t in strat_trades]
        wins = sum(1 for p in pnls if p >= 0)
        avg_pct = round(sum(pnls) / n, 2) if n else 0.0
        total_pnl_abs = round(sum(t["pnl_abs"] for t in strat_trades), 2)
        total_invested = capital * n
        total_pct = round(total_pnl_abs / total_invested * 100, 2) if total_invested else 0.0
        strategy_results.append({
            "key": strat["key"],
            "label": strat["label"],
            "executed": strat["key"] == SMART_SWING["key"],
            "trades": n,
            "wins": wins,
            "win_rate": round(wins / n * 100, 1) if n else 0.0,
            "avg_pct": avg_pct,
            "total_pnl_abs": total_pnl_abs,
            "total_pct": total_pct,
            "per_trade": strat_trades,
        })

    return {
        "data_source": "yfinance 1-minute (last 7 days)",
        "capital_per_trade": capital,
        "symbols_tested": symbols_processed,
        "symbols_count": len(symbols_processed),
        "errors": errors,
        "strategies": strategy_results,
    }

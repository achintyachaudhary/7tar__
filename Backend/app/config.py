"""Application configuration and Nifty 50 watchlist."""

import os
from pathlib import Path

# Data fetch
HISTORY_PERIOD = "6mo"
CACHE_TTL_SECONDS = 900  # 15 minutes

# Screening defaults
DEFAULT_MIN_SCORE = 5
DEFAULT_SCAN_LIMIT = 50

# RSI thresholds
RSI_BULLISH_LOW = 50
RSI_BULLISH_HIGH = 70
RSI_RISING_LOW = 40
RSI_OVERBOUGHT = 70

# Indicator windows
RSI_WINDOW = 14
SMA_SHORT = 20
SMA_LONG = 50
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

# Nifty 50 constituents (NSE .NS suffix)
NIFTY_50_TICKERS: list[str] = [
    "ADANIENT.NS",
    "ADANIPORTS.NS",
    "APOLLOHOSP.NS",
    "ASIANPAINT.NS",
    "AXISBANK.NS",
    "BAJAJ-AUTO.NS",
    "BAJFINANCE.NS",
    "BAJAJFINSV.NS",
    "BPCL.NS",
    "BHARTIARTL.NS",
    "BRITANNIA.NS",
    "CIPLA.NS",
    "COALINDIA.NS",
    "DIVISLAB.NS",
    "DRREDDY.NS",
    "EICHERMOT.NS",
    "GRASIM.NS",
    "HCLTECH.NS",
    "HDFCBANK.NS",
    "HDFCLIFE.NS",
    "HEROMOTOCO.NS",
    "HINDALCO.NS",
    "HINDUNILVR.NS",
    "ICICIBANK.NS",
    "ITC.NS",
    "INDUSINDBK.NS",
    "INFY.NS",
    "JSWSTEEL.NS",
    "KOTAKBANK.NS",
    "LT.NS",
    "M&M.NS",
    "MARUTI.NS",
    "NESTLEIND.NS",
    "NTPC.NS",
    "ONGC.NS",
    "POWERGRID.NS",
    "RELIANCE.NS",
    "SBILIFE.NS",
    "SBIN.NS",
    "SUNPHARMA.NS",
    "TCS.NS",
    "TATACONSUM.NS",
    "TATAMOTORS.NS",
    "TATASTEEL.NS",
    "TECHM.NS",
    "TITAN.NS",
    "ULTRACEMCO.NS",
    "UPL.NS",
    "WIPRO.NS",
]

# Parallel workers for DB-backed scans (screeners read stock_prices_daily only)
SCAN_MAX_WORKERS = int(os.getenv("SCAN_MAX_WORKERS", "10"))
SCAN_MAX_WORKERS_DB = int(os.getenv("SCAN_MAX_WORKERS_DB", "30"))

# Legacy: live API fetches (non-scanner paths only)
SCAN_MAX_WORKERS_LARGE = int(os.getenv("SCAN_MAX_WORKERS_LIVE", "5"))
YFINANCE_REQUEST_DELAY = float(os.getenv("YFINANCE_REQUEST_DELAY", "0.8"))

# WebSocket scan:progress throttle (emit every N symbols)
SCAN_PROGRESS_INTERVAL = int(os.getenv("SCAN_PROGRESS_INTERVAL", "15"))

# Day Scan historical backfill target (years)
DAY_SCAN_HISTORY_YEARS = 5

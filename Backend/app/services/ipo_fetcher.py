"""Fetch recent IPO listings from NSE."""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

from app.utils.network import make_requests_session
from app.watchlists.loader import NSE_HEADERS

logger = logging.getLogger(__name__)

PAST_IPO_URL = "https://www.nseindia.com/api/public-past-issues"
CACHE_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "cache" / "past_ipos.json"
)
CACHE_TTL = 3600  # 1 hour

# Equity IPO series on NSE (excludes NCDs, REITs, debt, etc.)
EQUITY_IPO_TYPES = frozenset({"EQ", "SME", "BE"})

# Symbols that look like NCDs / bonds / partly-paid — not Yahoo-tradeable equity
_BOND_LIKE_SYMBOL = re.compile(
    r"^\d"  # starts with digit e.g. 10MWL29
    r"|\d{2,}[A-Z]{2,}\d"  # 1275DCCL28
    r"|ENPP|PP\d*$|MWL|NCD|DEBT|BOND",
    re.IGNORECASE,
)
_VALID_EQUITY_SYMBOL = re.compile(r"^[A-Z][A-Z0-9&.-]{1,19}$")


def is_tradeable_equity_symbol(symbol: str) -> bool:
    """
    NSE past-IPO feed includes debt and structured products labeled as listings.
    Skip symbols Yahoo Finance cannot map to listed equity.
    """
    symbol = (symbol or "").strip().upper()
    if not symbol or not _VALID_EQUITY_SYMBOL.match(symbol):
        return False
    if _BOND_LIKE_SYMBOL.search(symbol):
        return False
    # Require mostly letters (filters codes like '1275DCCL28')
    letters = sum(c.isalpha() for c in symbol)
    if letters < max(2, len(symbol) // 2):
        return False
    return True

_memory: tuple[float, list[dict]] | None = None


def _nse_session() -> requests.Session:
    session = make_requests_session()
    session.headers.update(NSE_HEADERS)
    session.get("https://www.nseindia.com", timeout=15)
    return session


def _parse_nse_date(raw: str) -> datetime | None:
    raw = (raw or "").strip()
    if not raw or raw == "-":
        return None
    for fmt in ("%d-%b-%Y", "%d-%B-%Y"):
        try:
            return datetime.strptime(raw.upper(), fmt)
        except ValueError:
            continue
    return None


def _parse_issue_price(issue_price: str, price_range: str) -> float | None:
    issue_price = (issue_price or "").strip()
    if issue_price and issue_price != "-":
        try:
            return float(issue_price)
        except ValueError:
            pass

    if price_range:
        nums = re.findall(r"[\d.]+", price_range.replace(",", ""))
        if nums:
            return float(nums[-1])
    return None


def fetch_all_past_ipos() -> list[dict]:
    """Download full past-IPO list from NSE (cached)."""
    global _memory
    now = time.time()
    if _memory and now < _memory[0]:
        return _memory[1]

    if CACHE_PATH.exists():
        try:
            payload = json.loads(CACHE_PATH.read_text())
            if now - payload.get("fetched_at", 0) < CACHE_TTL:
                rows = payload.get("rows", [])
                _memory = (now + 300, rows)
                return rows
        except (json.JSONDecodeError, OSError):
            pass

    session = _nse_session()
    response = session.get(
        PAST_IPO_URL,
        params={"category": "ipo"},
        timeout=45,
    )
    response.raise_for_status()
    rows = response.json()
    if not isinstance(rows, list):
        rows = []

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps({"fetched_at": now, "rows": rows}))
    _memory = (now + 300, rows)
    logger.info("Fetched %d past IPO rows from NSE", len(rows))
    return rows


def filter_recent_ipos(rows: list[dict], months: int = 2) -> list[dict]:
    """Keep IPOs with a valid listing date in the last N months."""
    cutoff = datetime.now() - timedelta(days=months * 30)
    recent: list[dict] = []

    for row in rows:
        listing_dt = _parse_nse_date(row.get("listingDate", ""))
        if listing_dt is None or listing_dt < cutoff:
            continue

        symbol = (row.get("symbol") or "").strip().upper()
        if not symbol or not is_tradeable_equity_symbol(symbol):
            continue

        security_type = (row.get("securityType") or "").strip().upper()
        if security_type and security_type not in EQUITY_IPO_TYPES:
            continue

        issue_price = _parse_issue_price(
            str(row.get("issuePrice", "")),
            str(row.get("priceRange", "")),
        )

        recent.append(
            {
                "symbol": symbol,
                "company_name": row.get("companyName") or row.get("company") or symbol,
                "security_type": security_type or row.get("securityType") or "",
                "ipo_start_date": row.get("ipoStartDate") or "",
                "ipo_end_date": row.get("ipoEndDate") or "",
                "listing_date": listing_dt.strftime("%Y-%m-%d"),
                "listing_date_display": row.get("listingDate", ""),
                "issue_price": issue_price,
                "price_range": row.get("priceRange") or "",
            },
        )

    recent.sort(key=lambda r: r["listing_date"], reverse=True)
    return recent


def filter_all_equity_ipos(
    rows: list[dict],
    *,
    min_listing_year: int = 2018,
    max_listing_days_ago: int = 14,
    months_back: int | None = None,
) -> list[dict]:
    """All equity IPOs with listing date in range (for ML / research dataset)."""
    today = datetime.now()
    if months_back is not None:
        cutoff_min = today - timedelta(days=months_back * 30)
    else:
        cutoff_min = datetime(min_listing_year, 1, 1)
    cutoff_max = today - timedelta(days=max_listing_days_ago)
    out: list[dict] = []

    for row in rows:
        listing_dt = _parse_nse_date(row.get("listingDate", ""))
        if listing_dt is None or listing_dt < cutoff_min or listing_dt > cutoff_max:
            continue

        symbol = (row.get("symbol") or "").strip().upper()
        if not symbol or not is_tradeable_equity_symbol(symbol):
            continue

        security_type = (row.get("securityType") or "").strip().upper()
        if security_type and security_type not in EQUITY_IPO_TYPES:
            continue

        issue_price = _parse_issue_price(
            str(row.get("issuePrice", "")),
            str(row.get("priceRange", "")),
        )

        out.append(
            {
                "symbol": symbol,
                "company_name": row.get("companyName") or row.get("company") or symbol,
                "security_type": security_type or row.get("securityType") or "",
                "ipo_start_date": row.get("ipoStartDate") or "",
                "ipo_end_date": row.get("ipoEndDate") or "",
                "listing_date": listing_dt.strftime("%Y-%m-%d"),
                "listing_date_display": row.get("listingDate", ""),
                "issue_price": issue_price,
                "price_range": row.get("priceRange") or "",
            },
        )

    out.sort(key=lambda r: r["listing_date"], reverse=True)
    return out

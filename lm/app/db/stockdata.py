"""Read-only access to the stock screener tables.

Tries DATABASE_URL (your stock_ai Postgres) first; if it is unreachable or
does not contain the screener tables, falls back to the existing SQLite
database at <repo>/data/app.db so the API always has data to work with.
"""

import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from app.config import DATABASE_URL, SQLITE_FALLBACK

log = logging.getLogger("lm.stockdata")

REQUIRED_TABLE = "stock_prices_daily"

_engine: Engine | None = None
_source: str = "none"


def _normalize(url: str) -> str:
    # venv ships psycopg 3; SQLAlchemy's bare postgresql:// dialect wants psycopg2
    if url.startswith("postgresql://"):
        try:
            import psycopg2  # noqa: F401
        except ImportError:
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _try_engine(url: str) -> Engine | None:
    try:
        eng = create_engine(_normalize(url), pool_pre_ping=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        if REQUIRED_TABLE not in inspect(eng).get_table_names():
            log.warning("connected to %s but table %r missing", url.split("@")[-1], REQUIRED_TABLE)
            return None
        return eng
    except Exception as exc:
        log.warning("cannot use database %s: %s", url.split("@")[-1], exc)
        return None


def get_engine() -> Engine | None:
    global _engine, _source
    if _engine is not None:
        return _engine

    _engine = _try_engine(DATABASE_URL)
    if _engine is not None:
        _source = "postgres" if DATABASE_URL.startswith("postgres") else "database_url"
        return _engine

    if SQLITE_FALLBACK.exists():
        _engine = _try_engine(f"sqlite:///{SQLITE_FALLBACK.as_posix()}")
        if _engine is not None:
            _source = f"sqlite ({SQLITE_FALLBACK.name})"
            return _engine

    _source = "none"
    return None


def data_source() -> str:
    get_engine()
    return _source


def _rows(sql: str, **params) -> list[dict]:
    eng = get_engine()
    if eng is None:
        return []
    try:
        with eng.connect() as conn:
            result = conn.execute(text(sql), params)
            return [dict(r._mapping) for r in result]
    except Exception as exc:
        log.warning("query failed: %s", exc)
        return []


def search_stocks(q: str, limit: int = 12) -> list[dict]:
    like = f"%{q.upper()}%"
    rows = _rows(
        """
        SELECT s.symbol, s.company_name, p.sector, p.industry, p.market_cap_cr
        FROM stock_universe s
        LEFT JOIN stock_profiles p ON p.symbol = s.symbol
        WHERE UPPER(s.symbol) LIKE :like OR UPPER(s.company_name) LIKE :like
        ORDER BY CASE WHEN UPPER(s.symbol) LIKE :prefix THEN 0 ELSE 1 END, s.symbol
        LIMIT :limit
        """,
        like=like, prefix=f"{q.upper()}%", limit=limit,
    )
    if rows:
        return rows
    # stock_universe may be absent — fall back to distinct symbols with prices
    return _rows(
        """
        SELECT DISTINCT symbol, NULL AS company_name, NULL AS sector,
               NULL AS industry, NULL AS market_cap_cr
        FROM stock_prices_daily WHERE UPPER(symbol) LIKE :like
        ORDER BY symbol LIMIT :limit
        """,
        like=like, limit=limit,
    )


def get_profile(symbol: str) -> dict | None:
    rows = _rows(
        "SELECT * FROM stock_profiles WHERE symbol = :s", s=symbol
    )
    return rows[0] if rows else None


def get_snapshot(symbol: str) -> dict | None:
    rows = _rows(
        "SELECT * FROM day_scan_snapshots WHERE symbol = :s", s=symbol
    )
    return rows[0] if rows else None


def get_recent_prices(symbol: str, limit: int = 260) -> list[dict]:
    rows = _rows(
        """
        SELECT trade_date, open, high, low, close, volume
        FROM stock_prices_daily WHERE symbol = :s
        ORDER BY trade_date DESC LIMIT :limit
        """,
        s=symbol, limit=limit,
    )
    return list(reversed(rows))


def get_financials(symbol: str) -> dict:
    quarterly = _rows(
        """
        SELECT period_label, revenue_cr, profit_cr, period_date
        FROM financial_cache WHERE symbol = :s AND is_quarterly = :q
        ORDER BY period_date DESC LIMIT 8
        """,
        s=symbol, q=True,
    )
    yearly = _rows(
        """
        SELECT period_label, revenue_cr, profit_cr, period_date
        FROM financial_cache WHERE symbol = :s AND is_quarterly = :q
        ORDER BY period_date DESC LIMIT 5
        """,
        s=symbol, q=False,
    )
    return {"quarterly": quarterly, "yearly": yearly}


def get_holdings(symbol: str) -> dict | None:
    rows = _rows(
        """
        SELECT promoter_pct, fii_pct, dii_pct, public_pct, retail_pct, as_of
        FROM holdings_cache WHERE symbol = :s
        """,
        s=symbol,
    )
    return rows[0] if rows else None


def compute_price_summary(prices: list[dict]) -> dict | None:
    """Derive last price, returns and 52w range from the daily series."""
    closes = [p["close"] for p in prices if p.get("close") is not None]
    if not closes:
        return None

    def ret(days_back: int) -> float | None:
        if len(closes) <= days_back:
            return None
        prev = closes[-1 - days_back]
        return round((closes[-1] - prev) / prev * 100, 2) if prev else None

    return {
        "last_close": closes[-1],
        "last_date": prices[-1].get("trade_date"),
        "return_1w_pct": ret(5),
        "return_1m_pct": ret(21),
        "return_3m_pct": ret(63),
        "return_1y_pct": ret(250),
        "high_52w": max(closes[-250:]),
        "low_52w": min(closes[-250:]),
    }

"""DB-only financials and shareholding loaders for Golden / Weekly screeners."""

from __future__ import annotations

from app.services.holdings import _normalize_shareholding_period
from app.services.scan_context import get_scan_context, normalize_symbol


def load_quarterly_financials_db(symbol: str) -> list[dict]:
    """Quarterly financials from preloaded scan cache or DB."""
    sym = normalize_symbol(symbol)
    ctx = get_scan_context()
    if ctx is not None:
        return list(ctx.financials_quarterly.get(sym, []))

    from app.db import crud
    from app.db.database import SessionLocal

    with SessionLocal() as db:
        return crud.get_financials_rows(db, sym, is_quarterly=True)


def load_shareholding_db(symbol: str) -> list[dict]:
    """Shareholding history from preloaded scan cache or DB."""
    sym = normalize_symbol(symbol)
    ctx = get_scan_context()
    if ctx is not None:
        history = ctx.holdings_history.get(sym, [])
        if not history:
            return []
        return [_normalize_shareholding_period(p) for p in history[:5]]

    from app.db import crud
    from app.db.database import SessionLocal

    with SessionLocal() as db:
        history = crud.get_holdings_history(db, sym)
        if not history:
            return []
        return [_normalize_shareholding_period(p) for p in history[:5]]

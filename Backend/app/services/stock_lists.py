"""Favorite / blacklist symbol lists — shared helpers for scanners and API."""

from __future__ import annotations

from typing import Any, Iterable

from app.db import crud
from app.db.database import SessionLocal
from app.services.live_trading import _fetch_quotes, _is_market_open
from app.services.price_alerts import _change_7d_pct, _normalize_symbol


def normalize_list_symbol(symbol: str) -> str:
    sym = symbol.upper().strip()
    if not sym:
        return sym
    if not sym.endswith((".NS", ".BO")):
        return f"{sym}.NS"
    return sym


def filter_blacklisted(symbols: Iterable[str], blacklist: set[str]) -> list[str]:
    if not blacklist:
        return list(symbols)
    return [s for s in symbols if normalize_list_symbol(s) not in blacklist]


def filter_blacklisted_matches(matches: list[dict], blacklist: set[str]) -> list[dict]:
    if not blacklist:
        return matches
    out: list[dict] = []
    for m in matches:
        sym = normalize_list_symbol(str(m.get("symbol") or ""))
        if sym and sym not in blacklist:
            out.append(m)
    return out


def build_enriched_stock_list_rows() -> list[dict[str, Any]]:
    """Merge favorites/fishy/blacklist into table rows with live market fields."""
    with SessionLocal() as db:
        lists = crud.get_user_stock_lists(db)
        tag_map: dict[str, list[str]] = {}

        def add_tag(entries: list[dict], tag: str) -> None:
            for entry in entries:
                sym = normalize_list_symbol(str(entry.get("symbol") or ""))
                if not sym:
                    continue
                tags = tag_map.setdefault(sym, [])
                if tag not in tags:
                    tags.append(tag)

        add_tag(lists.get("favorites") or [], "favorite")
        add_tag(lists.get("fishy") or [], "fishy")
        add_tag(lists.get("blacklist") or [], "blacklist")

        if not tag_map:
            return []

        symbols = sorted(tag_map.keys())
        from app.db.models import DayScanSnapshot

        snap_rows = (
            db.query(DayScanSnapshot)
            .filter(DayScanSnapshot.symbol.in_(symbols))
            .all()
        )
        snaps = {r.symbol: r for r in snap_rows}
        quotes = _fetch_quotes(symbols)
        market_open = _is_market_open()

        rows: list[dict[str, Any]] = []
        for sym in symbols:
            snap = snaps.get(sym)
            quote = quotes.get(sym)
            ltp: float | None = None
            day_pct: float | None = None
            week_pct: float | None = None
            day_pct_live = False

            if quote:
                ltp = round(float(quote["price"]), 2)
                prev = crud._cached_prev_close(sym, db)
                if prev and prev > 0:
                    day_pct = round((ltp - prev) / prev * 100, 2)
                    day_pct_live = True
                week_pct = _change_7d_pct(sym, ltp, db)

            # Do not use day-scan return_1d_pct during live session — it reflects
            # yesterday's close-to-close move, not today's LTP vs previous close.
            if day_pct is None and not market_open and snap and snap.return_1d_pct is not None:
                day_pct = round(float(snap.return_1d_pct), 2)
            if week_pct is None and snap and snap.return_1w_pct is not None:
                week_pct = round(float(snap.return_1w_pct), 2)

            company = (
                (snap.company_name if snap else None)
                or sym.replace(".NS", "").replace(".BO", "")
            )
            rows.append(
                {
                    "symbol": sym,
                    "company_name": company,
                    "industry": snap.industry if snap else None,
                    "market_cap_cr": snap.market_cap_cr if snap else None,
                    "ltp": ltp if ltp is not None else (snap.last_price if snap else None),
                    "change_day_pct": day_pct,
                    "change_day_pct_live": day_pct_live,
                    "change_7d_pct": week_pct,
                    "tags": tag_map[sym],
                }
            )
        return rows

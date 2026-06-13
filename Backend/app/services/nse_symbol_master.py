"""Official NSE equity symbol masters (main board + SME) — symbol/ISIN/name resolver.

Source of truth for symbol → ISIN and company-name → symbol resolution,
especially for freshly listed IPOs that third-party instrument masters lag.
Seeded from the bundled CSVs in data/cache and refreshed daily from NSE
archives (EQUITY_L.csv / SME_EQUITY_L.csv); a failed refresh silently keeps
the existing files.

Upstox keys all fundamentals/news endpoints on ISIN, so this feeds the
Upstox client as a resolution fallback (instrument_key = "NSE_EQ|<ISIN>").
"""

from __future__ import annotations

import csv
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache"

MASTERS = {
    "main": {
        "file": CACHE_DIR / "nse_equity_master.csv",
        "url": "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv",
    },
    "sme": {
        "file": CACHE_DIR / "nse_sme_equity_master.csv",
        "url": "https://nsearchives.nseindia.com/content/equities/SME_EQUITY_L.csv",
    },
}

REFRESH_SECONDS = 86_400

_lock = threading.Lock()
_rows: list[dict[str, Any]] | None = None
_by_symbol: dict[str, dict[str, Any]] = {}


def _norm_header(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def _parse_listing_date(raw: str) -> str | None:
    """'06-OCT-2008' / '29-May-26' → ISO date."""
    raw = (raw or "").strip()
    for fmt in ("%d-%b-%Y", "%d-%b-%y"):
        try:
            return datetime.strptime(raw.title(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _refresh_file(board: str) -> None:
    """Best-effort daily refresh from NSE archives; keeps the seed on failure."""
    import requests

    from app.utils.network import make_requests_session
    from app.watchlists.loader import NSE_HEADERS

    cfg = MASTERS[board]
    path: Path = cfg["file"]
    if path.exists() and time.time() - path.stat().st_mtime < REFRESH_SECONDS:
        return
    try:
        session = make_requests_session()
        resp = session.get(cfg["url"], headers=NSE_HEADERS, timeout=30)
        resp.raise_for_status()
        if b"SYMBOL" not in resp.content[:200]:
            raise ValueError("unexpected payload")
        path.write_bytes(resp.content)
        logger.info("NSE %s equity master refreshed (%d bytes)", board, len(resp.content))
    except Exception:
        logger.warning("NSE %s master refresh failed — using cached copy", board)
        if path.exists():
            # Bump mtime so a flaky NSE endpoint isn't hammered on every call.
            path.touch()


def _load_rows() -> list[dict[str, Any]]:
    global _rows, _by_symbol
    with _lock:
        if _rows is not None:
            return _rows

        rows: list[dict[str, Any]] = []
        for board, cfg in MASTERS.items():
            _refresh_file(board)
            path: Path = cfg["file"]
            if not path.exists():
                logger.warning("NSE %s master file missing: %s", board, path)
                continue
            try:
                with path.open(encoding="utf-8", errors="replace", newline="") as fh:
                    reader = csv.DictReader(fh)
                    fields = {_norm_header(f): f for f in (reader.fieldnames or [])}
                    sym_f = fields.get("symbol")
                    name_f = fields.get("name_of_company")
                    isin_f = fields.get("isin_number")
                    date_f = fields.get("date_of_listing")
                    if not (sym_f and name_f and isin_f):
                        logger.warning("NSE %s master has unexpected headers", board)
                        continue
                    for rec in reader:
                        symbol = (rec.get(sym_f) or "").strip().upper()
                        isin = (rec.get(isin_f) or "").strip().upper()
                        name = (rec.get(name_f) or "").strip()
                        if not symbol or not isin.startswith("INE"):
                            continue
                        rows.append(
                            {
                                "symbol": symbol,
                                "name": name,
                                "isin": isin,
                                "board": board,
                                "listing_date": _parse_listing_date(rec.get(date_f) or "") if date_f else None,
                            }
                        )
            except Exception:
                logger.exception("Failed to parse NSE %s master", board)

        _rows = rows
        _by_symbol = {r["symbol"]: r for r in rows}
        logger.info("NSE symbol masters loaded: %d equities", len(rows))
        return rows


def all_rows() -> list[dict[str, Any]]:
    return _load_rows()


def resolve_symbol(symbol: str) -> dict[str, Any] | None:
    """RELIANCE / RELIANCE.NS → {symbol, name, isin, board, listing_date}."""
    _load_rows()
    base = symbol.upper().replace(".NS", "").replace(".BO", "").strip()
    return _by_symbol.get(base)


def resolve_by_name(name_key_value: str, *, min_score: float = 0.7) -> dict[str, Any] | None:
    """Fuzzy company-name lookup using the IPO-intel name normalizer."""
    from app.services.ipo_intel import fuzzy_name_score, name_key

    if not name_key_value:
        return None
    best, best_score = None, 0.0
    for row in _load_rows():
        score = fuzzy_name_score(name_key_value, name_key(row["name"]))
        if score > best_score:
            best, best_score = row, score
            if score >= 1.0:
                break
    return best if best is not None and best_score >= min_score else None

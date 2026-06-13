"""Investor / shareholding data from NSE and yfinance."""

from __future__ import annotations

import json
import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import requests
import yfinance as yf

from app.utils.network import make_requests_session, without_proxy
from app.watchlists.loader import NSE_HEADERS

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache" / "holdings"
CACHE_TTL = 86400 * 7  # 7 days

_memory: dict[str, tuple[float, dict]] = {}

SUMMARY_CONTEXT_SUFFIX = "_ContextI"
XBRL_CATEGORY_TAGS = {
    "promoter_holding_pct": "ShareholdingOfPromoterAndPromoterGroup",
    "fii_holding_pct": "InstitutionsForeign",
    "dii_holding_pct": "InstitutionsDomestic",
    "public_holding_pct": "PublicShareholding",
    "mutual_fund_holding_pct": "MutualFundsOrUTI",
}


def _nse_symbol(symbol: str) -> str:
    return symbol.upper().replace(".NS", "").replace(".BO", "")


def _parse_pct(value: str | float | None) -> float | None:
    if value is None:
        return None
    try:
        num = float(str(value).strip().replace(",", ""))
        if num > 100:
            return round(num, 2)
        if 0 <= num <= 1:
            return round(num * 100, 2)
        return round(num, 2)
    except (TypeError, ValueError):
        return None


def _parse_nse_date(raw: str) -> str | None:
    raw = (raw or "").strip()
    return raw if raw and raw != "-" else None


def _nse_session() -> requests.Session:
    session = make_requests_session()
    session.headers.update(NSE_HEADERS)
    session.headers["Referer"] = (
        "https://www.nseindia.com/companies-listing/corporate-filings-shareholding-pattern"
    )
    session.get("https://www.nseindia.com", timeout=15)
    return session


def _fetch_nse_master_list(nse_symbol: str) -> list[dict]:
    session = _nse_session()
    response = session.get(
        "https://www.nseindia.com/api/corporate-share-holdings-master",
        params={"index": "equities", "symbol": nse_symbol},
        timeout=20,
    )
    response.raise_for_status()
    rows = response.json()
    return rows if isinstance(rows, list) else []


def _fetch_nse_master(nse_symbol: str) -> dict | None:
    """Latest shareholding filing summary from NSE."""
    try:
        rows = _fetch_nse_master_list(nse_symbol)
        if not rows:
            return None

        def sort_key(row: dict) -> tuple:
            date = _parse_nse_date(row.get("date", "")) or ""
            return (date, row.get("submissionDate") or "")

        rows.sort(key=sort_key, reverse=True)
        latest = rows[0]
        xbrl = (latest.get("xbrl") or "").strip()
        if xbrl.endswith("/null") or xbrl == "null":
            xbrl = ""

        return {
            "promoter_holding_pct": _parse_pct(latest.get("pr_and_prgrp")),
            "public_holding_pct": _parse_pct(latest.get("public_val")),
            "holding_as_of": _parse_nse_date(latest.get("date", "")),
            "xbrl_url": xbrl or None,
        }
    except Exception:
        logger.exception("NSE shareholding master failed for %s", nse_symbol)
        return None


def _parse_xbrl_holdings(xbrl_url: str) -> dict[str, float | None]:
    """Extract category % from NSE shareholding XBRL (summary context)."""
    session = make_requests_session()
    response = session.get(xbrl_url, headers=NSE_HEADERS, timeout=45)
    response.raise_for_status()
    root = ET.fromstring(response.content)

    tag_to_field = {v: k for k, v in XBRL_CATEGORY_TAGS.items()}
    result: dict[str, float | None] = {k: None for k in XBRL_CATEGORY_TAGS}

    for elem in root.iter():
        tag = elem.tag.split("}")[-1]
        if tag != "ShareholdingAsAPercentageOfTotalNumberOfShares":
            continue
        ctx = elem.get("contextRef", "")
        if not ctx.endswith(SUMMARY_CONTEXT_SUFFIX):
            continue
        category = ctx.removesuffix(SUMMARY_CONTEXT_SUFFIX)
        field = tag_to_field.get(category)
        if not field or not elem.text:
            continue
        pct = _parse_pct(elem.text)
        if pct is not None:
            result[field] = pct

    return result


def _fetch_yfinance_holdings(yf_symbol: str) -> dict[str, float | None]:
    try:
        with without_proxy():
            info = yf.Ticker(yf_symbol).info
        inst = info.get("heldPercentInstitutions")
        insider = info.get("heldPercentInsiders")
        return {
            "institutional_holding_pct": round(inst * 100, 2) if inst is not None else None,
            "promoter_holding_pct": round(insider * 100, 2) if insider is not None else None,
        }
    except Exception:
        return {"institutional_holding_pct": None, "promoter_holding_pct": None}


def _cache_path(nse_symbol: str) -> Path:
    return CACHE_DIR / f"{nse_symbol}.json"


def _read_cache(nse_symbol: str) -> dict | None:
    path = _cache_path(nse_symbol)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
        if time.time() - payload.get("fetched_at", 0) > CACHE_TTL:
            return None
        return payload.get("data")
    except (json.JSONDecodeError, OSError):
        return None


def _write_cache(nse_symbol: str, data: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(nse_symbol).write_text(
        json.dumps({"fetched_at": time.time(), "data": data}, indent=0),
    )


def get_shareholding(symbol: str, *, fetch_xbrl: bool = True) -> dict:
    """
    Return holding percentages for a symbol — vendor-routed.
    Upstox fundamentals first when configured; NSE quarterly filing next;
    yfinance as the last fallback.
    Set fetch_xbrl=False for faster scans (promoter/public from NSE master only).
    """
    from app.services.vendors.registry import use_upstox

    nse_symbol = _nse_symbol(symbol)
    yf_symbol = symbol if symbol.endswith((".NS", ".BO")) else f"{symbol}.NS"

    now = time.time()
    mem = _memory.get(nse_symbol)
    if mem and now < mem[0]:
        return mem[1].copy()

    cached = _read_cache(nse_symbol)
    if cached:
        _memory[nse_symbol] = (now + 300, cached)
        return cached.copy()

    if use_upstox("shareholding"):
        try:
            history = _get_shareholding_history_upstox(symbol, max_periods=1)
        except Exception:
            logger.exception("Upstox shareholding failed for %s — falling back", symbol)
            history = None
        if history:
            latest = history[-1]
            fii = latest.get("fii_holding_pct") or 0
            dii = latest.get("dii_holding_pct") or 0
            data = {
                "promoter_holding_pct": latest.get("promoter_holding_pct"),
                "fii_holding_pct": latest.get("fii_holding_pct"),
                "dii_holding_pct": latest.get("dii_holding_pct"),
                "public_holding_pct": latest.get("public_holding_pct"),
                "mutual_fund_holding_pct": latest.get("mutual_fund_holding_pct"),
                "institutional_holding_pct": round(fii + dii, 2) if (fii or dii) else None,
                "holding_as_of": latest.get("as_of"),
                "holding_source": "upstox",
            }
            _write_cache(nse_symbol, data)
            _memory[nse_symbol] = (now + 300, data)
            return data.copy()

    data: dict[str, float | str | None] = {
        "promoter_holding_pct": None,
        "fii_holding_pct": None,
        "dii_holding_pct": None,
        "public_holding_pct": None,
        "mutual_fund_holding_pct": None,
        "institutional_holding_pct": None,
        "holding_as_of": None,
        "holding_source": None,
    }

    master = _fetch_nse_master(nse_symbol)
    if master:
        data["promoter_holding_pct"] = master.get("promoter_holding_pct")
        data["public_holding_pct"] = master.get("public_holding_pct")
        data["holding_as_of"] = master.get("holding_as_of")
        data["holding_source"] = "nse"

        xbrl_url = master.get("xbrl_url")
        if fetch_xbrl and xbrl_url:
            try:
                xbrl = _parse_xbrl_holdings(xbrl_url)
                for key, val in xbrl.items():
                    if val is not None:
                        data[key] = val
                data["holding_source"] = "nse_xbrl"
            except Exception:
                logger.warning("XBRL parse failed for %s", nse_symbol)

    yf = _fetch_yfinance_holdings(yf_symbol)
    if data["institutional_holding_pct"] is None:
        data["institutional_holding_pct"] = yf.get("institutional_holding_pct")
    if data["promoter_holding_pct"] is None:
        data["promoter_holding_pct"] = yf.get("promoter_holding_pct")
    if data["holding_source"] is None and (
        yf.get("institutional_holding_pct") is not None or yf.get("promoter_holding_pct") is not None
    ):
        data["holding_source"] = "yfinance"

    _write_cache(nse_symbol, data)
    _memory[nse_symbol] = (now + 300, data)
    return data.copy()


def _date_to_label(raw: str) -> str:
    """31-MAR-2026 -> Mar '26"""
    try:
        dt = datetime.strptime(raw.upper(), "%d-%b-%Y")
        return dt.strftime("%b '%y")
    except ValueError:
        return raw


def _compute_retail_and_others(entry: dict) -> float | None:
    """
    Residual public shareholding after FII and DII.

    NSE ``public_val`` / XBRL ``PublicShareholding`` is the full non-promoter block
    (promoter + public = 100). FII and DII are subsets of public — not additive
    with the public total.
    """
    public = entry.get("public_holding_pct")
    fii = entry.get("fii_holding_pct") or 0
    dii = entry.get("dii_holding_pct") or 0

    if public is not None:
        return round(max(0.0, float(public) - fii - dii), 2)

    promoter = entry.get("promoter_holding_pct")
    if promoter is not None:
        return round(max(0.0, 100.0 - float(promoter) - fii - dii), 2)

    return None


_UPSTOX_MONTHS = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06",
    "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}


def _upstox_period_to_as_of(period: str) -> str | None:
    """'Mar 2026' → '31-Mar-2026' (matches the NSE as_of format used app-wide)."""
    parts = (period or "").strip().split()
    if len(parts) != 2:
        return None
    mon, year = parts[0][:3].lower(), parts[1]
    if mon not in _UPSTOX_MONTHS or not year.isdigit():
        return None
    day = {"03": "31", "06": "30", "09": "30", "12": "31"}.get(_UPSTOX_MONTHS[mon], "28")
    return f"{day}-{parts[0][:3].title()}-{year}"


def _get_shareholding_history_upstox(symbol: str, max_periods: int) -> list[dict] | None:
    """Quarterly shareholding from the Upstox fundamentals API.

    Upstox splits domestic institutions into other_dii + mutual_funds; the
    app's dii bucket (NSE InstitutionsDomestic) includes mutual funds, so the
    two are summed for consistency with historical NSE-sourced rows.
    """
    from app.services.vendors import upstox

    isin = upstox.resolve_isin(symbol)
    if not isin:
        return None

    categories = upstox.fetch_share_holdings(isin)
    by_period: dict[str, dict[str, float]] = {}
    for cat in categories:
        name = cat.get("category")
        for item in cat.get("history") or []:
            period = str(item.get("period") or "")
            value = item.get("value")
            if not period or value is None:
                continue
            by_period.setdefault(period, {})[name] = float(value)

    if not by_period:
        return None

    def period_sort_key(p: str) -> str:
        as_of = _upstox_period_to_as_of(p)
        if not as_of:
            return ""
        day, mon, year = as_of.split("-")
        return f"{year}-{_UPSTOX_MONTHS[mon.lower()]}-{day}"

    periods: list[dict] = []
    for period in sorted(by_period, key=period_sort_key)[-max_periods:]:
        vals = by_period[period]
        as_of = _upstox_period_to_as_of(period)
        if not as_of:
            continue
        promoter = vals.get("promoters")
        fii = vals.get("fii")
        other_dii = vals.get("other_dii")
        mf = vals.get("mutual_funds")
        dii = None
        if other_dii is not None or mf is not None:
            dii = round((other_dii or 0) + (mf or 0), 2)
        entry = {
            "as_of": as_of,
            "label": _date_to_label(as_of),
            "promoter_holding_pct": promoter,
            "public_holding_pct": round(100 - promoter, 2) if promoter is not None else None,
            "fii_holding_pct": fii,
            "dii_holding_pct": dii,
            "mutual_fund_holding_pct": mf,
        }
        retail = vals.get("retail_and_other")
        entry["retail_and_others_pct"] = (
            round(retail, 2) if retail is not None else _compute_retail_and_others(entry)
        )
        periods.append(entry)

    return periods or None


def get_shareholding_history(symbol: str, max_periods: int = 5) -> list[dict]:
    """Historical quarterly shareholding — vendor-routed (Upstox first, NSE fallback)."""
    from app.services.vendors.registry import use_upstox

    if use_upstox("shareholding"):
        try:
            periods = _get_shareholding_history_upstox(symbol, max_periods)
            if periods:
                return periods
        except Exception:
            logger.exception(
                "Upstox shareholding failed for %s — falling back to NSE", symbol
            )

    nse_symbol = _nse_symbol(symbol)
    try:
        rows = _fetch_nse_master_list(nse_symbol)
    except Exception:
        logger.exception("NSE master list failed for %s", nse_symbol)
        return []

    def sort_key(row: dict) -> tuple:
        date = _parse_nse_date(row.get("date", "")) or ""
        return (date, row.get("submissionDate") or "")

    rows.sort(key=sort_key, reverse=True)

    seen_dates: set[str] = set()
    periods: list[dict] = []

    for row in rows:
        if len(periods) >= max_periods:
            break
        as_of = _parse_nse_date(row.get("date", ""))
        if not as_of or as_of in seen_dates:
            continue
        xbrl = (row.get("xbrl") or "").strip()
        if not xbrl or xbrl.endswith("/null") or xbrl.endswith("null"):
            continue

        seen_dates.add(as_of)
        entry: dict = {
            "as_of": as_of,
            "label": _date_to_label(as_of),
            "promoter_holding_pct": _parse_pct(row.get("pr_and_prgrp")),
            "public_holding_pct": _parse_pct(row.get("public_val")),
            "fii_holding_pct": None,
            "dii_holding_pct": None,
            "mutual_fund_holding_pct": None,
        }

        try:
            xbrl_data = _parse_xbrl_holdings(xbrl)
            for key, val in xbrl_data.items():
                if val is not None:
                    entry[key] = val
        except Exception:
            logger.warning("XBRL history parse failed for %s %s", nse_symbol, as_of)

        entry["retail_and_others_pct"] = _compute_retail_and_others(entry)

        periods.append(entry)

    periods.reverse()
    return [_normalize_shareholding_period(p) for p in periods]


def _normalize_shareholding_period(entry: dict) -> dict:
    """Recompute retail/others so cached rows stay consistent after formula fixes."""
    normalized = dict(entry)
    normalized["retail_and_others_pct"] = _compute_retail_and_others(normalized)
    return normalized


def normalize_scan_match(match: dict) -> dict:
    """Fix shareholding buckets on cached screener matches (weekly/golden)."""
    m = dict(match)
    sh = m.get("shareholding")
    if not isinstance(sh, list) or not sh:
        return m
    normalized = [_normalize_shareholding_period(p) for p in sh]
    m["shareholding"] = normalized
    latest = normalized[-1]
    m["promoter_holding_pct"] = latest.get("promoter_holding_pct")
    m["fii_holding_pct"] = latest.get("fii_holding_pct")
    m["dii_holding_pct"] = latest.get("dii_holding_pct")
    m["retail_holding_pct"] = latest.get("retail_and_others_pct")
    m["mutual_fund_holding_pct"] = latest.get("mutual_fund_holding_pct")
    return m


def normalize_scan_cache_payload(cached: dict) -> dict:
    """Apply shareholding fixes to all matches in a scan-results response."""
    out = dict(cached)
    matches = out.get("matches")
    if isinstance(matches, list):
        out["matches"] = [normalize_scan_match(m) for m in matches]
    return out

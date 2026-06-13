"""IPO market intel scraper — GMP + live subscription via headless Chromium.

Sources (top-ranked Indian IPO trackers):
- InvestorGain live GMP report: grey-market premium, est. listing gain, price
  band, dates, fire rating.
- Chittorgarh live subscription report: QIB / NII / Retail / Total multiples
  and application counts.

Both pages render their tables with JavaScript, so a real headless browser is
required. Scrapes are low-volume (one page each, manual or once-a-day
schedule), parsed header-by-name so column reordering doesn't break them, and
merged into the ipo_intel table by normalized company name.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from datetime import date, datetime, timezone
from difflib import SequenceMatcher
from typing import Any

logger = logging.getLogger(__name__)

GMP_URL = "https://www.investorgain.com/report/live-ipo-gmp/331/"
SUBSCRIPTION_URL = (
    "https://www.chittorgarh.com/report/ipo-subscription-status-live-bidding-data-bse-nse/21/"
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

PAGE_TIMEOUT_MS = 45_000
RENDER_WAIT_MS = 3_000

# Badge / suffix tokens the source sites append to company names — exchange,
# board, and status markers (U=upcoming, O=open, C=closed, L=listed) plus the
# combined forms like "OSM" (open + SME).
_NAME_NOISE = {
    "ipo", "ltd", "ltd.", "limited", "bse", "nse", "sme", "sm", "cm",
    "u", "o", "c", "l", "p",
    "usm", "osm", "csm", "lsm",
    "&", "and",
}

_job_lock = threading.Lock()
_job: dict[str, Any] = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "error": None,
    "summary": None,
}


# ── Fetch ─────────────────────────────────────────────────────────────────────

def launch_headless_browser(playwright: Any, **extra: Any) -> Any:
    """Launch headless Chromium, preferring installed Chrome/Edge over the Playwright bundle."""
    launch_kwargs: dict[str, Any] = {"headless": True, **extra}

    channel_override = os.getenv("SCRAPER_BROWSER_CHANNEL", "").strip()
    channels: list[str | None] = (
        [channel_override] if channel_override else ["chrome", "msedge", None]
    )

    last_err: Exception | None = None
    for channel in channels:
        kwargs = dict(launch_kwargs)
        label = channel or "playwright-chromium"
        if channel:
            kwargs["channel"] = channel
        try:
            browser = playwright.chromium.launch(**kwargs)
            logger.info("IPO scraper using browser: %s", label)
            return browser
        except Exception as exc:
            last_err = exc
            logger.debug("Browser launch failed for %s: %s", label, exc)

    assert last_err is not None
    raise last_err


def _fetch_rendered_html(urls: list[str]) -> dict[str, str]:
    """Load each URL in one headless Chromium session; return url → html."""
    from playwright.sync_api import sync_playwright

    launch_kwargs: dict[str, Any] = {}
    proxy = os.getenv("SCRAPER_PROXY")
    if proxy:
        launch_kwargs["proxy"] = {"server": proxy}

    out: dict[str, str] = {}
    with sync_playwright() as p:
        browser = launch_headless_browser(p, **launch_kwargs)
        try:
            page = browser.new_page(user_agent=USER_AGENT)
            for url in urls:
                page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
                # Wait for the JS-rendered data table; fall back to a fixed pause
                # so a missing table still yields HTML for the parser to inspect.
                try:
                    page.wait_for_selector("table tbody tr td", timeout=15_000)
                except Exception:
                    logger.warning("No data table rendered for %s", url)
                page.wait_for_timeout(RENDER_WAIT_MS)
                out[url] = page.content()
        finally:
            browser.close()
    return out


# ── Parsing helpers ───────────────────────────────────────────────────────────

def _num(text: str | None) -> float | None:
    if not text:
        return None
    cleaned = re.sub(r"[₹,x×\s]", "", str(text))
    m = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    return float(m.group()) if m else None


def _strip_markers(raw: str) -> str:
    """Cut InvestorGain status suffixes like 'L@70.00 (1.43%)' off the name."""
    return re.split(r"\s+[A-Z]@", raw.strip())[0].strip()


def name_key(raw: str) -> str:
    """Normalized join key: lowercase, badges and punctuation stripped."""
    tokens = re.sub(r"[^\w\s]", " ", _strip_markers(raw).lower()).split()
    kept = [t for t in tokens if t not in _NAME_NOISE and not t.isdigit()]
    return " ".join(kept)


def _clean_display_name(raw: str) -> str:
    """Drop trailing badge tokens (exchange / board / status markers)."""
    words = _strip_markers(raw).split()
    while words and words[-1].lower() in _NAME_NOISE:
        words.pop()
    return " ".join(words) or raw.strip()


def _parse_day_month(text: str | None) -> str | None:
    """'12-Jun' / '09-Jun-2026' → ISO date; year inferred near today when absent."""
    if not text:
        return None
    text = text.strip()
    m = re.match(r"(\d{1,2})-([A-Za-z]{3})(?:-(\d{4}))?", text)
    if not m:
        return None
    day, mon_txt, year_txt = int(m.group(1)), m.group(2).lower(), m.group(3)
    months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    if mon_txt not in months:
        return None
    month = months.index(mon_txt) + 1
    today = date.today()
    year = int(year_txt) if year_txt else today.year
    try:
        d = date(year, month, day)
    except ValueError:
        return None
    if not year_txt:
        # Year-less dates are always near today; fix Dec/Jan wraparound.
        if (d - today).days > 180:
            d = date(year - 1, month, day)
        elif (today - d).days > 180:
            d = date(year + 1, month, day)
    return d.isoformat()


def _table_records(html: str) -> list[dict[str, str]]:
    """First data table on the page → list of header-keyed row dicts."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if table is None:
        return []
    headers = [
        re.sub(r"[▲▼]", "", th.get_text(" ", strip=True)).strip()
        for th in table.find_all("th")
    ]
    body = table.find("tbody") or table
    records: list[dict[str, str]] = []
    for tr in body.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if not cells or all(not c for c in cells):
            continue
        records.append({headers[i]: cells[i] for i in range(min(len(headers), len(cells)))})
    return records


def _col(record: dict[str, str], *needles: str) -> str | None:
    """First cell whose header contains all the given needles (case-insensitive)."""
    for header, value in record.items():
        h = header.lower()
        if all(n.lower() in h for n in needles):
            return value
    return None


# ── Source parsers ────────────────────────────────────────────────────────────

def parse_gmp_rows(html: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rec in _table_records(html):
        raw_name = _col(rec, "name") or ""
        if not raw_name:
            continue
        gmp_cell = _col(rec, "gmp") or ""
        gmp_match = re.search(r"₹\s*(-?\d+(?:\.\d+)?)", gmp_cell)
        pct_match = re.search(r"\((-?\d+(?:\.\d+)?)%\)", gmp_cell)
        rating_cell = _col(rec, "rating") or ""
        is_sme = bool(re.search(r"\b(SME|SM)\b", raw_name))
        rows.append(
            {
                "name_key": name_key(raw_name),
                "display_name": _clean_display_name(raw_name),
                "ipo_type": "sme" if is_sme else "mainboard",
                "gmp": float(gmp_match.group(1)) if gmp_match else None,
                "gmp_pct": float(pct_match.group(1)) if pct_match else None,
                "rating": rating_cell.count("🔥") or None,
                "price_band": _col(rec, "price") or None,
                "ipo_size": _col(rec, "size") or None,
                "lot_size": _col(rec, "lot") or None,
                "open_date": _parse_day_month(_col(rec, "open")),
                "close_date": _parse_day_month(_col(rec, "close")),
                "listing_date": _parse_day_month(_col(rec, "listing")),
                "gmp_updated_at": _col(rec, "updated") or None,
            }
        )
    return rows


def parse_subscription_rows(html: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rec in _table_records(html):
        raw_name = _col(rec, "company") or ""
        if not raw_name:
            continue
        rows.append(
            {
                "name_key": name_key(raw_name),
                "display_name": _clean_display_name(raw_name),
                "close_date": _parse_day_month(_col(rec, "closing")),
                "sub_qib": _num(_col(rec, "qib")),
                "sub_nii": _num(_col(rec, "nii (x)")),
                "sub_retail": _num(_col(rec, "retail")),
                "sub_total": _num(_col(rec, "total (x)")),
                "sub_applications": _col(rec, "applications") or None,
                "sub_as_of": _col(rec, "subscription as on") or None,
            }
        )
    return rows


# ── Merge + status ────────────────────────────────────────────────────────────

def _derive_status(open_iso: str | None, close_iso: str | None, listing_iso: str | None) -> str | None:
    today = date.today().isoformat()
    if listing_iso and today >= listing_iso:
        return "listed"
    if open_iso and today < open_iso:
        return "upcoming"
    if open_iso and close_iso and open_iso <= today <= close_iso:
        return "open"
    if close_iso and today > close_iso:
        return "closed"
    return None


def _match_key(key: str, candidates: dict[str, dict[str, Any]]) -> str | None:
    """Exact key match, else containment match (sites abbreviate names differently)."""
    if key in candidates:
        return key
    for other in candidates:
        if key and other and (key.startswith(other) or other.startswith(key)):
            return other
    return None


def fuzzy_name_score(a: str, b: str) -> float:
    """0–1 similarity between two normalized name keys.

    Combines sequence similarity with token-overlap so 'utkal speciality'
    matches 'utkal speciality industries india' (sites abbreviate freely).
    """
    if not a or not b:
        return 0.0
    if a == b or a.startswith(b) or b.startswith(a):
        return 1.0
    seq = SequenceMatcher(None, a, b).ratio()
    ta, tb = set(a.split()), set(b.split())
    overlap = len(ta & tb) / max(1, min(len(ta), len(tb)))
    return max(seq, overlap)


def merge_intel(
    gmp_rows: list[dict[str, Any]],
    sub_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for row in gmp_rows:
        if row["name_key"]:
            row["sources"] = "investorgain"
            by_key[row["name_key"]] = row

    for sub in sub_rows:
        key = _match_key(sub["name_key"], by_key)
        if key is not None:
            target = by_key[key]
            for field, value in sub.items():
                if field in ("name_key", "display_name"):
                    continue
                if value is not None:
                    target[field] = value
            target["sources"] = "investorgain+chittorgarh"
        else:
            sub["sources"] = "chittorgarh"
            by_key[sub["name_key"]] = sub

    merged = list(by_key.values())
    for row in merged:
        row["status"] = _derive_status(
            row.get("open_date"), row.get("close_date"), row.get("listing_date")
        )
    return merged


# ── Upstox verification ───────────────────────────────────────────────────────

FUZZY_MATCH_THRESHOLD = 0.7


def _upstox_to_row(ipo: dict[str, Any]) -> dict[str, Any]:
    """Upstox IPO record → ipo_intel row fields (authoritative values)."""
    lo, hi = ipo.get("minimum_price"), ipo.get("maximum_price")
    band = None
    if lo is not None and hi is not None:
        band = f"{lo:g}" if lo == hi else f"{lo:g}–{hi:g}"
    sub_total = None
    try:
        raw_sub = ipo.get("total_subscription")
        if raw_sub is not None and float(raw_sub) > 0:
            sub_total = float(raw_sub)
    except (TypeError, ValueError):
        pass
    issue_size = ipo.get("issue_size")
    return {
        "display_name": re.sub(r"\s+IPO$", "", str(ipo.get("name") or "").strip()),
        "ipo_type": "sme" if ipo.get("issue_type") == "sme" else "mainboard",
        "status": ipo.get("status") or None,
        "price_band": band,
        "ipo_size": f"₹{issue_size:g} Cr" if issue_size else None,
        "open_date": ipo.get("bidding_start_date") or None,
        "close_date": ipo.get("bidding_end_date") or None,
        "sub_total": sub_total,
        "upstox_verified": True,
        "upstox_symbol": ipo.get("symbol") or None,
        "isin": ipo.get("isin") or None,
        "industry": ipo.get("industry") or None,
        "upstox_id": ipo.get("id") or None,
        "sources": "upstox",
    }


def _is_current_ipo(row: dict[str, Any], *, max_listed_age_days: int = 30) -> bool:
    """Open/upcoming/closed IPOs are always current; listed ones only briefly.

    The Upstox 'listed' catalog spans years — without this filter every
    historical IPO would flood the table.
    """
    if row.get("status") in ("open", "upcoming", "closed"):
        return True
    ref = row.get("close_date") or row.get("open_date")
    if not ref:
        return False
    try:
        d = date.fromisoformat(str(ref))
    except ValueError:
        return False
    return (date.today() - d).days <= max_listed_age_days


def verify_with_upstox(merged: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Fuzzy-join scraped rows onto the authoritative Upstox IPO catalog.

    Matched rows take Upstox's name, status, band, and dates (the scrape keeps
    GMP and live subscription detail). Upstox IPOs the scrape missed are added
    as their own verified rows. Returns (rows, verified_count); a missing token
    or API failure leaves the scraped rows untouched.
    """
    from app.services.vendors import upstox
    from app.services.vendors.registry import use_upstox

    if not use_upstox("ipo_catalog"):
        return merged, 0

    try:
        catalog = upstox.fetch_ipos()
    except Exception:
        logger.exception("Upstox IPO catalog fetch failed — rows stay scrape-only")
        return merged, 0

    u_rows = [(_upstox_to_row(ipo), name_key(str(ipo.get("name") or ""))) for ipo in catalog]
    u_rows = [(row, key) for row, key in u_rows if key]

    matched_upstox: set[str] = set()
    verified = 0

    for row in merged:
        best_key, best_row, best_score = None, None, 0.0
        for u_row, u_key in u_rows:
            score = fuzzy_name_score(row["name_key"], u_key)
            if score > best_score:
                best_key, best_row, best_score = u_key, u_row, score
        if best_row is None or best_score < FUZZY_MATCH_THRESHOLD:
            continue
        matched_upstox.add(best_key)
        verified += 1
        scrape_sources = row.get("sources")
        # Authoritative fields win; scrape-only fields (GMP, QIB/NII/retail) stay.
        for field, value in best_row.items():
            if value is not None:
                if field == "sub_total" and row.get("sub_total") is not None:
                    continue  # live scrape detail is fresher intraday
                row[field] = value
        row["name_key"] = best_key
        row["sources"] = f"{scrape_sources}+upstox" if scrape_sources else "upstox"

    for u_row, u_key in u_rows:
        if u_key in matched_upstox or not _is_current_ipo(u_row):
            continue
        u_row["name_key"] = u_key
        merged.append(u_row)

    return merged, verified


def enrich_with_nse_master(merged: list[dict[str, Any]]) -> int:
    """Fill symbol / ISIN / listing date from the official NSE equity masters.

    Catches what the Upstox catalog misses — typically freshly listed SME
    names — by fuzzy-matching company names against EQUITY_L / SME_EQUITY_L.
    Returns the number of rows enriched.
    """
    from app.services.nse_symbol_master import resolve_by_name

    enriched = 0
    for row in merged:
        if row.get("isin") and row.get("upstox_symbol") and row.get("listing_date"):
            continue
        try:
            hit = resolve_by_name(row["name_key"])
        except Exception:
            logger.exception("NSE master lookup failed for %s", row.get("display_name"))
            return enriched
        if hit is None:
            continue
        if not row.get("isin"):
            row["isin"] = hit["isin"]
        if not row.get("upstox_symbol"):
            row["upstox_symbol"] = hit["symbol"]
        if not row.get("listing_date"):
            row["listing_date"] = hit.get("listing_date")
        if not row.get("ipo_type") and hit.get("board") == "sme":
            row["ipo_type"] = "sme"
        sources = row.get("sources") or ""
        if "nse" not in sources:
            row["sources"] = f"{sources}+nse" if sources else "nse"
        enriched += 1
    return enriched


# ── Persistence + job control ─────────────────────────────────────────────────

def run_ipo_intel_scrape() -> dict[str, Any]:
    """Scrape both sources, merge, verify against Upstox, upsert into ipo_intel."""
    from app.db import crud
    from app.db.database import SessionLocal

    pages = _fetch_rendered_html([GMP_URL, SUBSCRIPTION_URL])
    gmp_rows = parse_gmp_rows(pages.get(GMP_URL, ""))
    sub_rows = parse_subscription_rows(pages.get(SUBSCRIPTION_URL, ""))
    merged = merge_intel(gmp_rows, sub_rows)
    merged, verified_count = verify_with_upstox(merged)
    nse_enriched = enrich_with_nse_master(merged)

    # De-duplicate after re-keying (two scraped rows can map to one Upstox IPO)
    by_key: dict[str, dict[str, Any]] = {}
    for row in merged:
        existing = by_key.get(row["name_key"])
        if existing is None:
            by_key[row["name_key"]] = row
        else:
            for field, value in row.items():
                if value is not None and existing.get(field) is None:
                    existing[field] = value
    merged = list(by_key.values())

    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        for row in merged:
            crud.upsert_ipo_intel(db, fetched_at=now, **row)
        # Table mirrors the latest scrape — but only prune when BOTH sources
        # returned data, so one source failing transiently can't wipe the
        # other's rows. Stale rows linger until the next fully healthy run.
        both_ok = bool(gmp_rows) and bool(sub_rows)
        pruned = crud.prune_ipo_intel(db, older_than=now) if both_ok else 0
        if not both_ok:
            logger.warning(
                "IPO intel scrape partial (gmp=%d, subs=%d) — prune skipped",
                len(gmp_rows),
                len(sub_rows),
            )

    summary = {
        "gmp_rows": len(gmp_rows),
        "subscription_rows": len(sub_rows),
        "merged_rows": len(merged),
        "verified_rows": verified_count,
        "nse_enriched_rows": nse_enriched,
        "pruned_rows": pruned,
        "fetched_at": now.isoformat(),
    }
    logger.info("IPO intel scrape complete: %s", summary)
    return summary


def _run_job() -> None:
    global _job
    try:
        summary = run_ipo_intel_scrape()
        with _job_lock:
            _job.update(
                running=False,
                finished_at=datetime.now(timezone.utc).isoformat(),
                error=None,
                summary=summary,
            )
    except Exception as exc:
        logger.exception("IPO intel scrape failed")
        with _job_lock:
            _job.update(
                running=False,
                finished_at=datetime.now(timezone.utc).isoformat(),
                error=str(exc),
                summary=None,
            )


def start_ipo_intel_scrape() -> dict[str, Any]:
    with _job_lock:
        if _job["running"]:
            return {"status": "already_running", **_job}
        _job.update(
            running=True,
            started_at=datetime.now(timezone.utc).isoformat(),
            finished_at=None,
            error=None,
        )
    thread = threading.Thread(target=_run_job, name="ipo-intel-scrape", daemon=True)
    thread.start()
    return {"status": "started", **_job}


def get_ipo_intel_status() -> dict[str, Any]:
    with _job_lock:
        return dict(_job)

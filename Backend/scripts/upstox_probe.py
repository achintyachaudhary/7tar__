"""Probe the Upstox Analytics API with the configured token.

Run from Backend:  python scripts/upstox_probe.py
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

load_dotenv(BACKEND_DIR / ".env")


def main() -> int:
    from app.services.vendors import upstox

    if not upstox.is_configured():
        print("FAIL: UPSTOX_ANALYTICS_TOKEN not set")
        return 1

    inst = upstox.resolve_instrument("RELIANCE.NS")
    print(f"instrument master: RELIANCE -> {inst}")
    assert inst and inst["isin"].startswith("INE")

    ipos = upstox.fetch_ipos(("open", "upcoming"))
    print(f"ipos (open+upcoming): {len(ipos)}")
    for ipo in ipos[:5]:
        print(
            f"  {ipo.get('name')!r:<42} sym={ipo.get('symbol')} status={ipo.get('status')} "
            f"band={ipo.get('minimum_price')}-{ipo.get('maximum_price')} "
            f"subs={ipo.get('total_subscription')}"
        )

    news = upstox.fetch_news([inst["instrument_key"]], page_size=5)
    articles = news.get(inst["instrument_key"], [])
    print(f"news for RELIANCE: {len(articles)} articles")
    for a in articles[:3]:
        print(f"  - {a.get('heading', '')[:80]}")

    income = upstox.fetch_income_statement(inst["isin"], time_period="quarterly")
    cats = {row.get("category"): len(row.get("history") or []) for row in income}
    print(f"income statement categories: {cats}")

    holdings = upstox.fetch_share_holdings(inst["isin"])
    hcats = {row.get("category"): (row.get("history") or [{}])[-1] for row in holdings}
    print(f"shareholding latest: {hcats}")

    print("UPSTOX PROBE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

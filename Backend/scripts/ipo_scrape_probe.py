"""Probe the IPO data sources with headless Chromium — prints table headers found.

Run from Backend:  python scripts/ipo_scrape_probe.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from app.services.ipo_intel import launch_headless_browser

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

URLS = {
    "investorgain_gmp": "https://www.investorgain.com/report/live-ipo-gmp/331/",
    "chittorgarh_subscription": "https://www.chittorgarh.com/report/ipo-subscription-status-live-bidding-data-bse-nse/21/",
}


def main() -> int:
    with sync_playwright() as p:
        browser = launch_headless_browser(p)
        page = browser.new_page(user_agent=UA)
        for name, url in URLS.items():
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(3000)
                html = page.content()
                soup = BeautifulSoup(html, "lxml")
                tables = soup.find_all("table")
                print(f"\n=== {name} — {len(tables)} tables, page len {len(html)} ===")
                for i, t in enumerate(tables[:4]):
                    headers = [th.get_text(strip=True) for th in t.find_all("th")][:14]
                    body = t.find("tbody") or t
                    rows = body.find_all("tr")
                    print(f"  table[{i}] body-rows={len(rows)} headers={headers}")
                    for r in rows[:3]:
                        cells = [td.get_text(" ", strip=True)[:30] for td in r.find_all("td")]
                        if cells:
                            print(f"    row: {cells}")
            except Exception as exc:
                print(f"\n=== {name} FAILED: {exc}")
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

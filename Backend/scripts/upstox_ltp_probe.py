"""Probe the Upstox LTP market-quote endpoint shape.

Run from Backend:  python scripts/upstox_ltp_probe.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

load_dotenv(BACKEND_DIR / ".env")

import requests

from app.services.vendors.upstox import _headers
from app.utils.network import without_proxy

KEYS = "NSE_INDEX|Nifty 50,NSE_INDEX|Nifty Bank,NSE_EQ|INE002A01018,NSE_EQ|INE040H01021"


def main() -> int:
    with without_proxy():
        resp = requests.get(
            "https://api.upstox.com/v2/market-quote/ltp",
            params={"instrument_key": KEYS},
            headers=_headers(),
            timeout=20,
        )
    print("status:", resp.status_code)
    body = resp.json()
    print(json.dumps(body, indent=2)[:1500])
    return 0 if resp.status_code == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Run each screener against a handful of symbols from the local DB.

Verifies the new filter params execute end-to-end on real data (no scan context,
so each call falls back to single-symbol DB reads).

Run from the Backend directory:  python scripts/screener_sanity.py
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

# Reject reasons contain symbols like ≤ that the default Windows console codepage rejects
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    from app.db import crud
    from app.db.database import SessionLocal
    from app.services.brst_screener import scan_brst_symbol
    from app.services.darvas_screener import scan_darvas_symbol
    from app.services.golden_screener import scan_golden_symbol
    from app.services.mean_reversion_screener import scan_mean_reversion_symbol
    from app.services.multi_year_screener import scan_multi_year_symbol
    from app.services.scan_filters import is_reject_result, reject_reason
    from app.services.vol_squeeze_screener import scan_vol_squeeze_symbol
    from app.services.volume_surge_screener import scan_volume_surge_symbol
    from app.services.weekly_screener import scan_weekly_symbol

    with SessionLocal() as db:
        symbols = crud.list_stock_universe_with_filters(
            db, active_only=True, min_market_cap_cr=10000, max_market_cap_cr=None
        )[:8]

    if not symbols:
        print("No symbols in stock universe — run Day Scan first. Skipping live test.")
        return 0

    scanners = {
        "brst": scan_brst_symbol,
        "multi_year": scan_multi_year_symbol,
        "darvas": scan_darvas_symbol,
        "golden": scan_golden_symbol,
        "weekly": scan_weekly_symbol,
        "mean_reversion": scan_mean_reversion_symbol,
        "vol_squeeze": scan_vol_squeeze_symbol,
        "volume_surge": scan_volume_surge_symbol,
    }

    for name, fn in scanners.items():
        outcomes: list[str] = []
        for sym in symbols:
            res = fn(sym)
            if res is None:
                outcomes.append(f"{sym}: ERROR(None)")
            elif is_reject_result(res):
                outcomes.append(f"{sym}: reject — {reject_reason(res)}")
            else:
                outcomes.append(f"{sym}: MATCH")
        print(f"--- {name} ---")
        for line in outcomes:
            print("  " + line)

    print("SANITY RUN COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

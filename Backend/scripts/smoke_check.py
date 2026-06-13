"""Smoke check: compile the app package, import every service, sanity-check scan defs.

Run from the Backend directory:  python scripts/smoke_check.py
"""

from __future__ import annotations

import compileall
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


def main() -> int:
    ok = compileall.compile_dir(str(BACKEND_DIR / "app"), quiet=2, force=True)
    if not ok:
        print("FAIL: compileall reported syntax errors")
        return 1
    print("compile: ok")

    from app.services import (  # noqa: F401
        brst_screener,
        darvas_screener,
        golden_screener,
        job_manager,
        live_trading,
        market_indices,
        mean_reversion_screener,
        multi_year_screener,
        scan_config,
        scan_definitions,
        scan_filters,
        screener,
        vol_squeeze_screener,
        weekly_screener,
    )
    from app.api import news_routes  # noqa: F401
    from app.services.vendors import registry, upstox  # noqa: F401

    print("imports: ok")

    # Vendor registry consistency
    from app.services.vendors.registry import CAPABILITIES, VENDOR_INFO, active_vendor

    for cap_id, cap in CAPABILITIES.items():
        assert cap["default"] in cap["options"], f"{cap_id}: default not in options"
        for option in cap["options"]:
            assert option in VENDOR_INFO, f"{cap_id}: unknown vendor {option}"
        assert active_vendor(cap_id) in cap["options"]
    print(f"vendor registry: ok ({len(CAPABILITIES)} capabilities)")

    from app.services.scan_definitions import SCAN_DEFINITIONS, default_params

    for scan_type, defn in SCAN_DEFINITIONS.items():
        params = default_params(scan_type)
        schema_ids = {f["id"] for f in defn["param_schema"]}
        assert params.keys() == schema_ids, f"{scan_type}: defaults/schema mismatch"
        assert "min_price" in params, f"{scan_type}: missing min_price"
        assert "min_avg_turnover_cr" in params, f"{scan_type}: missing min_avg_turnover_cr"
        print(f"scan defs: {scan_type} ok ({len(params)} params)")

    # Every registered scan type must have a definition and vice versa
    from app.services.job_manager import SCAN_REGISTRY

    assert set(SCAN_REGISTRY.keys()) == set(SCAN_DEFINITIONS.keys()), (
        "SCAN_REGISTRY and SCAN_DEFINITIONS out of sync: "
        f"{set(SCAN_REGISTRY) ^ set(SCAN_DEFINITIONS)}"
    )
    print("registry/definitions sync: ok")

    # NSE market-hours clock
    from datetime import datetime, timezone as _tz

    from app.utils.market_hours import (
        is_nse_data_live,
        is_nse_market_open,
        last_nse_close,
        nse_session_phase,
    )

    tue_noon = datetime(2026, 6, 9, 6, 30, tzinfo=_tz.utc)  # 12:00 IST Tuesday
    tue_night = datetime(2026, 6, 9, 16, 30, tzinfo=_tz.utc)  # 22:00 IST Tuesday
    tue_preopen = datetime(2026, 6, 9, 3, 41, tzinfo=_tz.utc)  # 09:11 IST Tuesday
    sunday = datetime(2026, 6, 7, 6, 30, tzinfo=_tz.utc)
    assert is_nse_market_open(tue_noon) and not is_nse_market_open(tue_night)
    assert not is_nse_market_open(sunday)
    # Pre-open (9:00–9:15 IST): data is live but continuous trading hasn't started.
    assert nse_session_phase(tue_preopen) == "pre_open"
    assert is_nse_data_live(tue_preopen) and not is_nse_market_open(tue_preopen)
    assert nse_session_phase(tue_noon) == "open" and nse_session_phase(sunday) == "closed"
    close = last_nse_close(tue_night)
    assert close.astimezone(_tz.utc).hour == 10  # 15:30 IST == 10:00 UTC
    assert last_nse_close(sunday).weekday() == 4  # Friday close
    print("market hours clock: ok")

    # NSE symbol masters (official EQUITY_L + SME_EQUITY_L)
    from app.services.nse_symbol_master import all_rows, resolve_by_name, resolve_symbol

    rows = all_rows()
    assert len(rows) > 2000, f"NSE masters too small: {len(rows)}"
    rel = resolve_symbol("RELIANCE.NS")
    assert rel and rel["isin"] == "INE002A01018", f"RELIANCE resolution broken: {rel}"
    bml = resolve_by_name("bio medica laboratories")
    assert bml and bml["symbol"] == "BMLL", f"SME name resolution broken: {bml}"
    print(f"nse symbol masters: ok ({len(rows)} equities, fuzzy + symbol lookups)")

    # Reject sentinel round-trip
    from app.services.scan_filters import is_reject_result, reject, reject_reason

    sentinel = reject("test reason")
    assert is_reject_result(sentinel) and reject_reason(sentinel) == "test reason"
    assert not is_reject_result({"symbol": "X"})
    print("reject sentinel: ok")

    # Liquidity filter on a synthetic frame
    import pandas as pd

    from app.services.scan_filters import distance_from_52w_high_pct, liquidity_reject

    df = pd.DataFrame(
        {
            "close": [100.0] * 30,
            "high": [110.0] * 30,
            "volume": [1_000_000] * 30,
        },
        index=pd.date_range("2025-01-01", periods=30, freq="B"),
    )
    assert liquidity_reject(df, min_price=20, min_avg_turnover_cr=1) is None
    assert liquidity_reject(df, min_price=500, min_avg_turnover_cr=1) is not None
    assert liquidity_reject(df, min_price=20, min_avg_turnover_cr=50) is not None
    dist = distance_from_52w_high_pct(df)
    assert dist is not None and abs(dist - (10 / 110 * 100)) < 0.01
    print("liquidity/52w helpers: ok")

    print("ALL SMOKE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

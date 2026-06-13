#!/usr/bin/env python3
"""Send sample trigger + eod_summary messages to StockRelay for connectivity testing."""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services import stockrelay


def main() -> int:
    trigger_ok = stockrelay.push_trigger(
        msg_id="trigger_test_RELIANCE_manual",
        symbol="RELIANCE.NS",
        company_name="Reliance Industries",
        current_price=2845.50,
        direction="above",
        threshold=2800.0,
        label="RELIANCE moved above ₹2800 (test)",
    )

    eod_ok = stockrelay.push_message(
        {
            "type": "eod_summary",
            "date": "2026-06-09",
            "portfolio": {
                "invested": 8_000_000,
                "current_value": 8_120_000,
                "today_pnl": 4820,
                "today_pnl_percent": 0.06,
            },
            "stocks": [
                {
                    "symbol": "RELIANCE",
                    "name": "Reliance Industries",
                    "invested": 200_000,
                    "current_value": 208_500,
                    "today_pnl": 2100,
                    "today_pnl_percent": 1.02,
                    "status": "profit",
                }
            ],
        }
    )

    print(f"trigger: {'ok' if trigger_ok else 'failed'}")
    print(f"eod_summary: {'ok' if eod_ok else 'failed'}")
    return 0 if trigger_ok and eod_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

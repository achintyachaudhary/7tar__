"""Quick check of the NSE session-phase clock (run from Backend/)."""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.market_hours import (
    current_session_date,
    is_nse_data_live,
    is_nse_market_open,
    nse_session_phase,
)

checks = {
    "09:11 IST Wed": datetime(2026, 6, 11, 3, 41, tzinfo=timezone.utc),
    "09:00 IST Wed": datetime(2026, 6, 11, 3, 30, tzinfo=timezone.utc),
    "09:15 IST Wed": datetime(2026, 6, 11, 3, 45, tzinfo=timezone.utc),
    "08:59 IST Wed": datetime(2026, 6, 11, 3, 29, tzinfo=timezone.utc),
    "12:00 IST Wed": datetime(2026, 6, 11, 6, 30, tzinfo=timezone.utc),
    "16:00 IST Wed": datetime(2026, 6, 11, 10, 30, tzinfo=timezone.utc),
    "12:00 IST Sun": datetime(2026, 6, 7, 6, 30, tzinfo=timezone.utc),
}
for label, t in checks.items():
    print(
        f"{label}: phase={nse_session_phase(t):8s} data_live={is_nse_data_live(t)!s:5s} "
        f"market_open={is_nse_market_open(t)!s:5s} session_date={current_session_date(t)}"
    )

assert nse_session_phase(checks["09:11 IST Wed"]) == "pre_open"
assert is_nse_data_live(checks["09:11 IST Wed"])
assert not is_nse_market_open(checks["09:11 IST Wed"])
assert current_session_date(checks["09:11 IST Wed"]).isoformat() == "2026-06-11"
assert nse_session_phase(checks["08:59 IST Wed"]) == "closed"
assert nse_session_phase(checks["09:15 IST Wed"]) == "open"
assert nse_session_phase(checks["16:00 IST Wed"]) == "closed"
assert nse_session_phase(checks["12:00 IST Sun"]) == "closed"
print("all assertions passed")

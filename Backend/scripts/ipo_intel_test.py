"""End-to-end test of the IPO intel scrape — fetches, parses, merges, persists.

Run from Backend:  python scripts/ipo_intel_test.py
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    from app.db import crud
    from app.db.database import Base, SessionLocal, engine
    from app.db.migrations import migrate_ipo_intel_columns
    from app.services.ipo_intel import run_ipo_intel_scrape

    Base.metadata.create_all(bind=engine)
    migrate_ipo_intel_columns()

    summary = run_ipo_intel_scrape()
    print("summary:", summary)

    with SessionLocal() as db:
        rows = crud.list_ipo_intel(db)

    print(f"\n{len(rows)} rows in ipo_intel:")
    for r in rows[:12]:
        print(
            f"  {r['display_name'][:32]:<32} status={r['status'] or '-':<8} "
            f"GMP={r['gmp'] if r['gmp'] is not None else '-':<7} "
            f"({r['gmp_pct'] if r['gmp_pct'] is not None else '-'}%) "
            f"sub_total={r['sub_total'] if r['sub_total'] is not None else '-'} "
            f"src={r['sources']}"
        )

    merged = [r for r in rows if r["sources"] == "investorgain+chittorgarh"]
    print(f"\nmerged from both sources: {len(merged)}")
    assert rows, "scrape produced no rows"
    print("IPO INTEL TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

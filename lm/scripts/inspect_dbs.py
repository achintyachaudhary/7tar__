"""List tables (and row counts for stock tables) in local SQLite files and the stock_ai Postgres."""

import glob
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

for f in sorted(glob.glob(str(DATA_DIR / "*.db"))):
    print(f"\n== {f} ==")
    try:
        con = sqlite3.connect(f)
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        print("tables:", tables)
        for t in ("stock_prices_daily", "stock_universe", "stock_profiles", "day_scan_snapshots",
                  "financial_cache", "holdings_cache"):
            if t in tables:
                n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                print(f"  {t}: {n} rows")
        con.close()
    except Exception as exc:
        print("  error:", exc)

print("\n== postgres stock_ai ==")
try:
    from sqlalchemy import create_engine, inspect
    from app.config import DATABASE_URL
    from app.db.stockdata import _normalize
    eng = create_engine(_normalize(DATABASE_URL))
    print("tables:", inspect(eng).get_table_names())
except Exception as exc:
    print("  error:", exc)

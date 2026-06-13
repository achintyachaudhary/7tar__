"""Report which database the existing Backend uses (credentials masked) and stock table row counts."""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent.parent / "Backend"
sys.path.insert(0, str(BACKEND))

from sqlalchemy import inspect, text

from app.db.database import engine  # Backend's own engine

url = engine.url
print(f"dialect : {url.get_backend_name()}")
print(f"host    : {url.host}")
print(f"database: {url.database}")
print(f"user    : {url.username}")

tables = inspect(engine).get_table_names()
print(f"tables  : {len(tables)}")
with engine.connect() as conn:
    for t in ("stock_prices_daily", "stock_universe", "stock_profiles",
              "day_scan_snapshots", "financial_cache", "holdings_cache"):
        if t in tables:
            n = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            print(f"  {t}: {n} rows")

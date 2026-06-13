"""Remove duplicate sample articles from stock_news.

The first ingestion run used random point IDs; the shared ingest path now uses
deterministic IDs (uuid5 of ticker|title). This deletes only points whose ID
does not match the deterministic ID for their own ticker+title — i.e. the old
duplicate copies of the same articles. No collection-level operations.
"""

import sys
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import QDRANT_COLLECTION
from app.vector.qdrant_store import client

qc = client()
points, _ = qc.scroll(QDRANT_COLLECTION, limit=1000, with_payload=True)

stale = []
for p in points:
    payload = p.payload or {}
    expected = str(uuid5(NAMESPACE_URL, f"{payload.get('ticker', '')}|{payload.get('title', '')}"))
    if str(p.id) != expected:
        stale.append(p.id)
        print(f"duplicate: [{payload.get('ticker')}] {payload.get('title', '')[:50]} ({p.id})")

if stale:
    qc.delete(QDRANT_COLLECTION, points_selector=stale)
    print(f"\nremoved {len(stale)} duplicate points")
else:
    print("no duplicates found")
print(f"document count now: {qc.count(QDRANT_COLLECTION).count}")

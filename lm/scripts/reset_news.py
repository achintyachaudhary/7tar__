"""Drop and re-create the stock_news collection, then re-ingest the bundled samples.

Use when the collection has duplicates or you want a clean slate.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import QDRANT_COLLECTION
from app.vector.qdrant_store import client
from app.services.news_ingest import SAMPLES, ingest_articles

qc = client()
if qc.collection_exists(QDRANT_COLLECTION):
    qc.delete_collection(QDRANT_COLLECTION)
    print(f"deleted collection {QDRANT_COLLECTION}")

stored = ingest_articles(SAMPLES)
print(f"re-ingested {len(stored)} samples: {stored}")
print(f"document count: {qc.count(QDRANT_COLLECTION).count}")

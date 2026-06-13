from uuid import uuid4

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from app.config import QDRANT_URL, QDRANT_COLLECTION
from app.vector.embeddings import embed, embedding_dim

_client: QdrantClient | None = None


def client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=QDRANT_URL, timeout=30)
    return _client


def ensure_collection() -> None:
    qc = client()
    if not qc.collection_exists(QDRANT_COLLECTION):
        qc.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=VectorParams(size=embedding_dim(), distance=Distance.COSINE),
        )


def upsert_document(text: str, payload: dict, point_id: str | None = None) -> str:
    ensure_collection()
    point_id = point_id or str(uuid4())
    client().upsert(
        collection_name=QDRANT_COLLECTION,
        points=[PointStruct(id=point_id, vector=embed(text), payload={**payload, "text": text})],
    )
    return point_id


def search(query: str, limit: int = 8, ticker: str | None = None) -> list[dict]:
    """Semantic search; optionally narrowed to one ticker. Returns payloads with scores."""
    qc = client()
    if not qc.collection_exists(QDRANT_COLLECTION):
        return []

    query_filter = None
    if ticker:
        query_filter = Filter(
            must=[FieldCondition(key="ticker", match=MatchValue(value=ticker.upper()))]
        )

    hits = qc.query_points(
        collection_name=QDRANT_COLLECTION,
        query=embed(query),
        limit=limit,
        query_filter=query_filter,
    ).points
    return [{**(h.payload or {}), "score": round(h.score, 4)} for h in hits]


def is_available() -> bool:
    try:
        client().get_collections()
        return True
    except Exception:
        return False

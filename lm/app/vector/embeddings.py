import requests

from app.config import OLLAMA_URL, EMBED_MODEL


def embed(text: str, timeout: int = 120) -> list[float]:
    response = requests.post(
        f"{OLLAMA_URL}/api/embed",
        json={"model": EMBED_MODEL, "input": text},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()["embeddings"][0]


def embedding_dim() -> int:
    """Probe the embedding model once to learn its vector size."""
    return len(embed("dimension probe"))

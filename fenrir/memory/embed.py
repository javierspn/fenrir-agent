"""Shared embedding helper (002). One place that turns text into a 768-dim vector
via the reused nomic-embed-text model on Ollama, used by both the retrieval selector
and the additive episode writer so episodes are searchable by similarity (FR-007).
"""
from __future__ import annotations

import httpx

from fenrir.settings import get_settings


def embed(text: str) -> list[float]:
    """Return the 768-dim embedding for ``text`` (nomic-embed-text via Ollama)."""
    s = get_settings()
    resp = httpx.post(
        f"{s.OLLAMA_HOST}/api/embeddings",
        json={"model": s.EMBED_MODEL, "prompt": text},
        timeout=60.0,
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


def to_pgvector(vec: list[float]) -> str:
    """Render an embedding as a pgvector literal: ``[0.1,0.2,...]``."""
    return "[" + ",".join(str(x) for x in vec) + "]"

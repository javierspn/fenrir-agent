"""Shared embedding helper (002). One place that turns text into a 768-dim vector
via the reused nomic-embed-text model on Ollama, used by both the retrieval selector
and the additive episode writer so episodes are searchable by similarity (FR-007).
"""
from __future__ import annotations

import httpx

from fenrir.settings import get_settings

# nomic-embed-text is hard-capped at a 2048-token context; over-long input makes
# Ollama 500 ("input length exceeds the context length") instead of truncating.
# Some MATH problem statements tokenize past that (dense LaTeX ~1.3 char/token),
# so cap the input by characters before the call. 2600 chars stays under 2048
# tokens even at the densest realistic ratio, while keeping ample similarity
# signal — the leading problem text dominates the embedding regardless.
_MAX_EMBED_CHARS = 2600


def embed(text: str) -> list[float]:
    """Return the 768-dim embedding for ``text`` (nomic-embed-text via Ollama)."""
    s = get_settings()
    resp = httpx.post(
        f"{s.OLLAMA_HOST}/api/embeddings",
        json={"model": s.EMBED_MODEL, "prompt": text[:_MAX_EMBED_CHARS]},
        timeout=60.0,
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


def to_pgvector(vec: list[float]) -> str:
    """Render an embedding as a pgvector literal: ``[0.1,0.2,...]``."""
    return "[" + ",".join(str(x) for x in vec) + "]"

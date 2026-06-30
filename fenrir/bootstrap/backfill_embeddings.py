"""Training-pool embedding backfill (004 T003).

Additive: fills ``benchmark_tasks.embedding`` for ``pool='training'`` rows so the curriculum
can score skill-adjacency by cosine (fenrir.curriculum). Idempotent — only embeds rows whose
embedding is still NULL. Evaluation/transfer rows are left NULL on purpose: selection never
reads them, so the "embedded ⇒ training" invariant also guards pool isolation (Constitution III).

Embeddings come from the local nomic-embed-text model via Ollama (no frontier call → no budget
spend, IX). Run as part of `python -m fenrir.bootstrap`, or directly:
    python -m fenrir.bootstrap.backfill_embeddings
"""
from __future__ import annotations

import psycopg

from fenrir import db
from fenrir.memory.embed import embed, to_pgvector


def backfill_training_embeddings(conn: psycopg.Connection) -> int:
    """Embed every not-yet-embedded training task. Returns the number embedded."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, content FROM benchmark_tasks "
            "WHERE pool = 'training' AND embedding IS NULL"
        )
        rows = cur.fetchall()

    n = 0
    for task_id, content in rows:
        vec = to_pgvector(embed(content or ""))
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE benchmark_tasks SET embedding = %s::vector WHERE id = %s",
                (vec, task_id),
            )
        n += 1
    conn.commit()
    return n


def main() -> int:
    conn = db.connect()
    try:
        n = backfill_training_embeddings(conn)
        print(f"✓ embedded {n} training task(s)")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())

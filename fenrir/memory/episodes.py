"""Additive episode writer (002, T015). Constitution VI / FR-016/017.

Every attempt — success, failure, or unverified — writes exactly one
short_term_memory row capturing the task, prediction, verdict, prediction error,
and solve path. Episodes are NEVER hard-deleted; consolidation only marks them.
"""
from __future__ import annotations

from dataclasses import dataclass

import psycopg

from fenrir.memory.embed import embed, to_pgvector
from fenrir.memory.salience import salience


@dataclass
class Episode:
    task_id: str
    content: str
    domain: str
    prediction_error: float
    importance: float = 1.0


def write_episode(conn: psycopg.Connection, ep: Episode) -> str:
    """Insert an additive episode and return its id. salience computed from factors.
    Uses the baseline STM columns (importance, retrieval_count, status default 'raw')."""
    sal = salience(ep.prediction_error, ep.importance, 0)
    # embed on write so the episode is recallable by vector similarity (FR-007).
    # Fall back to a NULL embedding if the embedder is unreachable — never block the
    # additive write (Constitution VI: the episode must persist regardless).
    try:
        vec: str | None = to_pgvector(embed(ep.content))
    except Exception:
        vec = None
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO short_term_memory "
            "(content, embedding, domain, task_id, prediction_error, importance, "
            " retrieval_count, salience) "
            "VALUES (%s, %s::vector, %s, %s, %s, %s, 0, %s) RETURNING id",
            (ep.content, vec, ep.domain, ep.task_id, ep.prediction_error, ep.importance, sal),
        )
        episode_id = cur.fetchone()[0]
    conn.commit()
    return str(episode_id)

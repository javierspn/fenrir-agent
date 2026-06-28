"""Shared helpers for the 003-C competitive-replay integration tests.

Build embeddings as unit vectors in the first two dims at a chosen angle, so cosine between
two episodes is cos(Δangle) — clusters and over-merge cases are geometrically exact.
"""
from __future__ import annotations

import math


def vec_at(theta_deg: float) -> str:
    """768-dim pgvector literal: a unit vector at `theta_deg` in dims 0..1, zero elsewhere."""
    t = math.radians(theta_deg)
    comps = [math.cos(t), math.sin(t)] + [0.0] * 766
    return "[" + ",".join(repr(x) for x in comps) + "]"


def insert_episode(conn, *, theta, pe=0.1, salience=2.0, is_eval=False, domain="math"):
    """Insert one raw short_term_memory episode with an embedding. When is_eval=True it is
    linked to an is_eval task so the pool-isolation guard can be exercised."""
    task_id = None
    with conn.cursor() as cur:
        if is_eval:
            cur.execute(
                "INSERT INTO tasks (content, domain, is_eval) VALUES ('q','math', true) "
                "RETURNING id"
            )
            task_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO short_term_memory "
            "(content, embedding, domain, task_id, prediction_error, importance, "
            " retrieval_count, salience, consolidation_status) "
            "VALUES ('ep', %s::vector, %s, %s, %s, 1.0, 0, %s, 'raw') RETURNING id",
            (vec_at(theta), domain, task_id, pe, salience),
        )
        eid = cur.fetchone()[0]
    conn.commit()
    return str(eid)

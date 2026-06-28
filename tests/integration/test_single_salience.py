"""003 increment A — one significance definition (significance.contract Invariant 1, SC-001).

salience(), the recompute() path, and the bump_retrieval_count() path must all yield the
identical score for identical (prediction_error, importance, retrieval_count). The prior code
had three divergent SQL formulas (the 1.0-vs-0.5 default drift + a retrieval_count off-by-one);
this asserts they are gone — every entry point now routes through salience().
"""
from __future__ import annotations

import random

from fenrir.memory.salience import bump_retrieval_count, recompute, salience


def _insert(conn, pe, importance, retrieval_count):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO short_term_memory "
            "(content, domain, task_id, prediction_error, importance, retrieval_count, salience) "
            "VALUES ('x','math', gen_random_uuid(), %s, %s, %s, 0) RETURNING id",
            (pe, importance, retrieval_count),
        )
        eid = cur.fetchone()[0]
    conn.commit()
    return eid


def _read(conn, eid, col):
    with conn.cursor() as cur:
        cur.execute(f"SELECT {col} FROM short_term_memory WHERE id = %s", (eid,))
        return cur.fetchone()[0]


def test_recompute_matches_python_definition(migrated_conn):
    rng = random.Random(7)
    for _ in range(20):
        pe = round(rng.uniform(0, 1), 4)
        importance = round(rng.uniform(0, 3), 4)
        rc = rng.randint(0, 12)
        eid = _insert(migrated_conn, pe, importance, rc)
        recompute(migrated_conn, eid)
        stored = float(_read(migrated_conn, eid, "salience"))
        assert abs(stored - salience(pe, importance, rc)) < 1e-9


def test_bump_matches_python_definition(migrated_conn):
    """bump increments retrieval_count then recomputes with the POST-bump count, once."""
    rng = random.Random(11)
    for _ in range(20):
        pe = round(rng.uniform(0, 1), 4)
        importance = round(rng.uniform(0, 3), 4)
        rc = rng.randint(0, 12)
        eid = _insert(migrated_conn, pe, importance, rc)
        bump_retrieval_count(migrated_conn, [str(eid)])
        new_rc = int(_read(migrated_conn, eid, "retrieval_count"))
        stored = float(_read(migrated_conn, eid, "salience"))
        assert new_rc == rc + 1                                   # incremented exactly once
        assert abs(stored - salience(pe, importance, new_rc)) < 1e-9   # no off-by-one

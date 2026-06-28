"""003 increment C — merge-to-one (SC-005, FR-015/020).

A cluster of K near-duplicate successful episodes consolidates into exactly ONE abstraction
whose source list contains all K — not K rows. Sources are marked consolidated; nothing deleted.
"""
from __future__ import annotations

from fenrir.consolidation import sleep
from tests.integration._replay_helpers import insert_episode


def test_k_cluster_yields_one_abstraction(migrated_conn):
    conn = migrated_conn
    k_ids = [insert_episode(conn, theta=t, pe=0.1, salience=3.0) for t in (0, 1, 2, 1.5)]
    # two unrelated raw episodes (a separate, far cluster)
    insert_episode(conn, theta=90, pe=0.1, salience=0.5)
    insert_episode(conn, theta=91, pe=0.1, salience=0.5)

    before = _count_stm(conn)
    res = sleep.run(conn, seed=1, replay_budget=64)

    assert res["merged"] >= 1
    # exactly one abstraction carries all K sources
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM long_term_memory WHERE array_length(source_memories,1) = 4"
        )
        assert cur.fetchone()[0] == 1
        cur.execute(
            "SELECT source_memories FROM long_term_memory WHERE array_length(source_memories,1)=4"
        )
        sources = {str(x) for x in cur.fetchone()[0]}
        assert sources == set(k_ids)
        # the K sources are consolidated, none deleted (additive, VI)
        cur.execute(
            "SELECT count(*) FROM short_term_memory WHERE id = ANY(%s) "
            "AND consolidation_status='consolidated'",
            (k_ids,),
        )
        assert cur.fetchone()[0] == 4
    assert _count_stm(conn) == before          # zero deletions


def _count_stm(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM short_term_memory")
        return cur.fetchone()[0]

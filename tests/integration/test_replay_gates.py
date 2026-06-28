"""003 increment C — per-cluster gate + over-merge guard (FR-017/018, Acceptance 4).

A cluster that would regress on the held-out slice is skipped (members stay raw); an
internally-incoherent cluster (two distinct methods) is split, never collapsed into one row.
"""
from __future__ import annotations

from fenrir.consolidation import sleep
from tests.integration._replay_helpers import insert_episode


def test_regressing_cluster_is_skipped(migrated_conn):
    conn = migrated_conn
    # high average prediction error (≥ 0.9) → predictability gate rejects → not merged
    bad = [insert_episode(conn, theta=t, pe=0.95, salience=3.0) for t in (0, 1, 2)]
    res = sleep.run(conn, seed=1, replay_budget=32)

    assert res["skipped_gate"] >= 1
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM short_term_memory WHERE id = ANY(%s) "
            "AND consolidation_status='raw'",
            (bad,),
        )
        assert cur.fetchone()[0] == 3            # all members remain raw
        cur.execute("SELECT count(*) FROM long_term_memory WHERE abstraction_level >= 2")
        assert cur.fetchone()[0] == 0            # nothing merged


def test_incoherent_cluster_is_split(migrated_conn):
    conn = migrated_conn
    # all within sim_floor of the seed but B·C = cos60 = 0.5 → spread 0.5 > COHERENCE_MAX_SPREAD
    insert_episode(conn, theta=0, pe=0.1, salience=3.0)
    insert_episode(conn, theta=30, pe=0.1, salience=3.0)
    insert_episode(conn, theta=-30, pe=0.1, salience=3.0)

    sleep.run(conn, seed=1, replay_budget=64)
    with conn.cursor() as cur:
        # split → no single 3-source mushy abstraction
        cur.execute(
            "SELECT count(*) FROM long_term_memory WHERE array_length(source_memories,1) = 3"
        )
        assert cur.fetchone()[0] == 0

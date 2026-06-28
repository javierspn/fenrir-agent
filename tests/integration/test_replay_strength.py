"""003 increment C — replay-weighted strength + competition (SC-005/006, FR-016).

Strength and reinforcement_count grow with replay draws (not a constant 0.5), and a
higher-significance cluster receives more draws than a lower one under a fixed seed.
"""
from __future__ import annotations

from fenrir.consolidation import sleep
from fenrir.settings import get_settings
from tests.integration._replay_helpers import insert_episode


def test_strength_accrues_per_draw(migrated_conn):
    conn = migrated_conn
    spr = get_settings().STRENGTH_PER_REPLAY
    # one coherent cluster only → every draw lands on it
    for t in (0, 1, 2):
        insert_episode(conn, theta=t, pe=0.1, salience=3.0)

    res = sleep.run(conn, seed=1, replay_budget=10)
    assert res["replays"] == 10
    with conn.cursor() as cur:
        cur.execute(
            "SELECT strength, reinforcement_count FROM long_term_memory "
            "WHERE array_length(source_memories,1) = 3"
        )
        strength, rc = cur.fetchone()
    assert int(rc) == 10                         # one count per draw
    assert abs(float(strength) - 10 * spr) < 1e-9   # d × STRENGTH_PER_REPLAY, not constant 0.5


def test_higher_significance_cluster_wins_more_draws(migrated_conn):
    conn = migrated_conn
    hi = [insert_episode(conn, theta=t, pe=0.1, salience=5.0) for t in (0, 1)]
    lo = [insert_episode(conn, theta=t, pe=0.1, salience=0.3) for t in (90, 91)]

    sleep.run(conn, seed=1, replay_budget=64)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT reinforcement_count FROM long_term_memory WHERE source_memories @> %s",
            (hi,),
        )
        hi_rc = cur.fetchone()[0]
        cur.execute(
            "SELECT reinforcement_count FROM long_term_memory WHERE source_memories @> %s",
            (lo,),
        )
        lo_row = cur.fetchone()
        lo_rc = lo_row[0] if lo_row else 0
    assert int(hi_rc) > int(lo_rc)               # competition monotonic (within fixed seed)

"""003 increment C — additivity, idempotency, pool isolation, empty pass (SC-004/009, FR-020/021).

Re-running a pass creates no duplicate abstractions and deletes nothing; an eval-pool episode is
never a candidate; and a pass with no candidates returns a successful empty result, not an error.
"""
from __future__ import annotations

from fenrir.consolidation import sleep
from tests.integration._replay_helpers import insert_episode


def test_empty_pass_is_successful(migrated_conn):
    res = sleep.run(migrated_conn, seed=1, replay_budget=16)   # no episodes at all
    assert res["merged"] == 0 and res["replays"] == 0
    assert res["clusters"] == 0                                # not an error


def test_rerun_is_idempotent(migrated_conn):
    conn = migrated_conn
    for t in (0, 1, 2):
        insert_episode(conn, theta=t, pe=0.1, salience=3.0)

    first = sleep.run(conn, seed=1, replay_budget=32)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM long_term_memory")
        after_first = cur.fetchone()[0]
    assert first["merged"] >= 1

    second = sleep.run(conn, seed=1, replay_budget=32)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM long_term_memory")
        after_second = cur.fetchone()[0]
    assert second["merged"] == 0                # consolidated sources excluded → no new rows
    assert after_second == after_first          # no duplicate abstractions


def test_eval_pool_episode_never_consolidated(migrated_conn):
    conn = migrated_conn
    train = [insert_episode(conn, theta=t, pe=0.1, salience=3.0) for t in (0, 1, 2)]
    evil = insert_episode(conn, theta=0.5, pe=0.1, salience=9.0, is_eval=True)  # eval, near cluster

    sleep.run(conn, seed=1, replay_budget=64)
    with conn.cursor() as cur:
        # the eval episode is never a candidate → stays raw, never in any source list
        cur.execute("SELECT consolidation_status FROM short_term_memory WHERE id = %s", (evil,))
        assert cur.fetchone()[0] == "raw"
        cur.execute(
            "SELECT count(*) FROM long_term_memory WHERE %s = ANY(source_memories)", (evil,)
        )
        assert cur.fetchone()[0] == 0
        # the training cluster still consolidated normally
        cur.execute(
            "SELECT count(*) FROM short_term_memory WHERE id = ANY(%s) "
            "AND consolidation_status='consolidated'",
            (train,),
        )
        assert cur.fetchone()[0] == 3

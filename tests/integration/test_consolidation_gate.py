"""US4 (T030): consolidation processes salience-descending, the predictability gate
rejects non-improving merges, the held-out slice is training-only, and NO source
episode is hard-deleted. SC-007, Constitution III/V/VI.
"""
from __future__ import annotations

from fenrir.consolidation import sleep
from tests.integration._replay_helpers import vec_at


def _seed_training(conn, n):
    with conn.cursor() as cur:
        for i in range(n):
            cur.execute(
                "INSERT INTO benchmark_tasks (benchmark, problem_id, pool, difficulty, domain, "
                " content, ground_truth) VALUES ('gsm8k', %s, 'training', 'easy', 'math', %s, %s)",
                (f"c-{i}", f"{i}+{i}", str(2 * i)),
            )
        # an evaluation task that must NEVER be held_out
        cur.execute(
            "INSERT INTO benchmark_tasks (benchmark, problem_id, pool, difficulty, domain, "
            " content, ground_truth) "
            "VALUES ('gsm8k','eval-x','evaluation','easy','math','9+9','18')"
        )
    conn.commit()


def _episode(conn, content, pe, importance=1.0, theta=0.0):
    # 003-C clusters by embedding, so candidates need one (real episodes are embedded on write).
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO short_term_memory (content, embedding, domain, prediction_error, "
            " importance, retrieval_count, salience, consolidation_status) "
            "VALUES (%s,%s::vector,'math',%s,%s,0,%s,'raw') RETURNING id",
            (content, vec_at(theta), pe, importance, pe * importance),
        )
        eid = cur.fetchone()[0]
    conn.commit()
    return str(eid)


def test_held_out_is_training_only(migrated_conn):
    conn = migrated_conn
    _seed_training(conn, 20)
    sleep.ensure_heldout(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM benchmark_tasks WHERE held_out AND pool='evaluation'")
        assert cur.fetchone()[0] == 0          # never the evaluation pool (III)
        cur.execute("SELECT count(*) FROM benchmark_tasks WHERE held_out AND pool='training'")
        assert cur.fetchone()[0] >= 1


def test_gate_rejects_high_residual_error_and_never_deletes(migrated_conn):
    conn = migrated_conn
    _seed_training(conn, 20)
    # distinct embeddings → distinct clusters, so the gate decides each independently
    mergeable = _episode(conn, "low-residual cluster", pe=0.4, theta=0)     # avg PE < 0.9 → merge
    idiosyncratic = _episode(conn, "noisy cluster", pe=0.95, theta=90)      # avg PE ≥ 0.9 → reject

    before = _count_episodes(conn)
    summary = sleep.run(conn)

    assert summary["merged"] >= 1
    after = _count_episodes(conn)
    assert after == before                       # additive — zero hard deletes (SC-007)

    with conn.cursor() as cur:
        cur.execute("SELECT consolidation_status FROM short_term_memory WHERE id=%s", (mergeable,))
        assert cur.fetchone()[0] == "consolidated"
        cur.execute("SELECT consolidation_status FROM short_term_memory WHERE id=%s",
                    (idiosyncratic,))
        assert cur.fetchone()[0] == "raw"   # idiosyncratic detail left raw/unmerged (V)
        # the merged abstraction is a NEW long_term_memory row (additive, FR-021)
        cur.execute("SELECT count(*) FROM long_term_memory WHERE memory_type='semantic'")
        assert cur.fetchone()[0] >= 1


def _count_episodes(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM short_term_memory")
        return cur.fetchone()[0]

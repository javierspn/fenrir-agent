"""US1 (T018): the loop selects only the training pool; the evaluation pool is never
read or written. FR-001, Constitution III.
"""
from __future__ import annotations

from fenrir import core


def _seed(conn, problem_id, pool, content, gt):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO benchmark_tasks (benchmark, problem_id, pool, difficulty, domain, "
            " content, ground_truth) VALUES ('gsm8k', %s, %s, 'easy', 'math', %s, %s)",
            (problem_id, pool, content, gt),
        )
    conn.commit()


def test_select_task_never_returns_evaluation(migrated_conn):
    conn = migrated_conn
    _seed(conn, "eval-only", "evaluation", "5+5", "10")
    # only an evaluation-pool task exists → selector must return nothing
    assert core.select_task(conn) is None

    _seed(conn, "train-ok", "training", "2+2", "4")
    bt = core.select_task(conn)
    assert bt is not None and bt.problem_id == "train-ok"


def test_select_predicate_filters_solved_and_prefers_underpracticed(migrated_conn):
    conn = migrated_conn
    _seed(conn, "t-a", "training", "1+1", "2")
    _seed(conn, "t-b", "training", "3+3", "6")
    # mark t-a already solved → must not be reselected (FR-002)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO tasks (content, domain, source, benchmark_id, benchmark_pool, status, "
            " is_eval) VALUES ('1+1','math','benchmark','t-a','training','succeeded', false)"
        )
    conn.commit()
    for _ in range(5):
        bt = core.select_task(conn)
        assert bt.problem_id == "t-b"

"""T016 [US2]: the anti-reward-hacking guards hold on every cohort (SC-005, C1/C4).

A cohort = one run(n). run() drives the full loop (LLM proxy), so this suite exercises the
selection composition that run() uses — the external-slot plan + per-slot select() — and
asserts the guards on the resulting selection stream: ≥30% external, 0 eval-pool / is_eval,
0 non-training. The on-DB write of the same guards (is_eval=false, pool='training') is covered
by test_pool_no_leak; the live end-to-end cohort is exercised by T026.
"""
from __future__ import annotations

from fenrir import curriculum
from fenrir.settings import get_settings

from ._curriculum_helpers import seed_bench_task, seed_skill


def _cohort_selection_stream(conn, n):
    plan = curriculum.external_slot_plan(n, get_settings().EXTERNAL_MIN_FRACTION)
    return [curriculum.select(conn, force_external=plan[i], seed=i) for i in range(n)]


def test_guards_hold_on_a_cohort(migrated_conn):
    conn = migrated_conn
    seed_skill(conn)
    # a realistic mixed training pool + a held-out evaluation pool that must never be touched
    for pid, cos in {"a": 0.83, "b": 0.88, "c": 0.55, "d": 0.91}.items():
        seed_bench_task(conn, pid, cos)
    seed_bench_task(conn, "eval-x", 0.85, pool="evaluation")
    seed_bench_task(conn, "eval-y", 0.88, pool="evaluation")

    n = 10
    stream = _cohort_selection_stream(conn, n)
    assert all(s is not None for s in stream)

    external = sum(1 for s in stream if s.selected_via in ("external", "fallback"))
    assert external / n >= get_settings().EXTERNAL_MIN_FRACTION   # ≥30% guard (FR-004)

    chosen = {s.task.problem_id for s in stream}
    assert "eval-x" not in chosen and "eval-y" not in chosen      # eval never selected (III)


def test_eval_only_pool_yields_nothing(migrated_conn):
    # No training tasks → both lanes must return None (never reach into the evaluation pool).
    conn = migrated_conn
    seed_skill(conn)
    seed_bench_task(conn, "eval-only", 0.88, pool="evaluation")
    assert curriculum.select(conn, force_external=True) is None
    assert curriculum.select(conn, force_external=False) is None

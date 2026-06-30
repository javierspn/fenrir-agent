"""T008 [US1]: the feasibility gate never emits an infeasible or trivially-covered task.

Adjacency lane only ever returns a task in the *adjacent* band; below the feasibility floor
(cold) and at/above the trivial ceiling (near-duplicate) are both rejected. (SC-006, C2.)
"""
from __future__ import annotations

from fenrir import curriculum

from ._curriculum_helpers import seed_bench_task, seed_skill

_POOL = {
    "cold-1": 0.30,
    "cold-2": 0.79,        # just below the 0.80 floor → infeasible
    "ok-1": 0.81,
    "ok-2": 0.88,
    "dup-1": 0.92,         # at the ceiling → trivial
    "dup-2": 0.985,
}
_BAD = {"cold-1", "cold-2", "dup-1", "dup-2"}


def test_adjacency_lane_never_emits_out_of_band(migrated_conn):
    conn = migrated_conn
    seed_skill(conn)
    for pid, cos in _POOL.items():
        seed_bench_task(conn, pid, cos)

    for i in range(300):
        sel = curriculum.select(conn, force_external=False, seed=i)
        assert sel.task.problem_id not in _BAD


def test_all_infeasible_falls_back_not_emits_bad(migrated_conn):
    # Only out-of-band tasks exist → adjacency lane is empty → it falls back to the external
    # lane (which is allowed to draw any training task) rather than emitting from the gate.
    conn = migrated_conn
    seed_skill(conn)
    seed_bench_task(conn, "cold-only", 0.40)
    seed_bench_task(conn, "dup-only", 0.97)

    sel = curriculum.select(conn, force_external=False, seed=1)
    assert sel is not None
    assert sel.selected_via == "fallback"      # not 'adjacency' — the gate emitted nothing

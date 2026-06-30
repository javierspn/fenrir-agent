"""T007 [US1]: gate-ON (adjacency) lifts coverage above gate-OFF (uniform) on the same pool.

Coverage = the picked task's max-skill cosine clears RETRIEVAL_SIM_FLOOR (a solve-time
retrieval hit, the SC-001 metric). With the floor pinned to the retrieval floor, every
adjacency-lane pick is covered; the uniform external lane only hits coverage as often as the
pool happens to contain covered tasks. (US1 Independent Test, SC-001, selection.contract C2/C3.)
"""
from __future__ import annotations

from fenrir import curriculum
from fenrir.settings import get_settings

from ._curriculum_helpers import seed_bench_task, seed_skill

# problem_id → cosine to the single seeded skill. Mix of infeasible / adjacent / trivial.
_POOL = {
    "infeasible-a": 0.40,
    "infeasible-b": 0.65,
    "adjacent-a": 0.82,
    "adjacent-b": 0.86,
    "adjacent-c": 0.90,
    "trivial-a": 0.95,
    "trivial-b": 0.99,
}


def _seed(conn):
    seed_skill(conn)
    for pid, cos in _POOL.items():
        seed_bench_task(conn, pid, cos)


def _covered(problem_id: str) -> bool:
    return _POOL[problem_id] >= get_settings().RETRIEVAL_SIM_FLOOR


def test_gate_on_beats_gate_off_coverage(migrated_conn):
    conn = migrated_conn
    _seed(conn)

    draws = 200
    on = sum(
        _covered(curriculum.select(conn, force_external=False, seed=i).task.problem_id)
        for i in range(draws)
    )
    off = sum(
        _covered(curriculum.select(conn, force_external=True, seed=i).task.problem_id)
        for i in range(draws)
    )
    # adjacency lane is covered every time; uniform lane only on the covered share of the pool
    assert on == draws
    assert off < on


def test_gate_on_only_picks_the_adjacent_band(migrated_conn):
    conn = migrated_conn
    _seed(conn)
    s = get_settings()
    for i in range(200):
        sel = curriculum.select(conn, force_external=False, seed=i)
        cos = _POOL[sel.task.problem_id]
        assert s.ADJACENCY_FEASIBILITY_FLOOR <= cos < s.ADJACENCY_TRIVIAL_CEIL
        assert sel.selected_via == "adjacency"
        assert sel.adjacent_skill_id is not None

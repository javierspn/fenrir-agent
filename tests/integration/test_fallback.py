"""T017 [US2]: cold start / adjacency exhaustion never stalls (FR-008, C5).

With an empty skill library the adjacency lane has nothing to anchor to, so selection must
fall back to the uniform external draw and still fill a full cohort — never returning fewer
valid tasks than requested while unsolved training tasks remain.
"""
from __future__ import annotations

from fenrir import curriculum

from ._curriculum_helpers import seed_bench_task, seed_skill


def test_cold_start_empty_loadout_fills_the_cohort(migrated_conn):
    conn = migrated_conn
    # NO skills seeded — cold start. A modest training pool with embeddings present.
    for k in range(8):
        seed_bench_task(conn, f"t-{k}", 0.85)

    n = 50
    plan = curriculum.external_slot_plan(n, 0.30)
    stream = [curriculum.select(conn, force_external=plan[i], seed=i) for i in range(n)]

    assert all(s is not None for s in stream)                 # never stalls
    assert len(stream) == n
    # no skill ⇒ no adjacency lane
    assert all(s.selected_via in ("external", "fallback") for s in stream)


def test_adjacency_exhaustion_falls_back(migrated_conn):
    # A skill exists, but every task is out-of-band → adjacency lane empty → fallback fills it.
    conn = migrated_conn
    seed_skill(conn)
    seed_bench_task(conn, "cold", 0.50)
    seed_bench_task(conn, "dup", 0.98)

    sel = curriculum.select(conn, force_external=False, seed=3)
    assert sel is not None and sel.selected_via == "fallback"

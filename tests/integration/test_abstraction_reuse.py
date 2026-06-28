"""003 increment C — reuse instrumentation (SC-008, analyze G1; migration 0005).

(a) retrieve() surfaces consolidated long_term_memory abstractions so generalized knowledge is
reachable by later tasks, and (b) the per-task reuse SIGNAL is recorded
(tasks.retrieval_abstraction_id) — the countable, time-bucketed sink the SC-008 reuse-rate panel
reads. Together they are the headline compounding data path.
"""
from __future__ import annotations

import math

from fenrir.memory import retrieval


def _vec(theta_deg: float) -> list[float]:
    t = math.radians(theta_deg)
    return [math.cos(t), math.sin(t)] + [0.0] * 766


def _insert_abstraction(conn, theta=0.0):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO long_term_memory (content, embedding, memory_type, domain, "
            " abstraction_level, strength, is_anchor) "
            "VALUES ('abstraction[3]: sum of arithmetic series', %s::vector, 'semantic', 'math', "
            " 2, 0.5, false) RETURNING id",
            ("[" + ",".join(repr(x) for x in _vec(theta)) + "]",),
        )
        aid = str(cur.fetchone()[0])
    conn.commit()
    return aid


def test_retrieve_surfaces_consolidated_abstraction(migrated_conn, monkeypatch):
    conn = migrated_conn
    abstraction_id = _insert_abstraction(conn)
    # query embeds to the same direction → cosine ~1, above RETRIEVAL_SIM_FLOOR
    monkeypatch.setattr(retrieval, "embed", lambda _q: _vec(0))
    res = retrieval.retrieve(conn, "sum of an arithmetic series")

    assert any(a.abstraction_id == abstraction_id for a in res.abstractions)
    top = max(res.abstractions, key=lambda a: a.cosine)
    assert top.cosine >= 0.99


def test_reuse_signal_recorded_and_panel_counts(migrated_conn, monkeypatch):
    """The reuse sink: a surfaced abstraction is recorded on the task, and the SC-008 panel
    query counts a non-zero reuse rate (migration 0005)."""
    conn = migrated_conn
    abstraction_id = _insert_abstraction(conn)
    monkeypatch.setattr(retrieval, "embed", lambda _q: _vec(0))
    res = retrieval.retrieve(conn, "sum of an arithmetic series")
    top = res.abstractions[0].abstraction_id

    # simulate the loop's task UPDATE recording the surfaced abstraction
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO tasks (content, domain, retrieval_abstraction_id) "
            "VALUES ('later task','math', %s)",
            (top,),
        )
    conn.commit()
    assert top == abstraction_id

    with conn.cursor() as cur:
        # the headline reuse-rate panel query returns a measurably-above-zero share
        cur.execute(
            "SELECT avg(CASE WHEN retrieval_abstraction_id IS NOT NULL THEN 1.0 ELSE 0.0 END) "
            "FROM tasks"
        )
        assert float(cur.fetchone()[0]) > 0.0

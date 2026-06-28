"""SC-003 / FR-012/017/018 — bootstrap is idempotent + resumable; a failed fetch
leaves the system un-bootstrapped (spec edge case).

Models + benchmark download are external; they are monkeypatched so the DB-level
idempotency/resume contract is exercised without Ollama or network.
"""
from __future__ import annotations

import pytest

from fenrir.bootstrap import __main__ as bm


def _counts(conn):
    out = {}
    with conn.cursor() as cur:
        for table in ("long_term_memory", "graph_updates", "system_state", "benchmark_tasks"):
            cur.execute(f"SELECT count(*) FROM {table}")  # noqa: S608 — fixed table allowlist
            out[table] = cur.fetchone()[0]
    return out


def _stub_externals(monkeypatch):
    monkeypatch.setattr(bm, "ensure_models", lambda host: None)
    monkeypatch.setattr(
        "benchmark_loader.load.load_and_partition", lambda conn: {"training": 0, "evaluation": 0}
    )


def test_second_run_is_noop(migrated_conn, monkeypatch):
    _stub_externals(monkeypatch)
    assert bm.run(migrated_conn) == 0
    after_first = _counts(migrated_conn)
    assert bm.is_bootstrapped(migrated_conn)

    assert bm.run(migrated_conn) == 0  # marker present -> global guard short-circuits
    assert _counts(migrated_conn) == after_first


def test_failed_fetch_leaves_unbootstrapped_then_resumes(migrated_conn, monkeypatch):
    monkeypatch.setattr(bm, "ensure_models", lambda host: None)

    def boom(conn):
        raise RuntimeError("dataset source unavailable")

    monkeypatch.setattr("benchmark_loader.load.load_and_partition", boom)
    with pytest.raises(RuntimeError):
        bm.run(migrated_conn)
    # anchors/relations seeded, but NO marker — system is un-bootstrapped (edge case)
    assert not bm.is_bootstrapped(migrated_conn)

    # fix the source and re-run: per-section idempotency completes without duplication
    monkeypatch.setattr(
        "benchmark_loader.load.load_and_partition", lambda conn: {"training": 0}
    )
    assert bm.run(migrated_conn) == 0
    assert bm.is_bootstrapped(migrated_conn)

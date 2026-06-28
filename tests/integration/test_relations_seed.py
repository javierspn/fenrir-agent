"""FR-015 — ≥20 bootstrap_seed relations among anchors; idempotent reseed."""
from __future__ import annotations

from fenrir.bootstrap.anchors import seed_anchors
from fenrir.bootstrap.relations import seed_relations


def test_at_least_20_relations(migrated_conn):
    seed_anchors(migrated_conn)
    n = seed_relations(migrated_conn)
    assert n >= 20, n


def test_relations_are_bootstrap_seed_trigger(migrated_conn):
    seed_anchors(migrated_conn)
    seed_relations(migrated_conn)
    with migrated_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM graph_updates WHERE trigger <> 'bootstrap_seed'")
        assert cur.fetchone()[0] == 0


def test_relations_idempotent(migrated_conn):
    seed_anchors(migrated_conn)
    first = seed_relations(migrated_conn)
    second = seed_relations(migrated_conn)
    assert first == second

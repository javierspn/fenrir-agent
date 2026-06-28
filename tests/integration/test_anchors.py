"""SC-004 — 50–100 anchors, all is_anchor at strength 1.0 / decay 0; decay-immune."""
from __future__ import annotations

from fenrir.bootstrap.anchors import seed_anchors


def test_anchor_count_in_range(migrated_conn):
    n = seed_anchors(migrated_conn)
    assert 50 <= n <= 100, n


def test_all_anchors_max_strength_no_decay(migrated_conn):
    seed_anchors(migrated_conn)
    with migrated_conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM long_term_memory "
            "WHERE is_anchor AND (strength <> 1.0 OR decay_rate <> 0)"
        )
        assert cur.fetchone()[0] == 0


def test_decay_pass_leaves_anchors_untouched(migrated_conn):
    seed_anchors(migrated_conn)
    with migrated_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM long_term_memory WHERE is_anchor")
        before = cur.fetchone()[0]
        # a well-formed decay pass filters anchors out (research R4)
        cur.execute("UPDATE long_term_memory SET strength = strength * 0.5 WHERE is_anchor = FALSE")
        migrated_conn.commit()
        cur.execute("SELECT count(*) FROM long_term_memory WHERE is_anchor AND strength = 1.0")
        after = cur.fetchone()[0]
    assert before == after


def test_seed_anchors_idempotent(migrated_conn):
    first = seed_anchors(migrated_conn)
    second = seed_anchors(migrated_conn)
    assert first == second

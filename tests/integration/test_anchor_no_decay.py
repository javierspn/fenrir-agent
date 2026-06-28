"""003 increment B — anchor exemption (decay.contract Invariant 3, SC-003, spec I1 design).

Anchored ground truth lives in long_term_memory (is_anchor=true, decay_rate=0) and is exempt
from forgetting. Raw episodes (short_term_memory) carry NO anchor flag and always decay — the
exemption is satisfied structurally at the LTM layer.
"""
from __future__ import annotations

from fenrir.memory.salience import effective_salience_sql


def test_stm_has_no_anchor_column(migrated_conn):
    """Episodes are never anchors — the flag is an LTM-only property (resolves analyze I1)."""
    with migrated_conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'short_term_memory' AND column_name = 'is_anchor'"
        )
        assert cur.fetchone() is None


def test_ltm_anchor_decay_rate_zero(migrated_conn):
    with migrated_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO long_term_memory (content, memory_type, is_anchor, decay_rate) "
            "VALUES ('2+2=4', 'semantic', true, 0) RETURNING id, is_anchor, decay_rate"
        )
        _id, is_anchor, decay_rate = cur.fetchone()
    migrated_conn.commit()
    assert is_anchor is True
    assert float(decay_rate) == 0.0       # exempt by construction — never decays


def test_stm_decays_while_anchor_untouched(migrated_conn):
    """An old STM episode loses effective significance; the LTM anchor's strength does not."""
    with migrated_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO long_term_memory (content, memory_type, is_anchor, decay_rate, strength) "
            "VALUES ('pi is irrational', 'semantic', true, 0, 0.9) RETURNING id"
        )
        anchor_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO short_term_memory "
            "(content, domain, task_id, prediction_error, importance, retrieval_count, salience, "
            " created_at) VALUES ('x','math', gen_random_uuid(), 0.5, 1.0, 0, 2.0, "
            " now() - interval '120 days') RETURNING id"
        )
        stm_id = cur.fetchone()[0]
    migrated_conn.commit()

    expr = effective_salience_sql()
    with migrated_conn.cursor() as cur:
        cur.execute(
            f"SELECT salience, ({expr}) FROM short_term_memory WHERE id = %s", (stm_id,)
        )
        stored, eff = cur.fetchone()
        cur.execute("SELECT strength FROM long_term_memory WHERE id = %s", (anchor_id,))
        anchor_strength = cur.fetchone()[0]

    assert float(eff) < float(stored)        # STM episode decayed
    assert float(anchor_strength) == 0.9     # anchor untouched by any B operation

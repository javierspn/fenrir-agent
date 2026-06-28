"""US3 — versioned migrations apply once, in order, and re-apply is a no-op.

The fixture applies all migrations on a fresh DB; here we assert they were recorded,
the additive 0002 change is present, and a second migrate() changes nothing.
"""
from __future__ import annotations

from fenrir import db


def _applied(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT version FROM schema_migrations ORDER BY version")
        return [r[0] for r in cur.fetchall()]


def test_baseline_and_additive_recorded(migrated_conn):
    applied = _applied(migrated_conn)
    assert "0001" in applied
    assert "0002" in applied


def test_additive_migration_took_effect(migrated_conn):
    with migrated_conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_indexes WHERE indexname = 'ltm_domain'")
        assert cur.fetchone() is not None


def test_second_migrate_is_noop(migrated_conn):
    before = _applied(migrated_conn)
    newly = db.migrate()  # uses the same env wired by the fixture
    assert newly == []  # nothing re-applied
    assert _applied(migrated_conn) == before

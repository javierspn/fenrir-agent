"""Connection + in-house ordered-SQL migration applier (research R1).

Applies ``infra/migrations/NNNN_*.sql`` in lexical order, one transaction each,
recording applied versions in ``schema_migrations`` so a version never runs
twice. After migrating, sets the read-only ``grafana_ro`` role's password from
config (the role itself is created by the baseline migration; its password is
env-derived so it cannot live in static SQL). FR-004a, US3.

Run: ``python -m fenrir.db migrate``.
"""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg
from psycopg import sql

from fenrir.settings import get_settings

MIGRATIONS_DIR = Path("infra/migrations")
_TRACKER_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    name TEXT,
    applied_at TIMESTAMPTZ DEFAULT now()
)
"""


def connect() -> psycopg.Connection:
    return psycopg.connect(get_settings().db_dsn)


def _applied_versions(conn: psycopg.Connection) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(_TRACKER_DDL)
        cur.execute("SELECT version FROM schema_migrations")
        rows = cur.fetchall()
    conn.commit()
    return {r[0] for r in rows}


def _migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"))


def migrate(conn: psycopg.Connection | None = None) -> list[str]:
    """Apply pending migrations in order. Returns the versions newly applied."""
    own = conn is None
    conn = conn or connect()
    newly: list[str] = []
    try:
        done = _applied_versions(conn)
        for path in _migration_files():
            version = path.name.split("_", 1)[0]
            if version in done:
                continue
            ddl = path.read_text()
            with conn.cursor() as cur:
                cur.execute(ddl)  # one file = one transaction
                cur.execute(
                    "INSERT INTO schema_migrations (version, name) VALUES (%s, %s) "
                    "ON CONFLICT (version) DO NOTHING",
                    (version, path.name),
                )
            conn.commit()
            newly.append(version)
        _set_grafana_ro_password(conn)
    finally:
        if own:
            conn.close()
    return newly


def _set_grafana_ro_password(conn: psycopg.Connection) -> None:
    """Set the read-only datasource role's password from config (FR-004a).

    The role is created (NOLOGIN-safe, granted SELECT) by the baseline migration;
    here we attach LOGIN + the env-derived password. No-op if the role is absent
    (e.g. partial migrate)."""
    pw = get_settings().GRAFANA_DB_RO_PASSWORD
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = 'grafana_ro'")
        if cur.fetchone() is None:
            return
        cur.execute(
            sql.SQL("ALTER ROLE grafana_ro WITH LOGIN PASSWORD {}").format(
                sql.Literal(pw)
            )
        )
    conn.commit()


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv or argv[0] != "migrate":
        print("usage: python -m fenrir.db migrate")
        return 2
    applied = migrate()
    print(f"✓ migrations applied: {applied or 'none (up to date)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""SC-012 — grafana_ro can SELECT but every write/DDL through it is rejected."""
from __future__ import annotations

import psycopg
import pytest


def _ro_dsn(conn):
    info = conn.info
    return (
        f"host={info.host} port={info.port} dbname={info.dbname} "
        f"user=grafana_ro password=test-ro-pw"
    )


def test_grafana_ro_can_select(migrated_conn):
    with psycopg.connect(_ro_dsn(migrated_conn)) as ro, ro.cursor() as cur:
        cur.execute("SELECT count(*) FROM system_state")
        assert cur.fetchone()[0] >= 0


def test_grafana_ro_insert_rejected(migrated_conn):
    with psycopg.connect(_ro_dsn(migrated_conn)) as ro, ro.cursor() as cur:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("INSERT INTO system_state (key, value) VALUES ('x', 'y')")


def test_grafana_ro_ddl_rejected(migrated_conn):
    with psycopg.connect(_ro_dsn(migrated_conn)) as ro, ro.cursor() as cur:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("CREATE TABLE should_fail (x int)")

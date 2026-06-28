"""SC-001/SC-006 — stack comes up healthy; data survives `docker compose restart`.

Stack-level: needs the compose stack up (FENRIR_STACK_UP=1). Skipped otherwise.
"""
from __future__ import annotations

import subprocess  # noqa: S404 — fixed argv, no shell

import psycopg
import pytest

from tests.conftest import requires_stack, wait_for_pg

pytestmark = requires_stack

COMPOSE = ["docker", "compose", "-f", "infra/docker-compose.yml"]


def _owner_dsn():
    from fenrir.settings import get_settings

    return get_settings().db_dsn


@pytest.mark.timeout(180)
def test_data_survives_restart():
    marker = "restart-probe"
    with psycopg.connect(_owner_dsn()) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO system_state (key, value) VALUES (%s, 'v') "
            "ON CONFLICT (key) DO UPDATE SET value = 'v'",
            (marker,),
        )
        conn.commit()

    subprocess.run([*COMPOSE, "restart"], check=True)  # noqa: S603
    wait_for_pg(_owner_dsn())  # postgres needs a moment after restart

    with psycopg.connect(_owner_dsn()) as conn, conn.cursor() as cur:
        cur.execute("SELECT value FROM system_state WHERE key = %s", (marker,))
        row = cur.fetchone()
    assert row is not None and row[0] == "v"

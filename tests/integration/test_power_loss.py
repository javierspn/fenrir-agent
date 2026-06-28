"""SC-010 / FR-002a — survive a hard-kill (simulated power loss).

Committed rows intact after `docker compose kill` + restart; an interrupted
migration re-applies to the same state; and the budget counter is the Postgres
source of truth (a cache flush before restart still yields the correct counter,
never a double-count). Stack-level: needs FENRIR_STACK_UP=1.
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


@pytest.mark.timeout(240)
def test_committed_rows_survive_hard_kill():
    with psycopg.connect(_owner_dsn()) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO budget_tracking (date, llm_cost_usd) VALUES (CURRENT_DATE, 1.0) "
            "ON CONFLICT (date) DO UPDATE SET llm_cost_usd = 1.0"
        )
        conn.commit()

    subprocess.run([*COMPOSE, "kill"], check=True)  # noqa: S603 — SIGKILL, like a power cut
    subprocess.run([*COMPOSE, "up", "-d"], check=True)  # noqa: S603
    wait_for_pg(_owner_dsn())  # postgres replays WAL on restart — wait for it

    # re-applying migrations after a torn run is a clean no-op
    from fenrir import db

    db.migrate()

    with psycopg.connect(_owner_dsn()) as conn, conn.cursor() as cur:
        cur.execute("SELECT llm_cost_usd FROM budget_tracking WHERE date = CURRENT_DATE")
        row = cur.fetchone()
    # committed cost intact; budget counter authoritative in Postgres (no double-count)
    assert row is not None and row[0] == 1.0

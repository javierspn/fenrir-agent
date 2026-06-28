"""Shared test fixtures (plan Testing).

`migrated_conn` — a fresh pgvector Postgres (testcontainers) with the baseline
migration applied, wired so `fenrir.settings`/`fenrir.db` point at it. Used by
the schema/bootstrap/migration tests.

Stack-level tests (compose restart, power-loss, backup, grafana, models) need the
real docker-compose stack + Ollama; they are guarded by `requires_stack` /
`requires_ollama` and skip when those aren't present, so the suite stays green on
a bare CI runner.
"""
from __future__ import annotations

import os
import shutil
import time

import psycopg
import pytest


def wait_for_pg(dsn: str, tries: int = 30, delay: float = 2.0) -> None:
    """Block until Postgres accepts a connection (after a restart/kill it needs a
    moment). Raises the last OperationalError if it never comes up."""
    last: Exception | None = None
    for _ in range(tries):
        try:
            psycopg.connect(dsn).close()
            return
        except psycopg.OperationalError as exc:  # not ready yet
            last = exc
            time.sleep(delay)
    if last:
        raise last

_REQUIRED_ENV = {
    "DB_PASSWORD": "test-owner-pw",
    "GRAFANA_DB_RO_PASSWORD": "test-ro-pw",
    "GRAFANA_PASSWORD": "test-grafana-pw",
    "ANTHROPIC_API_KEY": "sk-ant-test",
    "OLLAMA_HOST": os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
    "OWNER_TELEGRAM_CHAT_ID": "0",
}


def _docker_available() -> bool:
    return shutil.which("docker") is not None


@pytest.fixture(scope="session")
def pg_container():
    if not _docker_available():
        pytest.skip("docker not available — skipping container-backed tests")
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer(
        "pgvector/pgvector:pg16", username="postgres", dbname="fenrir_core"
    ) as pg:
        yield pg


@pytest.fixture()
def migrated_conn(pg_container, monkeypatch):
    """Fresh DB env + baseline migration applied; yields an open connection."""
    for key, val in _REQUIRED_ENV.items():
        monkeypatch.setenv(key, val)
    monkeypatch.setenv("DB_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("DB_PORT", str(pg_container.get_exposed_port(5432)))
    monkeypatch.setenv("DB_NAME", "fenrir_core")
    monkeypatch.setenv("DB_USER", "postgres")
    monkeypatch.setenv("DB_PASSWORD", pg_container.password)

    from fenrir import db
    from fenrir.settings import get_settings

    get_settings.cache_clear()
    # Isolate each test: the Postgres container is session-scoped and reused, so
    # reset the schema before migrating (else seeded rows / the bootstrap marker leak).
    reset = psycopg.connect(get_settings().db_dsn)
    with reset.cursor() as cur:
        cur.execute("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;")
    reset.commit()
    reset.close()
    db.migrate()

    conn = psycopg.connect(get_settings().db_dsn)
    try:
        yield conn
    finally:
        conn.close()
        get_settings.cache_clear()


# --- guards for stack-level tests --------------------------------------------
requires_stack = pytest.mark.skipif(
    os.environ.get("FENRIR_STACK_UP") != "1",
    reason="needs the docker-compose stack up (set FENRIR_STACK_UP=1)",
)
requires_ollama = pytest.mark.skipif(
    os.environ.get("FENRIR_OLLAMA_UP") != "1",
    reason="needs a reachable Ollama with models pulled (set FENRIR_OLLAMA_UP=1)",
)

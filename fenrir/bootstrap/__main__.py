"""`python -m fenrir.bootstrap` — idempotent bootstrap (contracts/bootstrap.contract.md).

Sequence: marker-gated global guard -> models -> anchors -> relations -> benchmarks
-> marker. The global guard keys on the system_state('bootstrapped') marker (set
ONLY at the final step), NOT on a row count — a run interrupted before completion
has no marker and resumes via per-section idempotency (FR-012/017/018). Any failure
before the final step leaves the system un-bootstrapped so a retry completes it.
"""
from __future__ import annotations

import psycopg

from fenrir import db
from fenrir.bootstrap.anchors import seed_anchors
from fenrir.bootstrap.models import ensure_models
from fenrir.bootstrap.relations import seed_relations
from fenrir.settings import get_settings

MARKER = "bootstrapped"


def is_bootstrapped(conn: psycopg.Connection) -> bool:
    """Authoritative completion signal — the marker, never a row count (FR-017)."""
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM system_state WHERE key = %s", (MARKER,))
        return cur.fetchone() is not None


def mark_bootstrapped(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO system_state (key, value, updated_at) VALUES (%s, now()::text, now()) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = now()",
            (MARKER,),
        )
    conn.commit()


def run(conn: psycopg.Connection | None = None, *, load_benchmarks: bool = True) -> int:
    own = conn is None
    conn = conn or db.connect()
    try:
        if is_bootstrapped(conn):
            print("already bootstrapped — no changes")
            return 0

        settings = get_settings()
        ensure_models(settings.OLLAMA_HOST)          # FR-013
        n_anchors = seed_anchors(conn)               # FR-014
        n_rel = seed_relations(conn)                 # FR-015
        if load_benchmarks:
            from benchmark_loader.load import load_and_partition

            pools = load_and_partition(conn)         # FR-016
            print(f"benchmarks: {pools}")

        mark_bootstrapped(conn)                       # FR-017 — only after all sections succeed
        print(f"✓ bootstrapped: {n_anchors} anchors, {n_rel} relations")
        return 0
    finally:
        if own:
            conn.close()


if __name__ == "__main__":
    raise SystemExit(run())

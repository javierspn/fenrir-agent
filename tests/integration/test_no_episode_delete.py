"""SC-007 — no cascade path hard-deletes a source episode; no graph-DB service."""
from __future__ import annotations

from pathlib import Path

import yaml


def test_no_on_delete_cascade_toward_short_term_memory(migrated_conn):
    # Any FK whose referenced table is short_term_memory must NOT be ON DELETE CASCADE (D1).
    with migrated_conn.cursor() as cur:
        cur.execute(
            """
            SELECT con.conname, con.confdeltype
            FROM pg_constraint con
            JOIN pg_class ref ON ref.oid = con.confrelid
            WHERE con.contype = 'f' AND ref.relname = 'short_term_memory'
            """
        )
        offenders = [name for name, deltype in cur.fetchall() if deltype == "c"]  # 'c' = CASCADE
    assert offenders == [], f"cascade FKs toward episodes: {offenders}"


def test_compose_has_no_graph_db_service():
    # Check the actual service list (not a substring — comments mention "no neo4j").
    compose = yaml.safe_load(Path("infra/docker-compose.yml").read_text())
    services = compose.get("services", {})
    assert "neo4j" not in services
    for svc in services.values():
        assert "neo4j" not in str(svc.get("image", "")).lower()

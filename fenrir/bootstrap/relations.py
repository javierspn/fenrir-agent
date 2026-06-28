"""Seed ≥20 obvious starting relations among anchors (FR-015).

Written to graph_updates with trigger='bootstrap_seed' (NO graph DB). Endpoints
are given as anchor natural keys and resolved to long_term_memory.id at seed time;
idempotent via the (from_node, relation_type, to_node) unique constraint.
"""
from __future__ import annotations

from pathlib import Path

import psycopg
import yaml

DEFAULT_SEED = Path("infra/seeds/relations_seed.yaml")


def seed_relations(conn: psycopg.Connection, path: Path = DEFAULT_SEED) -> int:
    """Insert seed relations. Returns count of bootstrap_seed rows after."""
    relations = yaml.safe_load(path.read_text())["relations"]
    with conn.cursor() as cur:
        cur.execute("SELECT natural_key, id FROM long_term_memory WHERE natural_key IS NOT NULL")
        key_to_id = dict(cur.fetchall())
        for r in relations:
            frm = key_to_id.get(r["from"])
            to = key_to_id.get(r["to"])
            if frm is None or to is None:
                continue  # endpoint not seeded — skip rather than orphan
            cur.execute(
                "INSERT INTO graph_updates "
                "(trigger, from_node, relation_type, to_node, confidence) "
                "VALUES ('bootstrap_seed', %s, %s, %s, 1.0) "
                "ON CONFLICT (from_node, relation_type, to_node) DO NOTHING",
                (frm, r["type"], to),
            )
    conn.commit()
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM graph_updates WHERE trigger = 'bootstrap_seed'")
        return cur.fetchone()[0]

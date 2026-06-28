"""Seed 50–100 invariant math anchors (FR-014).

is_anchor=TRUE, strength=1.0, decay_rate=0, memory_type='semantic',
domain='mathematics'. Idempotent via the natural_key unique constraint.
"""
from __future__ import annotations

from pathlib import Path

import psycopg
import yaml

DEFAULT_SEED = Path("infra/seeds/anchors_math.yaml")


def seed_anchors(conn: psycopg.Connection, path: Path = DEFAULT_SEED) -> int:
    """Insert anchors (ON CONFLICT DO NOTHING). Returns total anchor count after."""
    anchors = yaml.safe_load(path.read_text())["anchors"]
    with conn.cursor() as cur:
        for a in anchors:
            cur.execute(
                "INSERT INTO long_term_memory "
                "(content, memory_type, domain, strength, decay_rate, is_anchor, natural_key) "
                "VALUES (%s, 'semantic', 'mathematics', 1.0, 0, TRUE, %s) "
                "ON CONFLICT (natural_key) DO NOTHING",
                (a["content"], a["key"]),
            )
    conn.commit()
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM long_term_memory WHERE is_anchor")
        return cur.fetchone()[0]

"""Significance bookmark (002 T014; 003 increment A — significance.contract).

THE single definition of significance:

    salience = prediction_error × value × (retrieval_count + 1)
               [surprise]        [worth]   [use]

Product form — a zero in any factor drops salience to the floor (the brain's
selective tagging, research R6). The three factors stay orthogonal and individually
inspectable (FR-004): ``prediction_error`` = surprise, ``value`` = worth (stored in the
``importance`` column), ``retrieval_count`` = use.

``value()`` is the live reward-magnitude bookmark computed at write time from outcomes
the loop already holds (verdict, escalated, crystallized) — it is NOT the inert 1.0 the
loop used to default (003 fixes that). ``recompute()`` and ``bump_retrieval_count()`` both
CALL ``salience()`` so there is exactly one definition across every call site (SC-001) —
this removes the prior divergent SQL formulas (the 1.0-vs-0.5 default drift and the
retrieval_count off-by-one).
"""
from __future__ import annotations

import math
from datetime import datetime

import psycopg

from fenrir.settings import get_settings
from fenrir.verify.sympy_oracle import FAILED, SUCCEEDED, UNVERIFIED

_LN2 = math.log(2)


def value(verdict: str, *, escalated: bool, crystallized: bool) -> float:
    """Reward-magnitude bookmark, computed at write time (significance.contract).

        value = base(verdict) × (W_ESCALATED if escalated) × (W_CRYSTALLIZED if crystallized)
        base(SUCCEEDED)=1.0, base(FAILED)=W_FAIL, base(UNVERIFIED)=W_UNVERIFIED

    Ordering (SC-002): skill-yielding ≥ teacher-taught ≥ from-scratch, all > failed ≥ unverified.
    Never the constant 1.0 across outcomes — that was the standing bug.
    """
    s = get_settings()
    bases = {SUCCEEDED: 1.0, FAILED: s.W_FAIL, UNVERIFIED: s.W_UNVERIFIED}
    score = bases.get(verdict, s.W_UNVERIFIED)
    if escalated:
        score *= s.W_ESCALATED
    if crystallized:
        score *= s.W_CRYSTALLIZED
    return float(score)


def salience(prediction_error: float, importance: float, retrieval_count: int) -> float:
    """Product-form salience — THE single definition. retrieval_count is treated as
    (count + 1) so a never-retrieved-but-surprising episode still has non-zero salience."""
    return float(prediction_error) * float(importance) * float(retrieval_count + 1)


def effective_salience(
    salience: float,
    last_reactivated_at: datetime | None,
    created_at: datetime,
    *,
    now: datetime,
) -> float:
    """Read-time decayed significance (003 increment B — decay.contract).

        effective = salience × exp(-ln2 · age_days / DECAY_HALFLIFE_DAYS)
        age_days  = (now − COALESCE(last_reactivated_at, created_at)) in fractional days

    Pure function — NEVER mutates the stored salience (additive guarantee, VI). NULL
    last_reactivated_at falls back to created_at (no backfill needed). Monotonic in age;
    equals salience at age 0; halves every DECAY_HALFLIFE_DAYS. The SQL form in
    effective_salience_sql() mirrors this exactly.
    """
    ref = last_reactivated_at or created_at
    age_days = (now - ref).total_seconds() / 86400.0
    half_life = get_settings().DECAY_HALFLIFE_DAYS
    return float(salience) * math.exp(-_LN2 * age_days / half_life)


def effective_salience_sql(
    salience_expr: str = "salience", *, half_life_days: float | None = None
) -> str:
    """SQL fragment that mirrors effective_salience() exactly, for use in consolidation
    candidate ranking and the dashboard decay panel. Pass a literal half-life for static
    dashboard SQL; defaults to the configured DECAY_HALFLIFE_DAYS."""
    hl = half_life_days if half_life_days is not None else get_settings().DECAY_HALFLIFE_DAYS
    return (
        f"{salience_expr} * exp(-ln(2) * "
        "extract(epoch from (now() - coalesce(last_reactivated_at, created_at))) "
        f"/ (86400 * {hl}))"
    )


def reactivate(conn: psycopg.Connection, episode_ids: list[str]) -> None:
    """Reset the decay clock for episodes that were re-accessed or won a replay
    (FR-009, reversible forgetting): last_reactivated_at = now(). Additive — no other
    column is touched, stored salience is unchanged."""
    if not episode_ids:
        return
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE short_term_memory SET last_reactivated_at = now() WHERE id = ANY(%s)",
            (episode_ids,),
        )
    conn.commit()


def recompute(conn: psycopg.Connection, episode_id: str) -> None:
    """Recompute and persist salience for one short_term_memory row via salience() —
    no inline SQL arithmetic, so this never diverges from the Python definition (SC-001)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT prediction_error, importance, retrieval_count "
            "FROM short_term_memory WHERE id = %s",
            (episode_id,),
        )
        row = cur.fetchone()
        if row is None:
            return
        pe, importance, rc = row
        sal = salience(pe or 0.0, importance if importance is not None else 0.0, rc or 0)
        cur.execute(
            "UPDATE short_term_memory SET salience = %s WHERE id = %s",
            (sal, episode_id),
        )
    conn.commit()


def bump_retrieval_count(conn: psycopg.Connection, episode_ids: list[str]) -> None:
    """Increment retrieval_count on surfaced episodes and recompute salience via salience()
    (FR-018). Increment-then-recompute uses the post-bump count exactly once — no off-by-one."""
    if not episode_ids:
        return
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE short_term_memory SET retrieval_count = retrieval_count + 1 "
            "WHERE id = ANY(%s) RETURNING id, prediction_error, importance, retrieval_count",
            (episode_ids,),
        )
        rows = cur.fetchall()
        for eid, pe, importance, rc in rows:
            sal = salience(pe or 0.0, importance if importance is not None else 0.0, rc or 0)
            cur.execute(
                "UPDATE short_term_memory SET salience = %s WHERE id = %s",
                (sal, eid),
            )
    conn.commit()

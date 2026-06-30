"""Feasibility-gated, skill-adjacency-biased task selection (004).

Replaces the uniform-random training draw with a curriculum that prefers tasks
*adjacent* to an existing skill — close enough that a stored skill could be
retrieved and reused, far enough that the attempt still exercises learning — and
never proposes a task the current loadout makes infeasible. Two lanes:

  * **adjacency lane** (`force_external=False`): rank unsolved training candidates
    by their max cosine to the current skill loadout, keep only the *adjacent* band
    [ADJACENCY_FEASIBILITY_FLOOR, ADJACENCY_TRIVIAL_CEIL), pick with ADJACENCY_STRENGTH.
  * **external lane** (`force_external=True`): the preserved uniform-random training
    draw — the forced ≥30% diversity mix, the cold-start path, and the exhaustion fallback.

Reads ONLY `skills` + `benchmark_tasks` — never the learner's reasoning, prediction, or
the judge's output (Constitution VIII, separation of powers) — and makes **zero LLM/proxy
calls** (the budget hard cap is respected by construction, IX). The selection objective is
a pure function of (feasibility band, cosine-to-loadout, used_count tiebreak): there is **no**
novelty / diversity / distance-from-seen term (rejects Voyager's objective; FR-006, §10.1).

Contract: contracts/selection.contract.md
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

import psycopg

from fenrir.core import BenchTask
from fenrir.settings import get_settings

# Sharpening constant for the intermediate-strength weighted sample. Tuned so the knob bites
# across the *narrow* adjacent cosine band [0.80, 0.92): only shapes the 0<strength<1 regime;
# the endpoints (uniform / argmax) are handled explicitly.
_SHARP = 40.0


@dataclass
class Selection:
    task: BenchTask
    selected_via: str            # 'adjacency' | 'external' | 'fallback'
    adjacent_skill_id: str | None


# ---------------------------------------------------------------------------
# pure policy helpers (unit-tested, no DB)
# ---------------------------------------------------------------------------
def classify(cosine: float, floor: float, ceil: float) -> str:
    """Adjacency band of a candidate's max-skill cosine (selection.contract C2, R2)."""
    if cosine < floor:
        return "infeasible"
    if cosine < ceil:
        return "adjacent"
    return "trivial"


def pick_index(cosines: list[float], strength: float, rng: random.Random) -> int:
    """Choose an index into ``cosines`` (assumed sorted desc, ties pre-broken by the caller).

    ``strength`` 0 → uniform (pure feasibility filter); 1 → argmax cosine; intermediate →
    cosine-sharpened weighted sample, monotone in cosine (selection.contract C3, R4). The
    objective depends ONLY on cosine + strength — no novelty term (FR-006).
    """
    if not cosines:
        raise ValueError("pick_index on empty candidate list")
    if strength >= 1.0:
        return max(range(len(cosines)), key=lambda i: cosines[i])
    if strength <= 0.0:
        return rng.randrange(len(cosines))
    weights = [c ** (1.0 + _SHARP * strength) for c in cosines]
    total = sum(weights)
    if total <= 0.0:
        return rng.randrange(len(cosines))
    r = rng.random() * total
    acc = 0.0
    for i, w in enumerate(weights):
        acc += w
        if r <= acc:
            return i
    return len(cosines) - 1


def external_slot_plan(n: int, fraction: float) -> list[bool]:
    """Deterministic per-cohort external-slot plan: at least ``ceil(fraction·n)`` of the ``n``
    slots are external, evenly spread (selection.contract C4, FR-004). Met by construction —
    not in expectation — so ≥30% holds on 100% of cohorts incl. small ``n``.
    """
    if n <= 0:
        return []
    k = min(n, math.ceil(fraction * n))
    plan = [False] * n
    # floor(i·n/k) is strictly increasing for i in 0..k-1 when n>=k, so exactly k distinct Trues.
    for i in range(k):
        plan[(i * n) // k] = True
    return plan


# ---------------------------------------------------------------------------
# lanes (DB)
# ---------------------------------------------------------------------------
def _adjacent_candidates(conn: psycopg.Connection, *, limit: int = 64) -> list[tuple]:
    """Unsolved training tasks in the *adjacent* band, ordered (cosine desc, used_count asc).

    Each row: (id, problem_id, content, ground_truth, domain, best_cosine, best_skill_id).
    Reads only benchmark_tasks (pool='training', embedded) × the stable/testing skill loadout.
    Returns [] on cold start / exhaustion so the caller can fall back (C5).
    """
    s = get_settings()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT b.id, b.problem_id, b.content, b.ground_truth, b.domain, "
            "       max(1 - (b.embedding <=> s.embedding)) AS best_cosine, "
            "       (array_agg(s.id ORDER BY b.embedding <=> s.embedding))[1] AS best_skill_id "
            "FROM benchmark_tasks b "
            "JOIN skills s ON s.state IN ('stable','testing') AND s.embedding IS NOT NULL "
            "WHERE b.pool = 'training' "                          # NEVER evaluation (III)
            "  AND b.embedding IS NOT NULL "
            "  AND NOT EXISTS (SELECT 1 FROM tasks t "
            "                  WHERE t.benchmark_id = b.problem_id AND t.status = 'succeeded') "
            "GROUP BY b.id, b.problem_id, b.content, b.ground_truth, b.domain, b.used_count "
            "HAVING max(1 - (b.embedding <=> s.embedding)) >= %s "
            "   AND max(1 - (b.embedding <=> s.embedding)) <  %s "
            "ORDER BY best_cosine DESC, b.used_count ASC "
            "LIMIT %s",
            (s.ADJACENCY_FEASIBILITY_FLOOR, s.ADJACENCY_TRIVIAL_CEIL, limit),
        )
        return cur.fetchall()


def _external_draw(conn: psycopg.Connection) -> BenchTask | None:
    """The preserved uniform-random training draw: unsolved, under-practiced first, then random.
    Training pool only (III) — the breadth/diversity guard, cold-start, and fallback lane.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT b.id, b.problem_id, b.content, b.ground_truth, b.domain "
            "FROM benchmark_tasks b "
            "WHERE b.pool = 'training' "                          # NEVER evaluation (III)
            "  AND NOT EXISTS (SELECT 1 FROM tasks t "
            "                  WHERE t.benchmark_id = b.problem_id AND t.status = 'succeeded') "
            "ORDER BY (SELECT count(*) FROM tasks t2 WHERE t2.benchmark_id = b.problem_id) ASC, "
            "         random() LIMIT 1"
        )
        row = cur.fetchone()
    if not row:
        return None
    return BenchTask(str(row[0]), row[1], row[2], row[3], row[4] or "math")


def select(conn: psycopg.Connection, *, force_external: bool,
           seed: int | None = None) -> Selection | None:
    """Pick the next training task. See module docstring + contract for the two lanes."""
    rng = random.Random(seed)
    if not force_external:
        cands = _adjacent_candidates(conn)
        if cands:
            idx = pick_index([float(c[5]) for c in cands], get_settings().ADJACENCY_STRENGTH, rng)
            r = cands[idx]
            bt = BenchTask(str(r[0]), r[1], r[2], r[3], r[4] or "math")
            return Selection(bt, "adjacency", str(r[6]) if r[6] is not None else None)
        # cold start / adjacency exhausted → fall back to the external lane (C5)
        fb = _external_draw(conn)
        return Selection(fb, "fallback", None) if fb is not None else None
    ext = _external_draw(conn)
    return Selection(ext, "external", None) if ext is not None else None

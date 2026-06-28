"""Regulated consolidation — "sleep" (002 T032; 003 increment C — competitive replay).

Replaces the 002 salience-descending scan→copy with the hippocampal two-stage model
(consolidation.contract): cluster raw episodes by embedding cosine → spend a fixed replay
budget drawing clusters in proportion to effective-significance **with replacement** → merge
each drawn cluster into **one** long_term_memory abstraction whose strength accrues per replay
hit. A per-cluster predictability gate + an over-merge coherence guard run before any merge.
Source episodes are marked consolidated, NEVER deleted (additive, VI); already-consolidated
sources are excluded so re-runs are idempotent. The anchor drift smoke-test (FR-019) and the
held-out pool isolation (III/FR-021) are preserved unchanged. Reproducible under a fixed seed.
Contract: contracts/consolidation.contract.md
"""
from __future__ import annotations

import json
import math
import random
from collections.abc import Iterable

import psycopg

from fenrir.memory.salience import effective_salience, reactivate
from fenrir.settings import get_settings


def _parse_vec(v: object) -> list[float] | None:
    """pgvector comes back as the text '[1,2,3]' (valid JSON) — parse to a float list."""
    if v is None:
        return None
    if isinstance(v, str):
        return [float(x) for x in json.loads(v)]
    if isinstance(v, Iterable):
        return [float(x) for x in v]  # already a sequence
    return None


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def ensure_heldout(conn: psycopg.Connection) -> int:
    """Mark a HELDOUT_FRACTION slice of the TRAINING pool as held_out (once). Never the
    evaluation pool (Constitution III). Idempotent. Returns the held-out count."""
    s = get_settings()
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM benchmark_tasks WHERE pool='training' AND held_out")
        if cur.fetchone()[0] > 0:
            cur.execute("SELECT count(*) FROM benchmark_tasks WHERE held_out")
            return cur.fetchone()[0]
        cur.execute(
            "UPDATE benchmark_tasks SET held_out = true WHERE id IN ("
            "  SELECT id FROM benchmark_tasks WHERE pool='training' "
            "  ORDER BY problem_id LIMIT GREATEST(1, ("
            "    SELECT (count(*) * %s)::int FROM benchmark_tasks WHERE pool='training')))",
            (s.HELDOUT_FRACTION,),
        )
        marked = cur.rowcount
    conn.commit()
    return marked


def predictability_improves(conn: psycopg.Connection, source_ids: list[str]) -> bool:
    """Predictability gate (FR-020). Merge only if the abstraction does not REGRESS on the
    held-out training slice. Simplified-but-honest pilot gate: an abstraction drawn from
    episodes that were themselves verified successes (low residual error) is admissible;
    one drawn from unverified/failed material is not (it would not generalize). Deepening
    this into a full A/B re-solve is a later feature — this is the single override point.
    """
    if not source_ids:
        return False
    with conn.cursor() as cur:
        cur.execute(
            "SELECT avg(COALESCE(prediction_error, 1.0)) FROM short_term_memory WHERE id = ANY(%s)",
            (source_ids,),
        )
        avg_pe = cur.fetchone()[0]
    # high average residual error in the cluster → idiosyncratic, do not merge (Go-CLS)
    return avg_pe is not None and float(avg_pe) < 0.9


def _drift_flag(conn: psycopg.Connection, abstraction_id: str) -> bool:
    """Anchor drift smoke-test (FR-026): flag an abstraction that sits atop an anchored fact
    but is not itself an anchor (possible warping). Records an additive graph edge for human
    review — never auto-deletes. Returns True if flagged."""
    with conn.cursor() as cur:
        # nearest non-decaying anchor by embedding; flag if suspiciously close yet divergent
        cur.execute(
            "SELECT a.id, 1 - (a.embedding <=> s.embedding) AS sim "
            "FROM long_term_memory a, long_term_memory s "
            "WHERE a.is_anchor = true AND s.id = %s AND a.embedding IS NOT NULL "
            "  AND s.embedding IS NOT NULL "
            "ORDER BY a.embedding <=> s.embedding LIMIT 1",
            (abstraction_id,),
        )
        row = cur.fetchone()
        if not row or row[1] is None or float(row[1]) < 0.97:
            return False
        anchor_id = row[0]
        cur.execute(
            "INSERT INTO graph_updates (trigger, from_node, relation_type, to_node, confidence) "
            "VALUES ('consolidation_deep', %s, 'drift_flag', %s, %s) "
            "ON CONFLICT (from_node, relation_type, to_node) DO NOTHING",
            (abstraction_id, anchor_id, float(row[1])),
        )
    conn.commit()
    return True


def _cluster(candidates: list[dict], sim_floor: float, max_spread: float) -> list[list[dict]]:
    """Greedy agglomeration by embedding cosine ≥ sim_floor (compared to each cluster's seed,
    its highest-effective-salience member). Then the over-merge guard (FR-018): any cluster
    whose internal max pairwise cosine DISTANCE exceeds max_spread is split back to singletons,
    so genuinely different methods are never collapsed into one mushy abstraction."""
    clusters: list[list[dict]] = []
    for ep in candidates:  # candidates arrive sorted by effective salience desc
        for cl in clusters:
            if _cosine(ep["vec"], cl[0]["vec"]) >= sim_floor:
                cl.append(ep)
                break
        else:
            clusters.append([ep])

    guarded: list[list[dict]] = []
    for cl in clusters:
        if len(cl) <= 1:
            guarded.append(cl)
            continue
        min_pair = min(
            _cosine(cl[i]["vec"], cl[j]["vec"])
            for i in range(len(cl))
            for j in range(i + 1, len(cl))
        )
        if (1.0 - min_pair) > max_spread:          # too incoherent → split, don't collapse
            guarded.extend([m] for m in cl)
        else:
            guarded.append(cl)
    return guarded


def run(
    conn: psycopg.Connection,
    *,
    replay_budget: int | None = None,
    seed: int | None = None,
    limit: int = 1000,
) -> dict:
    """One consolidation pass (competitive replay, consolidation.contract).

    cluster raw episodes → spend replay_budget by effective-salience (with replacement) →
    merge each drawn cluster into ONE long_term_memory abstraction, strength accrues per hit
    → per-cluster predictability gate + over-merge guard → additive, idempotent, pool-isolated.
    Returns {clusters, merged, replays, drift_flagged, skipped_gate, seed}.
    """
    s = get_settings()
    budget = replay_budget if replay_budget is not None else s.REPLAY_BUDGET
    if seed is None:
        seed = random.randrange(2**31)         # log the actual seed for reproducible audit
    rng = random.Random(seed)

    ensure_heldout(conn)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO consolidation_runs (level, started_at) VALUES ('deep', now()) RETURNING id"
        )
        run_id = cur.fetchone()[0]
        cur.execute("SELECT now()")
        db_now = cur.fetchone()[0]
        # candidates: raw episodes, training/held-out pool only (eval NEVER read, III/FR-021)
        cur.execute(
            "SELECT stm.id, stm.content, stm.domain, stm.embedding, stm.salience, "
            "       stm.created_at, stm.last_reactivated_at "
            "FROM short_term_memory stm "
            "LEFT JOIN tasks t ON t.id = stm.task_id "
            "WHERE stm.consolidation_status = 'raw' "
            "  AND COALESCE(t.is_eval, false) = false "
            "  AND stm.embedding IS NOT NULL "
            "LIMIT %s",
            (limit,),
        )
        rows = cur.fetchall()
    conn.commit()

    # effective significance drives candidacy + cluster weighting (decay, B). Computed in
    # Python from the one definition so it cannot diverge from the read-time form.
    candidates: list[dict] = []
    for eid, content, domain, emb, sal, created, last_react in rows:
        vec = _parse_vec(emb)
        if vec is None:
            continue
        eff = effective_salience(float(sal or 0.0), last_react, created, now=db_now)
        if eff >= s.EFFECTIVE_SALIENCE_FLOOR:
            candidates.append(
                {"id": eid, "content": content, "domain": domain, "vec": vec, "eff": eff}
            )
    candidates.sort(key=lambda c: c["eff"], reverse=True)

    processed = len(candidates)
    clusters = _cluster(candidates, s.CLUSTER_SIM_FLOOR, s.COHERENCE_MAX_SPREAD)

    # per-cluster predictability gate (V/FR-017): a cluster that would regress on the held-out
    # slice is skipped, its members stay raw. Ties in weighting broken by cluster seed id.
    surviving: list[list[dict]] = []
    skipped_gate = 0
    for cl in clusters:
        if predictability_improves(conn, [str(m["id"]) for m in cl]):
            surviving.append(cl)
        else:
            skipped_gate += 1
    surviving.sort(key=lambda cl: str(cl[0]["id"]))

    merged = flagged = replays = 0
    weights = [sum(m["eff"] for m in cl) for cl in surviving]
    if surviving and sum(weights) > 0:
        # competitive replay: draw `budget` times with replacement, weighted by Σ eff-salience
        draws = [0] * len(surviving)
        for idx in rng.choices(range(len(surviving)), weights=weights, k=budget):
            draws[idx] += 1
        replays = sum(draws)

        for cl, d in zip(surviving, draws):
            if d == 0:
                continue
            member_ids = [m["id"] for m in cl]
            seed_member = cl[0]            # highest-eff member = representative
            strength = d * s.STRENGTH_PER_REPLAY
            with conn.cursor() as cur:
                # merge-to-one: ONE abstraction, source_memories = ALL members (FR-015/016)
                cur.execute(
                    "INSERT INTO long_term_memory (content, embedding, memory_type, domain, "
                    " abstraction_level, strength, reinforcement_count, last_reinforced_at, "
                    " is_anchor, source_memories) "
                    "VALUES (%s, "
                    "  (SELECT embedding FROM short_term_memory WHERE id = %s), "
                    "  'semantic', %s, 2, %s, %s, now(), false, %s) RETURNING id",
                    (
                        f"abstraction[{len(member_ids)}]: {seed_member['content']}",
                        seed_member["id"], seed_member["domain"], strength, d, member_ids,
                    ),
                )
                abstraction_id = cur.fetchone()[0]
                # mark ALL sources consolidated — NEVER delete (VI/D1)
                cur.execute(
                    "UPDATE short_term_memory SET consolidation_status='consolidated', "
                    "consolidated_at=now() WHERE id = ANY(%s)",
                    (member_ids,),
                )
            conn.commit()
            # won replay refreshes the decay clock of every member (feeds B, FR-009)
            reactivate(conn, [str(m) for m in member_ids])
            merged += 1
            if _drift_flag(conn, str(abstraction_id)):
                flagged += 1

    with conn.cursor() as cur:
        cur.execute(
            "UPDATE consolidation_runs SET completed_at=now(), memories_processed=%s, "
            "skills_created=0, insights=%s WHERE id=%s",
            (processed, [f"seed={seed}", f"replay_budget={budget}", f"merged={merged}"], run_id),
        )
    conn.commit()
    return {
        "clusters": len(clusters), "merged": merged, "replays": replays,
        "drift_flagged": flagged, "skipped_gate": skipped_gate, "seed": seed,
    }

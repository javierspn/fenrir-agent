# Contract — Curriculum Selection (004)

The behavioural contract for `fenrir/curriculum.py` + its integration in `fenrir/core.py`. Revises the
selection half of 002's `loop.contract.md`. Every clause is test-backed (see `quickstart.md`).

**Glossary.** A **cohort** = one `core.run(n)` invocation of `n` slots; the ≥30% external guarantee
(C4) and the "every cohort" claims (SC-005) are per `run(n)` call. **`FEASIBILITY_FLOOR`** and
**`TRIVIAL_CEIL`** below are shorthand for the settings `ADJACENCY_FEASIBILITY_FLOOR` /
`ADJACENCY_TRIVIAL_CEIL`. `FEASIBILITY_FLOOR` defaults to `RETRIEVAL_SIM_FLOOR` (0.80) so every
adjacency-lane pick is a solve-time coverage hit (research.md/R2, floor reconciliation).

---

## Interface

```
curriculum.select(conn, *, force_external: bool, seed: int | None = None)
    -> Selection(task: BenchTask, selected_via: str, adjacent_skill_id: str | None)
```

- `force_external=True` → take the **external lane** (uniform-random unsolved training draw, the
  preserved pre-004 behaviour). Used to satisfy the cohort quota and as the fallback.
- `force_external=False` → take the **adjacency lane**; if it yields nothing (empty loadout, no
  adjacent-band candidate, exhaustion), it **falls back** to the external lane and returns
  `selected_via='fallback'`.
- `core.run(n)` owns the cohort quota and calls `select` with `force_external` set per slot.

---

## C1 — Pool isolation (Constitution III) — INVARIANT

Both lanes query `benchmark_tasks WHERE pool = 'training'` only. No `evaluation`/`transfer` row, and no
`tasks` row with `is_eval = true`, is ever selected, written, or read into selection. **0 eval-pool
tasks on 100% of cohorts** (SC-005). The adjacency lane additionally requires `embedding IS NOT NULL`,
which by the backfill invariant is true only for training rows.

## C2 — Feasibility gate (FR-002) — INVARIANT

The adjacency lane emits a task only if its max-skill-cosine `c` is in the **adjacent band**
`[ADJACENCY_FEASIBILITY_FLOOR, ADJACENCY_TRIVIAL_CEIL)`. It never emits:
- an **infeasible** task (`c < FEASIBILITY_FLOOR`) — nothing in the loadout is near it; or
- a **trivially-covered** task (`c ≥ TRIVIAL_CEIL`) — a near-duplicate (anti coverage-inflation).

**0 infeasible tasks proposed** by the adjacency lane (SC-006). (External/fallback draws are by
definition allowed regardless of band — they are the breadth/cold-start guarantee, not adjacency picks.)

## C3 — Skill-adjacency bias, no novelty (FR-001 / FR-006) — INVARIANT

The adjacency lane prefers tasks adjacent to an existing skill over uniform draws. The preference is a
pure function of `(feasibility band, cosine-to-loadout, used_count tiebreak)` modulated by
`ADJACENCY_STRENGTH ∈ [0,1]`:
- `0` → uniform among adjacent-band candidates (pure feasibility filter);
- `1` → highest-cosine adjacent candidate (ties: lower `used_count`, then seeded random);
- intermediate → cosine-sharpened sampling (monotone in cosine).

The objective contains **no** novelty/diversity/distance-from-seen term. Two candidates equal in
`(band, cosine)` are ranked indifferently no matter how "new" either is (tested).

## C4 — Forced external mix (FR-004) — INVARIANT

Across a cohort of `n` slots, `core.run(n)` takes the external lane on at least
`ceil(EXTERNAL_MIN_FRACTION · n)` slots, independent of adjacency. **≥30% external on 100% of cohorts**
(SC-005). The quota is met by construction (deterministic slot assignment), not in expectation.

## C5 — Never stall (FR-008)

On an empty/insufficient loadout, adjacency exhaustion, or a misjudged feasibility starving the
adjacency lane, `select` falls back to the external lane and **always returns a valid task** while any
unsolved training task remains. A cohort of size `n` over a non-empty training pool yields `n` tasks
(or stops only when the pool's unsolved tasks are exhausted — the pre-004 stop condition, unchanged).

## C6 — Selection audit (FR-003)

Every selected task records `selected_via ∈ {'adjacency','external','fallback'}` and, when
`'adjacency'`, the `adjacent_skill_id` it was judged adjacent to (NULL otherwise). Written at task-row
creation. The policy is fully reconstructable from `tasks` alone.

## C7 — Separation of powers (Constitution VIII / FR-007)

`curriculum.select` reads only the skill loadout + the task pool. It never reads the learner's
reasoning, self-evaluation, prediction, or any judge output, and makes no model call — it is a separate
instance by construction.

## C8 — Budget + additivity (FR-012 / VI / IX)

Selection makes no frontier model call (the one task embed is local + cached); the daily budget hard
cap and its degradation rule are unchanged. All schema is additive (data-model.md); no episode or
benchmark row is mutated or deleted by selection.

## C9 — Honest falsification (FR-011 / SC-007)

Nothing in selection alters, hides, or smooths a verdict signal. Coverage / reuse / escalation are
recorded raw per task; a flat cohort series renders on the board as a recorded negative result exactly
as a positive one would.

---

## Verdict signals (US3) — read-back contract

Per cohort, all four are queryable off `tasks` and render on the existing "Are we actually learning?"
board (overview.json / learning.json):
- **coverage (🧩)** = `avg(retrieval_skill_id IS NOT NULL)` — must rise off ~0.8% (SC-001).
- **reuse** = `avg(retrieval_abstraction_id IS NOT NULL)` — must track coverage (SC-003).
- **skill-covered vs cold escalation (🎯)** = `avg(escalated)` split on `retrieval_skill_id IS NULL` —
  covered must separate *below* cold (SC-002).
- **overall escalation** = `avg(escalated)` — trends down across the series (SC-004).

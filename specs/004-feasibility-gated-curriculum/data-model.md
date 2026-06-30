# Phase 1 — Data Model: Feasibility-Gated Curriculum (004)

The live 14-table schema already carries almost everything (Constitution XI / D4). This feature reads
existing columns and adds **one additive migration** `0006_curriculum_adjacency.sql` — one column on
`benchmark_tasks`, two on `tasks`, plus a one-time training-pool embedding backfill. No deletes, no
cascades, no drops (VI). Human-confirmed before apply (XII).

---

## Existing columns read (no change)

### `skills` (the loadout — read-only here)
- `id`, `name`, `embedding vector(768)`, `state` — adjacency reads
  `WHERE state IN ('stable','testing')` and ranks candidate tasks by cosine to these embeddings
  (`fenrir/memory/retrieval.py:54`). Never mutated by the curriculum (VII).

### `benchmark_tasks` (the training pool)
- `id`, `problem_id`, `pool`, `domain`, `content`, `ground_truth`, `used_count` — selection keeps the
  `pool = 'training'` filter (III) and the unsolved/under-practiced preference; `used_count` is the
  tiebreak under strong adjacency pull (R4).

### `tasks` (per-attempt rows — verdict substrate)
- `retrieval_skill_id`, `retrieval_abstraction_id` — the **coverage** proxy ("had a matching skill")
  the 🧩 panel already reads.
- `escalated` — the 🎯 skill-covered-vs-cold and overall-escalation panels.
- `is_eval` — stays `FALSE` for every curriculum-selected training task (III); consolidation skips
  `is_eval = true` (`fenrir/consolidation/sleep.py:180`) — unchanged.

---

## Additive changes — `0006_curriculum_adjacency.sql`

### 1. `benchmark_tasks.embedding` — the task vector for adjacency
```sql
ALTER TABLE benchmark_tasks ADD COLUMN IF NOT EXISTS embedding vector(768);
CREATE INDEX IF NOT EXISTS bench_embedding_ivf
    ON benchmark_tasks USING ivfflat (embedding vector_cosine_ops);
```
- Nullable, no default. Backfilled **once** for `pool = 'training'` rows via `embed(content)`
  (768-dim `nomic-embed-text`, same model + index family as `skills`/`short_term_memory`).
- Evaluation/transfer rows are **left NULL** — they are never selected, so they never need a vector;
  this also makes "embedded ⇒ training" an invariant a test can assert (pool non-leakage, III).
- Validation: a candidate with `embedding IS NULL` cannot enter the adjacency lane (it has no cosine);
  it is reachable only via the external lane.

### 2. `tasks.selected_via` + `tasks.adjacent_skill_id` — the selection audit (FR-003)
```sql
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS selected_via TEXT;        -- 'adjacency' | 'external' | 'fallback'
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS adjacent_skill_id UUID;   -- skill the task was judged adjacent to; NULL for external/fallback
```
- Both nullable, no backfill (pre-004 rows stay NULL — read as "uniform-random legacy draw").
- Written at row creation in `core._new_task_row` from the value `curriculum.select()` returns.
- `selected_via` domain enforced in application code (not a DB CHECK, to keep the migration trivially
  reversible and avoid a constraint on legacy NULLs).
- No FK on `adjacent_skill_id` → `skills(id)`: skills are versioned/superseded (VII) and an audit
  reference must survive its target's reconsolidation; it is a provenance pointer, not a live relation.

---

## Entities (spec → schema mapping)

| Spec entity | Realized as |
|---|---|
| **Curriculum selection** | `curriculum.select(conn)` → `(BenchTask, selected_via, adjacent_skill_id)`; persisted to `tasks.selected_via` + `tasks.adjacent_skill_id` |
| **Skill loadout / coverage** | `skills` (state-filtered) embeddings; coverage = share of `tasks` with `retrieval_skill_id IS NOT NULL` per cohort (🧩 panel) |
| **Task pools** | `benchmark_tasks.pool` (`training` selectable, `evaluation`/`transfer` read-only); `tasks.is_eval` stays FALSE; "external mix" = uniform training draws |
| **Cohort verdict signals** | derived from `tasks` (`retrieval_skill_id`, `retrieval_abstraction_id`, `escalated`) grouped per cohort — coverage, reuse, skill-covered-vs-cold escalation, overall escalation |

---

## Reversibility (XII)

The migration is mechanically reversible: drop the three columns + the one index. The embedding
backfill writes only to the new nullable column. No existing row's existing columns are touched, so a
rollback restores the pre-004 state exactly (the prior `select_task` still runs against the unchanged
`pool`/`used_count`/`content` columns).

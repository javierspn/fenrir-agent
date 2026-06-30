# Phase 1 — Data Model: family problem generator

Additive only (VI / migrations README). New file `infra/migrations/0009_benchmark_family.sql`.

## `benchmark_tasks` — new column

| column | type | null | meaning |
|---|---|---|---|
| `family` | `text` | yes (NULL = non-generated rows) | solution-method family of a `qwen-gen` problem; the within-family-reuse unit |

- Index `bench_pool_family` on `(pool, family)` for the by-family slice + family-aware queries.
- No CHECK constraint on `family` values (the family list is code-owned + extensible).

```sql
-- 0009_benchmark_family.sql — additive: family label for generated problems (006). One tx, idempotent.
BEGIN;
ALTER TABLE benchmark_tasks ADD COLUMN IF NOT EXISTS family text;
CREATE INDEX IF NOT EXISTS bench_pool_family ON benchmark_tasks (pool, family);
COMMIT;
```

## JSONL record (generator output)

```json
{"question": "<word problem>", "answer": "<int|rational str>", "solution_code": "<sympy code>",
 "family": "<one of 10>", "n_steps": <int>, "source": "qwen-gen"}
```
`answer` is the generator's *claimed* answer; **`solution_code` is REQUIRED** so the loader can
re-derive the authoritative ground truth in the sandbox (R8). *(This extends the Desktop script's
record, which dropped `solution_code` after its local gate — the loader needs it to re-verify under
II/X.)*

## `benchmark_tasks` row for a loaded generated problem

| column | value |
|---|---|
| `benchmark` | `'qwen-gen'` |
| `problem_id` | `'qwen-gen-' + sha256(normalize(question))[:16]` (UNIQUE → idempotent) |
| `pool` | `FAMILY_POOL[family]` (training \| evaluation \| transfer) — whole-family (III) |
| `domain` | `'math'` |
| `content` | `question` |
| `ground_truth` | **sandbox-derived** answer (NOT the JSONL `answer` if they disagree → row rejected) |
| `contamination_safe` | `TRUE` |
| `family` | the family |
| `embedding` | via the **migration-0006** embed path (not feature 006 — distinct numbering); NULL-tolerant, backfillable |

## The 10 families (A1 — `benchmark_loader/families.py`, extensible in code)

`two-step-rate`, `system-2eq`, `percent-of-percent`, `ratio-split`, `work-combined`, `age-problem`,
`unit-conversion`, `avg-backfill`, `interest-simple`, `distance-meet` — each ONE solution method, so
"solving instance 1 makes 2..N cheaper" is the within-family test.

## Family → pool map (R4, `benchmark_loader/families.py`)

Each family wholly assigned (III, never split): the 8 above (minus the two reserved) → `training`;
one held-out within-distribution family → `evaluation`; **≥1 family (default `distance-meet`) →
`transfer`** (never trained on). Static, deterministic, auditable dict.

## By-family verdict (read model — no new table)

Join `tasks.benchmark_id = benchmark_tasks.problem_id`; group by `benchmark_tasks.family`;
within-family position = `row_number() OVER (PARTITION BY family ORDER BY tasks.created_at)`.

```sql
WITH fam AS (
  SELECT bt.family, t.escalated, t.retrieval_skill_id, t.retrieval_abstraction_id,
         row_number() OVER (PARTITION BY bt.family ORDER BY t.created_at) AS pos
  FROM tasks t JOIN benchmark_tasks bt ON bt.problem_id = t.benchmark_id
  WHERE bt.benchmark = 'qwen-gen' AND t.is_eval = false AND t.status <> 'in_progress')
SELECT family,
  round(100*avg(escalated::int) FILTER (WHERE pos = 1),1)  AS escal_first,
  round(100*avg(escalated::int) FILTER (WHERE pos > 1),1)  AS escal_rest,
  round(100*avg((retrieval_skill_id IS NOT NULL OR retrieval_abstraction_id IS NOT NULL)::int)
        FILTER (WHERE pos > 1),1)                           AS reuse_rest
FROM fam GROUP BY family ORDER BY family;
```
Compounding within a family ⇔ `escal_rest < escal_first` AND `reuse_rest > 0`. Flat = recorded
negative (FR-010).

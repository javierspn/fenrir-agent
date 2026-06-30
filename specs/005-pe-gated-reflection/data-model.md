# Phase 1 — Data Model: PE-gated meta-reflection

Additive only (VI / migrations README). New file `infra/migrations/0007_reflection.sql`, one
transaction, idempotent (`IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS`).

## `tasks` — new columns (audit on the row itself)

| column | type | null | meaning |
|---|---|---|---|
| `reflection_tier` | `text` | yes (NULL = pre-feature rows) | one of `none` \| `cheap` \| `full` (CHECK constraint) |
| `reflection_outcome` | `text` | yes | `full` only: `edited` \| `created` \| `none` \| `suppressed`; NULL for `none`/`cheap` |
| `reflection_skill_id` | `uuid` | yes | FK → `skills(id)`; the skill edited/created by this task's full reflection (NULL otherwise) |

- CHECK: `reflection_tier IN ('none','cheap','full')` (NULLs allowed for legacy rows).
- CHECK: `reflection_outcome IN ('edited','created','none','suppressed')` when not NULL.
- FK `reflection_skill_id → skills(id)` — **no** `ON DELETE CASCADE` (D1/VI: never destroy via a task).
- Index `tasks_reflection_tier` on `(reflection_tier, created_at)` for the per-cohort SQL.

## `reflections` — new table (the lesson + provenance)

One row per task that reached `cheap` or `full` (the `none` tier writes only the `tasks` column).

| column | type | null | meaning |
|---|---|---|---|
| `id` | `uuid` PK | no | `gen_random_uuid()` |
| `task_id` | `uuid` | no | FK → `tasks(id)`; the originating task |
| `tier` | `text` | no | `cheap` \| `full` (mirrors `tasks.reflection_tier`; CHECK) |
| `prediction_error` | `double precision` | no | the PE that drove the tier (frozen at reflection time) |
| `lesson` | `text` | yes | `full`: the extracted reusable lesson (LLM); `cheap`: a templated non-LLM note |
| `outcome` | `text` | yes | `full` only: `edited`/`created`/`none`/`suppressed` (mirrors tasks col) |
| `skill_id` | `uuid` | yes | FK → `skills(id)`; skill edited/created (NULL otherwise) |
| `created_at` | `timestamptz` | no | `now()` |

- FKs `task_id → tasks(id)`, `skill_id → skills(id)`; neither cascades to source data (VI).
- Index `reflections_task` on `(task_id)`; index `reflections_created` on `(created_at)`.
- Additive: no change to `episodes`/`short_term_memory`/`skills` schemas; the **edit path reuses the
  existing skill-versioning mechanism** (a new skill version row), it does not alter `skills` columns.

## Relationships

```text
tasks 1──1 (reflection_tier/outcome/skill_id columns)
tasks 1──0..1 reflections   (none-tier tasks have no reflections row)
reflections 0..1──1 skills  (full-tier edited/created skill)
tasks 0..1──1 skills        (reflection_skill_id mirror, for single-row queries)
```

## Migration sketch (`0007_reflection.sql`)

```sql
-- 0007_reflection.sql — additive: PE-gated meta-reflection audit (feature 005). One tx, idempotent.
BEGIN;
ALTER TABLE tasks
  ADD COLUMN IF NOT EXISTS reflection_tier    text,
  ADD COLUMN IF NOT EXISTS reflection_outcome text,
  ADD COLUMN IF NOT EXISTS reflection_skill_id uuid REFERENCES skills(id);
-- CHECKs added NOT VALID-safe (additive); see implementation for exact guard.
CREATE INDEX IF NOT EXISTS tasks_reflection_tier ON tasks (reflection_tier, created_at);

CREATE TABLE IF NOT EXISTS reflections (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id          uuid NOT NULL REFERENCES tasks(id),
  tier             text NOT NULL CHECK (tier IN ('cheap','full')),
  prediction_error double precision NOT NULL,
  lesson           text,
  outcome          text CHECK (outcome IN ('edited','created','none','suppressed')),
  skill_id         uuid REFERENCES skills(id),
  created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS reflections_task    ON reflections (task_id);
CREATE INDEX IF NOT EXISTS reflections_created ON reflections (created_at);
COMMIT;
```

## State transitions (per task)

```text
PE computed ─▶ tier(pe):
  PE < REFLECT_PE_LOW           ─▶ none   ─▶ (episode only; tasks.reflection_tier='none')
  REFLECT_PE_LOW ≤ PE < HIGH    ─▶ cheap  ─▶ reflections row (templated note, no LLM)
  PE ≥ REFLECT_PE_HIGH          ─▶ full   ─▶ is_eval? ──yes──▶ record tier only (read-only, III)
                                            └─no─▶ verified win?
                                                    ├─ matched skill & moderate PE ─▶ EDIT  (new version)
                                                    ├─ cold or large PE            ─▶ CREATE(self-tested)
                                                    └─ budget refused              ─▶ SUPPRESSED (→cheap note)
                                                  unverified/failed ─▶ lesson only, outcome='none'
```

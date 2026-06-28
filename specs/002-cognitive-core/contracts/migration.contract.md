# Contract — Additive Migration `0003_cognitive_core.sql`

**Module**: `infra/migrations/0003_cognitive_core.sql`, applied by `python -m fenrir.db migrate`
**Constitution**: VI (additive, no delete), VII (no overwrite), XII (human-confirmed), IX/D10 (durable).

## Scope (full SQL in `data-model.md`)
Five additive columns + one partial index. **No drops, no `ON DELETE CASCADE`, no data rewrite.**

| Table | Column | Type / default |
|---|---|---|
| `tasks` | `solve_path` | TEXT, CHECK ∈ {retrieval, scratch}, NULL |
| `tasks` | `retrieval_skill_id` | UUID → `skills(id)` (**no** cascade), NULL |
| `short_term_memory` | `importance` | REAL NOT NULL DEFAULT 1.0 |
| `short_term_memory` | `retrieval_frequency` | INTEGER NOT NULL DEFAULT 0 |
| `benchmark_tasks` | `held_out` | BOOLEAN NOT NULL DEFAULT false |
| index | `idx_benchmark_held_out` | partial `(pool, held_out) WHERE held_out` |

## Application rules
- **Human-confirmed**: schema migrations are not run autonomously by the loop (FR-025, XII). The
  operator runs `python -m fenrir.db migrate` and reviews the plain SQL first.
- **Idempotent**: all `ADD COLUMN IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS`; re-run is a no-op.
- **Ordered**: applied after `0001`/`0002`; recorded in `schema_migrations` (version `0003`).
- **Power-loss-safe**: single transaction; a mid-migration power cut rolls back cleanly and re-runs
  (D10).

## Guarantees / tests
- After apply, all five columns + the index exist; `schema_migrations` has row `0003`
  (extend `test_migrations.py` / `test_schema.py`).
- `retrieval_skill_id` FK has no cascade — deleting a skill never deletes a task (D1/VI).
- Re-running the applier produces zero changes (idempotency).

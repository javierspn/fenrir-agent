-- 0003_cognitive_core.sql  (002, T006) — additive only; human-confirmed (Constitution XII / FR-025)
-- Adds the columns the cognitive loop needs on top of the 01-infra schema.
-- No drops, no ON DELETE CASCADE, no data rewrite. Idempotent. Power-loss-safe (single tx, D10).
--
-- NOTE: short_term_memory ALREADY carries `importance`, `salience`, `prediction_error`, and
-- `retrieval_count` (baseline D2/D3), so the loop reuses them — this migration touches STM not at
-- all. Only `tasks` and `benchmark_tasks` gain columns. Even tighter scope discipline (XI).

BEGIN;

-- Iteration solve-path + applied-skill linkage (retrieval-vs-from-scratch curve, SC-009)
ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS solve_path TEXT
        CHECK (solve_path IN ('retrieval', 'scratch')),
    ADD COLUMN IF NOT EXISTS retrieval_skill_id UUID
        REFERENCES skills(id);            -- NO ON DELETE CASCADE (D1/VI)

-- Predictability-gate held-out slice, carved from the TRAINING pool only (Constitution III)
ALTER TABLE benchmark_tasks
    ADD COLUMN IF NOT EXISTS held_out BOOLEAN NOT NULL DEFAULT false;

-- Scan the held-out training slice cheaply during consolidation
CREATE INDEX IF NOT EXISTS idx_benchmark_held_out
    ON benchmark_tasks (pool, held_out) WHERE held_out = true;

COMMIT;

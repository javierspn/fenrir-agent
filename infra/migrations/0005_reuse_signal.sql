-- 0005_reuse_signal.sql  (003 increment C — reuse instrumentation) — additive; human-confirmed (XII)
-- Records, per task, which consolidated abstraction was retrieved/available for the solve, so the
-- SC-008 reuse-rate curve has a countable, time-bucketed sink (graph_updates is constraint-locked
-- and cannot serve a time-series). Mirrors the existing tasks.retrieval_skill_id signal.
--
-- D1 INVARIANT preserved: additive only, NULLABLE, no default, no backfill, no drop/cascade,
-- no FK to short_term_memory. Idempotent. Power-loss-safe (single tx, D10).

BEGIN;

ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS retrieval_abstraction_id uuid;

COMMIT;

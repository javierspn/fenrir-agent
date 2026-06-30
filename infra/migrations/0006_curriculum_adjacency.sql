-- 0006_curriculum_adjacency.sql  (004 feasibility-gated curriculum) — additive; human-confirmed (XII)
-- Gives the curriculum a task vector to compare against the skill loadout, and an audit trail of
-- why each task was selected, so the uniform-random draw can become feasibility-gated + skill-adjacent.
--
--   (a) benchmark_tasks.embedding — 768-dim nomic-embed-text vector (same family as skills/STM/LTM),
--       backfilled for pool='training' rows only by fenrir.bootstrap.backfill_embeddings.
--       evaluation/transfer rows are left NULL — selection never reads them (Constitution III).
--   (b) tasks.selected_via   — 'adjacency' | 'external' | 'fallback' (FR-003 selection audit)
--       tasks.adjacent_skill_id — the skill a task was judged adjacent to (NULL for external/fallback).
--
-- D1 INVARIANT preserved: additive only, NULLABLE, no default, no backfill in SQL, no drop/cascade,
-- no FK (adjacent_skill_id is a provenance pointer that must survive skill reconsolidation, VII).
-- Idempotent. Reversible: drop the three columns + the one index. Power-loss-safe (single tx).

BEGIN;

ALTER TABLE benchmark_tasks
    ADD COLUMN IF NOT EXISTS embedding vector(768);

CREATE INDEX IF NOT EXISTS bench_embedding_ivf
    ON benchmark_tasks USING ivfflat (embedding vector_cosine_ops);

ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS selected_via TEXT;

ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS adjacent_skill_id uuid;

COMMIT;

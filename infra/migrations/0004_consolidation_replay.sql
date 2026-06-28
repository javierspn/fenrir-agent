-- 0004_consolidation_replay.sql  (003 increment B) — additive only; human-confirmed (Constitution XII / FR-012)
-- The ONE schema change for feature 003. Adds the reactivation clock that read-time decay
-- needs (003-B). Increments A and C add NO schema (they reuse existing STM/LTM columns).
--
-- D1 INVARIANT preserved: no drops, no ON DELETE CASCADE toward short_term_memory, no data
-- rewrite, no backfill. Episodes are never hard-deleted; decay is a read-time multiplier only,
-- so this column never causes a row to disappear. Idempotent. Power-loss-safe (single tx, D10).
--
-- last_reactivated_at: timestamptz, NULLABLE, NO default. NULL ⇒ effective_salience() falls back
-- to created_at, so existing rows need no backfill. Set to now() on re-access (retrieval) or a
-- won replay (reversible forgetting, FR-009).

BEGIN;

ALTER TABLE short_term_memory
    ADD COLUMN IF NOT EXISTS last_reactivated_at timestamptz;

COMMIT;

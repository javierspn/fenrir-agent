-- 0007_reflection.sql — PE-gated meta-reflection audit (feature 005). Additive, idempotent, one tx.
-- Constitution VI/D1: add columns/tables only; never destroy a source episode. Applied by the
-- in-house ordered applier (python -m fenrir.db migrate), human-confirmed on deploy (XII).
BEGIN;

-- Per-task audit on the row itself.
ALTER TABLE tasks
  ADD COLUMN IF NOT EXISTS reflection_tier     text,
  ADD COLUMN IF NOT EXISTS reflection_outcome  text,
  ADD COLUMN IF NOT EXISTS reflection_skill_id uuid REFERENCES skills(id);

DO $$ BEGIN
  ALTER TABLE tasks ADD CONSTRAINT tasks_reflection_tier_chk
    CHECK (reflection_tier IS NULL OR reflection_tier IN ('none','cheap','full'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  ALTER TABLE tasks ADD CONSTRAINT tasks_reflection_outcome_chk
    CHECK (reflection_outcome IS NULL OR reflection_outcome IN ('edited','created','none','suppressed'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS tasks_reflection_tier ON tasks (reflection_tier, created_at);

-- The lesson + provenance (one row per cheap/full task; none-tier writes only the tasks column).
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

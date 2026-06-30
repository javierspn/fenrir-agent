-- 0008_cohort_id.sql — per-invocation cohort id for the 004 verdict series. Additive, idempotent.
-- Each `python -m fenrir.core --run N` stamps one cohort_id on its tasks, so the verdict series can
-- plot one point PER BATCH (not per calendar day) — lets the ~8-13-cohort verdict accumulate from
-- many same-day batches instead of waiting one nightly cohort per day. Old rows keep NULL and fall
-- back to the day bucket in the dashboards. (Amends the 004 daily-bucket=cohort decision.)
BEGIN;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS cohort_id uuid;
CREATE INDEX IF NOT EXISTS tasks_cohort_id ON tasks (cohort_id, created_at);
COMMIT;

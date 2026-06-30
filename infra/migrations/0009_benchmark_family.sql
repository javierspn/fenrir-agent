-- 0009_benchmark_family.sql — family label for generated problems (feature 006). Additive, idempotent.
-- Distinct from feature 006: this is migration 0009. The within-family reuse test (D13) groups
-- generated tasks by solution-method family; the column is NULL for all non-generated rows.
BEGIN;
ALTER TABLE benchmark_tasks ADD COLUMN IF NOT EXISTS family text;
CREATE INDEX IF NOT EXISTS bench_pool_family ON benchmark_tasks (pool, family);
COMMIT;

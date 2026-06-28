-- 0002_example_additive.sql — demonstrates the additive-evolution pattern (US3).
--
-- New structure ONLY: a standalone index on long_term_memory(domain). No column
-- drop, no table drop, no DELETE, no destructive change (FR-010 spirit, D1). This
-- proves the applier runs a new NNNN file exactly once and never re-edits an old one.
CREATE INDEX IF NOT EXISTS ltm_domain ON long_term_memory (domain);

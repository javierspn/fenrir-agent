# Contract: Schema & Migrations

**Interface**: versioned SQL migrations under `infra/migrations/`, applied by the in-house
ordered applier, tracked in `schema_migrations`.

## Guarantees
- `0001_baseline_schema.sql` creates **all** entities in [data-model.md](../data-model.md)
  with the listed columns and indexes, including the D1–D4 columns and the salience-ordered
  index, plus `system_state` and `schema_migrations`.
- Both memory tables expose a generated `content_fts tsvector` column with a `gin` index — the
  lexical substrate for the §5 selector's BM25-style lane. Substrate only; no query logic here.
- The `skills` table carries `skill_kind` + `self_test` columns (D6) — substrate for later
  verified-executable-code skills. Columns only; no verification logic here.
- An `eval_runs` table + `tasks.{eval_run_id,is_eval,escalated}` + `benchmark_tasks.
  {contamination_safe,perturbation_of}` exist (D8) — substrate for the learning-measurement
  harness (`EVAL_PROTOCOL.md`) and the Grafana "Learning" dashboard. Ledger/columns only; no
  harness logic. **Invariant:** the consolidation feature MUST exclude `is_eval = TRUE` tasks
  (read-only measurement; extends constitution III — documented obligation).
- A read-only `grafana_ro` Postgres role exists (SELECT only, no DDL/DML; `ALTER DEFAULT
  PRIVILEGES` so future tables stay readable), created in the baseline migration — the Grafana
  datasource connects as this role, never as the owning role (FR-004/FR-004a).
- Migrations apply in lexical order, each in its own transaction; a recorded version is
  never re-executed (idempotent).
- Existing migration files are immutable — new structure ships only as a new `NNNN_*.sql`.

## Invariants (gates)
- **D1 / no episode deletion**: no `ON DELETE CASCADE` referencing `short_term_memory`;
  no `DELETE FROM short_term_memory` in any migration; header comment states the invariant.
- **Anchors**: schema supports `is_anchor` + `decay_rate=0`; decay consumers must filter
  `is_anchor = FALSE` (documented obligation for the consolidation feature).
- **Pools disjoint**: `benchmark_tasks.pool` constrained to the allowed set; a problem id
  is in exactly one pool (enforced by loader, asserted by test).

## Acceptance (maps to SC-002, SC-007)
- All tables/columns/indexes present after apply (introspection query passes).
- Second apply = no-op (no version re-run, no DDL change).
- No cascade path from any table deletes a `short_term_memory` row.

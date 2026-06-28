# Contract — Grafana "Learning" Dashboard

**Module**: `dashboard/provisioning/dashboards/learning.json` (replaces the placeholder)
**Constitution**: read-only datasource. User Story 5 (P2). FR-027/028/029/030, SC-004/005/010.

## Datasource
The existing **`grafana_ro`** read-only Postgres role only. No write capability, no admin creds
(SC-010, Acceptance US5.2). All panels are SQL queries over the live schema.

## The three falsifiable curves (FR-027, SC-004/005)
1. **Cost per solved task over time** — `avg(tasks.cost_usd)` where `verified` bucketed by time.
2. **Escalation rate over time** — `count(*) FILTER (WHERE escalated) / count(*)` per bucket. A **flat**
   line is the valid negative result (recall, not compounding); a **falling** line is compounding —
   the dashboard must make the two visually distinguishable (SC-005).
3. **Retrieval-vs-from-scratch share over time** — share of `tasks.solve_path='retrieval'` per bucket.

## Supporting panels (FR-029)
- Episode count (`short_term_memory`), skill count (`skills` by `state`).
- Pool occupancy (`benchmark_tasks` by `pool`; flag `contamination_safe`).
- Consolidation events (`consolidation_runs` timeline).
- Prediction-error distribution (`tasks.prediction_error` histogram).

## Contamination caveat (FR-030, SC-010)
Every accuracy/generalization panel carries a visible caveat annotation: current benchmark rows are
`contamination_unsafe` — contaminated-pool accuracy is **not** presented as a clean generalization claim.

## Guarantees / tests
- With a cohort of completed iterations, all panels render real values via `grafana_ro` only; the
  placeholder panel is removed (SC-010). Validation in `quickstart.md`.

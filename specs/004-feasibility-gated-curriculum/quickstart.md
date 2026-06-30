# Quickstart — Validate the Feasibility-Gated Curriculum (004)

How to prove the gate works (and is honest) on <host>. Validation/run guide only — implementation
detail lives in `tasks.md` + the contract. Constitution III/VI/XII hold throughout.

## Prerequisites

- The `fenrir` container on <host> with the live schema, `nomic-embed-text` embeddings + pgvector.
- Migration `0006_curriculum_adjacency.sql` applied **after human confirmation** (XII), including the
  one-time training-pool embedding backfill:
  ```
  # human-confirmed apply
  psql "$FENRIR_DSN" -f infra/migrations/0006_curriculum_adjacency.sql
  # verify backfill: every training row embedded, eval rows left NULL (pool-isolation invariant)
  psql "$FENRIR_DSN" -c "SELECT pool, count(*) FILTER (WHERE embedding IS NOT NULL) AS embedded, count(*) FROM benchmark_tasks GROUP BY pool"
  ```
- New tunables present in `fenrir/settings.py` (defaults): `ADJACENCY_STRENGTH=0.6`,
  `ADJACENCY_FEASIBILITY_FLOOR=0.80` (= `RETRIEVAL_SIM_FLOOR`, so the adjacent band is exactly
  "will retrieve, not trivial"), `ADJACENCY_TRIVIAL_CEIL=0.92`, `EXTERNAL_MIN_FRACTION=0.30`.

## Scenario 1 — Gate-ON vs gate-OFF coverage (US1 Independent Test)

Run the same pool twice with a fixed seed, once adjacency-biased, once forced-uniform:
```
# gate ON (adjacency-biased)
ADJACENCY_STRENGTH=1.0 python -m fenrir.core --run 100
# gate OFF (force external lane every slot == pre-004 uniform behaviour)
EXTERNAL_MIN_FRACTION=1.0 python -m fenrir.core --run 100
```
**Expected**: the gate-ON cohort's coverage (`avg(retrieval_skill_id IS NOT NULL)`) is **strictly
higher** than gate-OFF over the same pool, and **no selected task is infeasible** under the loadout
(C2). Per-cohort coverage:
```
psql "$FENRIR_DSN" -c "SELECT date_trunc('hour',created_at) t, avg((retrieval_skill_id IS NOT NULL)::int) coverage, count(*) FROM tasks WHERE created_at > now()-interval '1 hour' GROUP BY 1 ORDER BY 1"
```

## Scenario 2 — Guards hold on 100% of cohorts (US2 Independent Test)

After any cohort, assert all three guards from `tasks`:
```
psql "$FENRIR_DSN" -c "
SELECT
  avg((selected_via='external')::int)            AS external_share,   -- must be >= 0.30
  count(*) FILTER (WHERE is_eval)                 AS eval_selected,    -- must be 0
  count(*) FILTER (WHERE benchmark_pool<>'training') AS nontrain_sel   -- must be 0
FROM tasks WHERE created_at > now()-interval '1 hour'"
```
**Expected**: `external_share ≥ 0.30`, `eval_selected = 0`, `nontrain_sel = 0` (SC-005). The
no-novelty-term guarantee (C3 / FR-006) is asserted in the unit suite, not at runtime.

## Scenario 3 — Cold-start / exhaustion never stalls (US1 #4, FR-008)

With an empty skill library (or after the adjacent band is exhausted), run a cohort:
```
python -m fenrir.core --run 50
```
**Expected**: a full 50-task cohort completes; the no-adjacent slots record `selected_via='fallback'`
or `'external'`; the run never returns fewer tasks than requested while unsolved training tasks remain.

## Scenario 4 — The verdict is readable (US3)

Open the "Are we actually learning?" board (Grafana, `grafana_ro` role). Over an ~8–13 cohort series:
- **🧩 coverage** rises off ~0.8% (SC-001);
- **🎯 skill-covered escalation** separates *below* the cold curve (SC-002);
- **reuse** climbs with coverage (SC-003);
- **overall escalation** trends down (SC-004).

A flat series must be **just as readable** as a positive one — confirm no panel hides or smooths a
non-moving signal (SC-007 / C9).

## Run the test suites

```
pytest tests/unit -k "adjacency or external_quota or no_novelty"
pytest tests/integration -k "coverage or guards or fallback or feasibility or non_leakage"
```
**Expected**: green — band classification + knob semantics + quota arithmetic (unit); gate-ON>gate-OFF
coverage, ≥30% external & 0 eval, cold-start fallback, feasibility never emits infeasible, pool
non-leakage (integration).

## Series runner

The ~8–13 cohort series accumulates through the existing `fenrir-cohort.timer` nightly mechanism on
<host> (04:00 UTC) plus manual `--run N` batches. This feature changes *which* tasks that harness
selects, not how cohorts are launched.

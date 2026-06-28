# Contract — Consolidation ("sleep")

**Module**: `fenrir/consolidation/sleep.py`
**Constitution**: V (regulated, predictability gate — NON-NEGOTIABLE), VI (additive). User Story 4 (P2).

## Trigger
Cadence floor: every `CONSOLIDATION_EVERY_N_ITERS` (default 50) iterations, or manual. Records a
`consolidation_runs` row (level, started/completed, memories_processed, skills_created/patched, cost).

## Processing order
- Scan unconsolidated `short_term_memory` episodes in **descending `salience`** (existing
  `(consolidation_level_reached, salience DESC)` index). Recency is NOT the order (FR-019, D2).

## Predictability gate (the constitutional guard)
For a candidate abstraction:
1. Build the abstraction (generalize the high-salience episode cluster via the consolidator role
   through the proxy).
2. Evaluate on the **held-out training slice** (`benchmark_tasks.held_out=true`, training pool only):
   does post-merge predict/solve ≥ pre-merge?
3. **Merge only if it does not regress** (FR-020). Idiosyncratic detail that merely fits its source
   instances is **not** merged — episodes stay raw.

## Write (additive only)
- A merged abstraction is a **NEW** `long_term_memory` row (`source_memories` = merged episode ids,
  `is_anchor=false`).
- Source episodes get `consolidated_at` set + `consolidation_status` advanced. **Never deleted, never
  cascaded** (FR-021, VI, SC-007).

## Guarantees / tests (`test_consolidation_gate.py`)
- Episodes processed in salience-descending order (seed varied salience, assert order).
- A merge that does not improve held-out cases is rejected.
- Every source episode remains re-derivable after a run — zero hard deletes (SC-007).
- The held-out set is drawn from the **training** pool only; the evaluation pool is never read (III).

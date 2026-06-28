# Contract — Competitive replay over clusters (increment C)

**Module**: `fenrir/consolidation/sleep.py` — `run()` is rewritten. **Revises the 002
consolidation contract** (salience-descending scan → cluster + competitive replay). Gate,
additivity, drift-flag, and pool-isolation guarantees are preserved.

## Interface

```python
def run(conn, *, replay_budget: int | None = None, seed: int | None = None) -> dict:
    """One consolidation pass:
       cluster raw episodes → spend replay_budget by effective-salience (with replacement)
       → merge each drawn cluster into ONE long_term_memory abstraction, strength accrues
       per hit → per-cluster predictability gate + over-merge guard → additive, idempotent.
       Returns {clusters, merged, replays, drift_flagged, skipped_gate, seed}."""
```

## Algorithm (normative)

1. **Candidates**: `short_term_memory` with `consolidation_status='raw'` and
   `effective_salience ≥ EFFECTIVE_SALIENCE_FLOOR`, training/held-out pool only (never eval).
2. **Cluster**: greedy agglomeration, cosine ≥ `CLUSTER_SIM_FLOOR` (0.85) on `embedding`.
3. **Over-merge guard**: split any cluster whose internal max pairwise cosine distance
   > `COHERENCE_MAX_SPREAD` (0.25) back into singletons before gating.
4. **Per-cluster gate**: `predictability_improves(conn, member_ids)` on the held-out training
   slice; fail → skip cluster, members stay raw.
5. **Competitive replay**: seed RNG (`seed` or logged random); weight each surviving cluster
   by Σ member `effective_salience`; draw `REPLAY_BUDGET` times **with replacement**.
   - first draw of a cluster → INSERT one `long_term_memory` (`source_memories` = all members,
     `strength = STRENGTH_PER_REPLAY`, `reinforcement_count = 1`, `abstraction_level ≥ 2`).
   - subsequent draws → `strength += STRENGTH_PER_REPLAY`, `reinforcement_count += 1`,
     `last_reinforced_at = now()`.
   - on any draw, refresh members' `last_reactivated_at = now()` (feeds B).
6. **Mark sources** `consolidated` (+ `consolidated_at`); NEVER delete (VI).
7. **Drift-flag** each new abstraction (`_drift_flag`, FR-019 — unchanged).

## Invariants

1. **Merge-to-one** (SC-005, FR-015). A K-member cluster yields exactly ONE abstraction whose
   `source_memories` contains all K — never K rows.
2. **Replay-weighted strength** (SC-005, FR-016). `strength` and `reinforcement_count` grow
   with draws; a cluster drawn once has `strength = STRENGTH_PER_REPLAY`, drawn d times has
   `d × STRENGTH_PER_REPLAY`.
3. **Competition monotonic** (SC-006). Over a pass, higher-Σ-effective-salience clusters
   receive ≥ draws than lower ones (within sampling noise; deterministic under fixed seed).
4. **Per-cluster gate** (FR-017). No merge whose member set regresses on held-out.
5. **Over-merge rejected** (FR-018). Incoherent clusters are split, not collapsed.
6. **Additive + idempotent** (FR-020, SC-004). Consolidated sources excluded from candidates;
   re-running creates no duplicate abstractions; zero deletions.
7. **Pool isolation** (FR-021, SC-009). Candidate query and gate read only training/held-out;
   test asserts zero eval-pool reads.
8. **Reproducible**: same `(raw set, seed, budget)` → same merges + strengths.

## Tests (integration)

- seed K near-duplicates + noise → exactly 1 abstraction linked to all K.
- two clusters, hi vs lo significance → hi gets more draws (fixed seed).
- strength after d draws == d × STRENGTH_PER_REPLAY.
- regressing cluster → skipped, members remain raw.
- incoherent cluster → split (no single mushy merge).
- re-run pass → no new/duplicate abstractions.
- eval-pool row present in DB → never read (assert via query log / guard).

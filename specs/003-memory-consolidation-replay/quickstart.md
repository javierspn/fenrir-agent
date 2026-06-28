# Quickstart — validate 003 Memory Consolidation Replay

Prerequisites: the 002 loop is live on <host> (Postgres `fenrir_core`, `fenrir` container,
embeddings populated). Run DB ops via `ssh <host>` (`sudo docker exec <postgres> …`).
All checks use the **training/held-out** pool only — never the eval pool.

## Increment A — single bookmark, live value

1. Apply A (no migration). Run a short cohort so episodes are written with the new value.
2. **Single definition**: assert the three entry points agree —
   ```python
   from fenrir.memory.salience import salience
   # recompute() and bump_retrieval_count() must call salience(); unit test asserts equality
   ```
3. **Value ordering** (SC-002): write three verified successes with equal PE/use — from-scratch,
   escalated, crystallized — and assert
   `importance(skill) ≥ importance(teacher) ≥ importance(scratch)` in `short_term_memory`.
4. **No inert 1.0**: `SELECT count(*) FROM short_term_memory WHERE importance = 1.0` on new
   rows trends to ~0 (value now varies by outcome).

**Pass when**: one salience definition, strict value ordering, importance no longer constant.

## Increment B — decay (after 0004 migration, human-confirmed)

1. Review + apply `infra/migrations/0004_consolidation_replay.sql` (adds
   `short_term_memory.last_reactivated_at`). Confirm additive (no drop/backfill).
2. **Monotonic decay** (SC-003): two rows, equal `salience`; reactivate one
   (`last_reactivated_at = now()`), leave the other; with `DECAY_HALFLIFE_DAYS=7`, the idle
   row's `effective_salience` is strictly lower after the simulated interval.
3. **Anchor exemption**: an LTM `is_anchor=true` row (`decay_rate=0`) is unchanged at any age.
4. **Additive** (SC-004): every decayed STM row still returns in full from `SELECT` — zero
   deletions.
5. **Reversible**: re-access (retrieval) bumps `last_reactivated_at`; `effective_salience`
   bounces back toward stored `salience`.
6. **Observable**: dashboard "decay" panel shows `effective_salience` vs age.

**Pass when**: idle < active, anchors flat, nothing deleted, reactivation reverses fade.

## Increment C — competitive replay over clusters

1. Apply C (no migration). Seed a known cluster: insert K near-duplicate verified successes
   plus a few unrelated raw episodes (training pool), with embeddings.
2. Run one pass with a fixed seed:
   ```bash
   ssh <host> 'sudo docker exec <fenrir> python -c \
     "import psycopg,os; from fenrir.consolidation import sleep; \
      c=psycopg.connect(os.environ[\"DATABASE_URL\"]); print(sleep.run(c, seed=1, replay_budget=64))"'
   ```
3. **Merge-to-one** (SC-005): the K-cluster yields exactly ONE `long_term_memory` row with
   `array_length(source_memories,1) = K`.
4. **Replay-weighted strength**: that row's `strength = draws × STRENGTH_PER_REPLAY`,
   `reinforcement_count = draws` (> 1 for a winning cluster) — not a constant 0.5.
5. **Competition** (SC-006): a higher-significance cluster shows ≥ `reinforcement_count` than
   a lower one under the same seed.
6. **Per-cluster gate**: a deliberately regressing cluster is skipped (members stay `raw`).
7. **Over-merge guard**: a cluster of two distinct methods is split, not collapsed into one.
8. **Idempotent** (SC-004): re-run the pass → no new/duplicate abstractions; zero deletions.
9. **Pool isolation** (SC-009): an eval-pool row is never read (asserted in test).

**Pass when**: K→1 with full source list, strength accrues per replay, competition is
monotonic, gate + guard reject bad merges, re-run is a no-op.

## Whole-feature measurement (SC-007/008)

After A+B+C run on live cohorts, the dashboard shows three new curves:
- **strength vs `reinforcement_count`** — does strength concentrate on replayed clusters?
- **`effective_salience` vs age** — does the unimportant fade?
- **reuse rate** — are consolidated abstractions retrieved/applied to later tasks over time?

The **reuse curve is the headline**: compounding is *demonstrated* only if reuse rises above
zero. A flat reuse curve is reported honestly as a valid negative result.

# Implementation Plan: Memory Consolidation Replay (hippocampal two-stage) — 003

**Branch**: `003-memory-consolidation-replay` | **Date**: 2026-06-27 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/003-memory-consolidation-replay/spec.md`

## Summary

Re-found the memory/consolidation subsystem on the hippocampal **two-stage** model: a
significance **bookmark written once at encoding**, **passive forgetting** of what is not
reactivated, and consolidation as **competitive replay over clusters** that merges many
similar episodes into one strengthening abstraction. Three sequenced increments (A→B→C),
each independently mergeable.

The central engineering finding (Constitution XI / D4): **the live schema already carries
almost everything needed.** `short_term_memory` has `importance, salience, prediction_error,
retrieval_count, created_at, consolidated_at`; `long_term_memory` has `strength,
reinforcement_count, last_reinforced_at, decay_rate, source_memories, is_anchor`. So:

- **A (bookmark)** — pure application change in `fenrir/memory/`. The loop currently builds
  the episode with no `importance` (`core.py:168`), so it defaults to an inert `1.0`. Fix:
  one `salience` definition, and a live `value` computed at write from `(verdict, escalated,
  crystallized)`. **No migration.**
- **B (decay)** — compute **effective** significance at read time as
  `salience × exp(-λ · age_since_reactivation)`; the stored bookmark is never mutated
  (additive). Anchors live in `long_term_memory` and set `decay_rate = 0`. Needs exactly
  **one additive column**: `short_term_memory.last_reactivated_at timestamptz NULL`
  (fallback to `created_at`). → migration `0004`, human-confirmed (XII).
- **C (competitive replay)** — replace the top-K scan→copy in `consolidation/sleep.py` with:
  cluster raw episodes by embedding (pgvector), spend a replay budget sampled by cluster
  effective-significance **with replacement**, merge each cluster into **one**
  `long_term_memory` row (`source_memories = all members`), accruing `strength` +
  `reinforcement_count` per replay hit. Per-cluster predictability gate + over-merge guard.
  **No migration** (uses existing LTM columns).

Instrumented with three new dashboard curves (strength-vs-replay, decay, reuse). A flat
result is a valid negative result.

## Technical Context

**Language/Version**: Python 3.12 (extends `fenrir/`).

**Primary Dependencies**: no new runtime deps. Reuses `psycopg[binary]`, the existing
`nomic-embed-text` embeddings + pgvector index, `pydantic-settings`. Weighted sampling uses
the stdlib `random` seeded for reproducibility (no NumPy requirement).

**Storage**: live 14-table schema on <host>. **Additive-only**, exactly one column:
`0004_consolidation_replay.sql` → `ALTER TABLE short_term_memory ADD COLUMN
last_reactivated_at timestamptz` (nullable, no default backfill, no drop, no cascade).
A & C add **no** schema. (Constitution VI/VII/XII.)

**Testing**: pytest + testcontainers (reuse `conftest.py` `migrated_conn`). New suites:
single-salience-definition + value-ordering (A); decay monotonicity + anchor-exemption +
additive-preservation + reversibility (B); cluster-merge-to-one + replay-weighting +
strength-accrual + per-cluster gate + over-merge rejection + idempotency + pool
non-leakage (C).

**Target Platform**: single Linux host (<host>). Consolidation runs in the `fenrir`
container against Postgres; no new service.

**Project Type**: Python cognitive package (single project), DB-backed.

**Performance Goals**: not throughput-bound. One consolidation pass over the raw-episode
backlog completes and persists; weighted sampling terminates deterministically under a
fixed budget; read-time decay adds no write amplification.

**Constraints**: training/held-out only (eval pool never read — III); additive/no-delete
(VI); predictability gate retained and now per-cluster (V); PE stays a distinct factor
(IV); verifier/oracle untouched (II); scope fenced to `memory/` + `consolidation/` + one
migration (XI); the migration is human-confirmed (XII).

**Scale/Scope**: single operator/node. Raw-episode backlog on <host> is small (hundreds);
clustering is O(n²) cosine at this scale — acceptable; a pgvector-index path is noted for
later if the backlog grows.

## Constitution Check

*GATE: must pass before Phase 0. Re-checked after Phase 1.*

| Principle | How this feature complies | Status |
|---|---|---|
| I. Math-only pilot | No new domain; operates on existing math episodes | ✅ PASS |
| II. External ungameable verification | Verifier/oracle untouched; only memory scoring/consolidation changes (FR-022) | ✅ PASS |
| III. Eval pool never trained on | Clustering + per-cluster gate draw only from training/held-out; test asserts zero eval reads (FR-021, SC-009) | ✅ PASS |
| IV. Prediction error gates learning | PE remains a distinct, individually-inspectable factor of significance (FR-001/004); high-PE-idiosyncratic still rejected by the gate | ✅ PASS |
| V. Regulated consolidation + predictability gate | Gate retained and tightened to **per-cluster** before any merge; over-merge guard added (FR-017/018) | ✅ PASS |
| VI. Episodes additive — never hard-deleted | Decay is read-time down-weight only; stored bookmark immutable; consolidation marks sources, never deletes (FR-007/020, SC-004) | ✅ PASS |
| VII. Skills versioned before modification | Not touched (crystallization out of scope except as a value signal) | ✅ PASS |
| VIII. Learner/judge/curriculum separation | Unchanged | ✅ PASS |
| IX. Daily budget hard cap | No new model calls; consolidation is local DB + embeddings already cached | ✅ PASS |
| X. Sandbox network isolation | Unchanged | ✅ PASS |
| XI. Scope discipline | Confined to `memory/` + `consolidation/` + one column; A & C add no schema (D4) | ✅ PASS |
| XII. Human-in-loop on self-modifying schema | The single `0004` migration is presented for human confirmation before apply (FR-012) | ✅ PASS |
| XIII. Autonomous only where verification cheap | Consolidation outcomes gated against held-out problems; drift-flag for human review retained | ✅ PASS |

**No violations. Complexity Tracking table omitted (nothing to justify).**

## Project Structure

### Documentation (this feature)

```text
specs/003-memory-consolidation-replay/
├── plan.md              # this file
├── research.md          # Phase 0 — the 3 deferred decisions, resolved
├── data-model.md        # Phase 1 — STM/LTM fields used + the 0004 column
├── contracts/
│   ├── significance.contract.md     # A: the single salience + value definition
│   ├── decay.contract.md            # B: read-time decay + reactivation + anchor rule
│   └── consolidation.contract.md    # C: cluster → competitive replay → merge (revises 002)
├── quickstart.md        # Phase 1 — how to validate A, B, C on <host>
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
fenrir/
├── memory/
│   ├── salience.py        # A: single significance definition (surprise × value × use);
│   │                      #    add value(verdict, escalated, crystallized); read-time
│   │                      #    effective_salience() with decay (B)
│   ├── episodes.py        # A: write_episode takes a real importance; B: set/refresh
│   │                      #    last_reactivated_at
│   └── retrieval.py       # B: on surface, refresh last_reactivated_at (reactivation)
├── consolidation/
│   └── sleep.py           # C: cluster → weighted-with-replacement replay → merge-to-one →
│                          #    strength accrual; per-cluster gate + over-merge guard
├── core.py                # A: pass importance into Episode from (verdict, escalated,
│                          #    crystallized) — the only loop touch, supplying the signal
└── settings.py            # tunables: value weights, decay half-life, replay budget,
                           #    cluster similarity floor, strength-per-replay

infra/migrations/
└── 0004_consolidation_replay.sql   # B only: + short_term_memory.last_reactivated_at

dashboard/provisioning/dashboards/
└── learning.json          # +3 panels: strength-vs-replay, decay curve, reuse rate

tests/
├── unit/        # significance ordering, decay math, sampling weighting
└── integration/ # cluster-merge, per-cluster gate, idempotency, pool non-leakage
```

**Structure Decision**: single project; all changes inside `fenrir/memory/` +
`fenrir/consolidation/` + `settings.py`, one loop line in `core.py` to supply the value
signal, one additive migration, three dashboard panels. Matches the 002 layout.

## Complexity Tracking

> No Constitution violations — section intentionally empty.

# Implementation Plan: Feasibility-Gated Curriculum (skill-adjacent task bias) — 004

**Branch**: `004-feasibility-gated-curriculum` | **Date**: 2026-06-29 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/004-feasibility-gated-curriculum/spec.md`

## Summary

Replace the **uniform-random training-task draw** with a **feasibility-gated, skill-adjacency-biased**
one, so a stored skill actually meets the next task often enough that reuse can bite. The 003 verdict
is honest — *recall, not compounding* — and the single binding number is **skill coverage ≈ 0.8%**.
Random sampling over ~10k tasks makes a skill-to-task collision rare by construction; this feature
attacks that directly while keeping every reward-hacking guard intact.

The central engineering finding (Constitution XI / D4): **the adjacency substrate already exists.**
`fenrir/memory/retrieval.py` already ranks skills against a query by pgvector cosine + lexical lane,
and `RETRIEVAL_SIM_FLOOR` (0.80) already defines "a skill will be retrieved." So adjacency is not a
new classifier — it is the *same* cosine, evaluated at task-selection time instead of solve time.
The only thing missing is a **task vector to compare against the skill vectors**: `benchmark_tasks`
has no `embedding` column. That is the one additive schema change.

Surgical shape, mirroring the 003 layout (one new module + `settings.py` + one additive migration):

- **Selection policy** — a new thin module `fenrir/curriculum.py` scores each unsolved training
  candidate by its **max cosine to the current skill loadout**, classifies it into an
  **adjacency band** (infeasible / adjacent / trivially-covered), applies the **feasibility gate**
  (the adjacency lane never emits a task below the feasibility floor or above the trivial ceiling),
  and biases the pick by an operator-tunable **`ADJACENCY_STRENGTH`** (0 = pure feasibility filter,
  1 = strong pull to the most-adjacent feasible task). `core.select_task` becomes a thin caller.
- **30% external mix (US2 #1)** — enforced at **cohort granularity** inside `run(n)`: a deterministic
  quota guarantees ≥`EXTERNAL_MIN_FRACTION` of the cohort's slots are **uniform** external-benchmark
  draws (the existing `select_task` behaviour, preserved verbatim as the fallback/diversity lane),
  independent of adjacency. This is also the cold-start and adjacency-exhaustion fallback (FR-008).
- **Selection audit (FR-003)** — two additive columns on `tasks`: `selected_via TEXT`
  (`'adjacency' | 'external' | 'fallback'`) and `adjacent_skill_id UUID`, written at row creation.
- **No novelty term (US2 #3 / FR-006)** — the objective is *only* feasibility + adjacency cosine.
  There is no diversity/novelty reward anywhere; diversity comes solely from the forced external mix.
- **Eval pool untouched (III)** — selection already filters `pool = 'training'`; the new lane keeps
  that filter and adds nothing that could read an `is_eval`/evaluation row.
- **Verdict legibility (US3)** — coverage / reuse / skill-covered-vs-cold / escalation already render
  on the "Are we actually learning?" board off existing `tasks` columns
  (`retrieval_skill_id`, `retrieval_abstraction_id`, `escalated`). US3 confirms they read correctly
  under the new policy and adds only the missing per-cohort series cut, not a new board.

Instrumented to **prove or honestly falsify** that biasing toward skill-adjacent tasks lifts coverage
and, through it, produces observable compounding. A flat series over ~8–13 cohorts is a valid,
recorded negative result (FR-011 / SC-007).

## Technical Context

**Language/Version**: Python 3.12 (extends `fenrir/`).

**Primary Dependencies**: no new runtime deps. Reuses `psycopg[binary]`, the existing
`nomic-embed-text` (768-dim) embeddings + pgvector ivfflat indexes, `pydantic-settings`. Adjacency
scoring reuses `fenrir.memory.embed.embed` + the cosine operator already used by `retrieval.py`.
The biased pick uses stdlib `random` (seedable for reproducibility) — no novelty objective, no NumPy.

**Storage**: live schema on <host>. **Additive-only**, one migration `0006_curriculum_adjacency.sql`:
(a) `ALTER TABLE benchmark_tasks ADD COLUMN embedding vector(768)` + ivfflat index + a one-time
backfill of training-pool rows via `embed(content)`; (b) `ALTER TABLE tasks ADD COLUMN selected_via
TEXT` and `ADD COLUMN adjacent_skill_id UUID` (both nullable, no default backfill, no drop, no
cascade). Human-confirmed before apply (Constitution XII).

**Testing**: pytest + testcontainers (reuse `conftest.py` `migrated_conn`). New suites: adjacency-band
classification + knob semantics (unit); gate-ON vs gate-OFF coverage delta, ≥30% external & 0 eval
on every cohort, objective-has-no-novelty-term, cold-start/exhaustion fallback fills the cohort,
feasibility gate never emits an infeasible task, pool non-leakage (integration).

**Target Platform**: single Linux host (<host>). Selection runs in the `fenrir` container against
Postgres; no new service. The existing `fenrir-cohort.timer` nightly harness is the runner — this
feature changes *which* task `run(n)` selects, not how cohorts are launched.

**Project Type**: Python cognitive package (single project), DB-backed.

**Performance Goals**: not throughput-bound. Embedding backfill is one-time over the training pool
(hundreds–low-thousands of rows; embeddings are local + cached). Per-selection cost is one task embed
(cached) + one pgvector top-k over `skills` — negligible vs a solve.

**Constraints**: training-pool only, eval never read (III); additive/no-delete (VI); curriculum stays
a separate instance from learner+judge (VIII); selection objective limited to feasibility+adjacency,
no novelty reward (FR-006, §10.1); ≥30% external mix every cohort (FR-004); budget hard cap unchanged
(IX); scope fenced to `fenrir/curriculum.py` + `core.py` (thin) + `settings.py` + one additive
migration + dashboard read-back (XI); the migration is human-confirmed (XII).

**Scale/Scope**: single operator/node. Training pool is small (hundreds–low-thousands); top-k cosine
over the skill set (tens) per selection is trivial. ~8–13 cohorts (~2–2.5k tasks) produce the verdict.

## Constitution Check

*GATE: must pass before Phase 0. Re-checked after Phase 1.*

| Principle | How this feature complies | Status |
|---|---|---|
| I. Math-only pilot | No new domain; biases selection within the existing math training pool only | ✅ PASS |
| II. External ungameable verification | Verifier/oracle untouched; only task *selection* changes (FR-001/002) | ✅ PASS |
| III. Eval pool never trained on | Selection keeps the `pool='training'` filter; adjacency lane reads only training rows; test asserts 0 eval-pool tasks selected (FR-005, SC-005) | ✅ PASS |
| IV. Prediction error gates learning | Unchanged — PE still gates crystallization downstream; selection does not touch the PE gate | ✅ PASS |
| V. Regulated consolidation + predictability gate | Unchanged — consolidation/sleep untouched | ✅ PASS |
| VI. Episodes additive — never hard-deleted | Migration is additive (one column on `benchmark_tasks`, two on `tasks`); no deletes, no cascade (FR-012) | ✅ PASS |
| VII. Skills versioned before modification | Not touched — curriculum reads skills read-only, never mutates them | ✅ PASS |
| VIII. Learner/judge/curriculum separation | Curriculum stays a separate instance; reads only the skill loadout + task pool, never the learner's reasoning/self-eval (FR-007, US2 #4) | ✅ PASS |
| IX. Daily budget hard cap | No new model calls in the hot path; embedding backfill is local + one-time; on exhaustion the existing degradation rule applies unchanged (FR-012) | ✅ PASS |
| X. Sandbox network isolation | Unchanged — selection is a DB + local-embed operation | ✅ PASS |
| XI. Scope discipline | One new thin module + `settings.py` + one additive migration + dashboard read-back; **rejects** Voyager novelty-max (FR-006 / D6); adds one mechanism justified by the 003 coverage measurement | ✅ PASS |
| XII. Human-in-loop on self-modifying schema | The single `0006` migration (incl. backfill) is presented for human confirmation before apply | ✅ PASS |
| XIII. Autonomous only where verification cheap | Coverage inflation guarded by held-out eval verdict (III) + reuse cross-check, not training accuracy (Edge: coverage-inflation hack) | ✅ PASS |

**No violations. Complexity Tracking table omitted (nothing to justify).**

## Project Structure

### Documentation (this feature)

```text
specs/004-feasibility-gated-curriculum/
├── plan.md              # this file
├── research.md          # Phase 0 — the 4 selection decisions, resolved
├── data-model.md        # Phase 1 — columns used + the 0006 additive changes
├── contracts/
│   └── selection.contract.md   # feasibility gate + adjacency band + external quota + audit record
├── quickstart.md        # Phase 1 — how to validate the gate on <host> (gate-ON vs gate-OFF)
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
fenrir/
├── curriculum.py          # NEW: adjacency scoring (max skill-cosine via existing embed substrate);
│                          #   band classify (infeasible / adjacent / trivially-covered); feasibility
│                          #   gate; ADJACENCY_STRENGTH-weighted pick; returns (BenchTask, selected_via,
│                          #   adjacent_skill_id). Pure policy — no model calls, no novelty term.
├── core.py                # select_task → thin caller of curriculum.select(); run() enforces the
│                          #   per-cohort ≥EXTERNAL_MIN_FRACTION external quota and writes the
│                          #   selection audit (selected_via, adjacent_skill_id) into the task row
└── settings.py            # + ADJACENCY_STRENGTH, ADJACENCY_FEASIBILITY_FLOOR, ADJACENCY_TRIVIAL_CEIL,
                           #   EXTERNAL_MIN_FRACTION

infra/migrations/
└── 0006_curriculum_adjacency.sql   # additive: benchmark_tasks.embedding vector(768) + ivfflat +
                                    #   training-pool backfill; tasks.selected_via, tasks.adjacent_skill_id

dashboard/provisioning/dashboards/
├── overview.json          # US3: confirm 🧩 coverage + 🎯 skill-covered-vs-cold read under new policy
└── learning.json          # US3: add the missing per-cohort series cut if absent (no new board)

tests/
├── unit/        # adjacency-band classification, knob semantics (0 = filter, 1 = strong pull),
│                #   external-quota arithmetic, no-novelty-term assertion on the objective
└── integration/ # gate-ON > gate-OFF coverage on same pool; ≥30% external & 0 eval every cohort;
                 #   cold-start + adjacency-exhaustion fallback fills a full cohort; feasibility gate
                 #   never emits an infeasible task; pool non-leakage
```

**Structure Decision**: single project; selection policy isolated in a new `fenrir/curriculum.py`
to keep `core.py` thin (it stays the loop runner), one cohort-quota touch in `run()`, the audit write
in the task-row insert, four tunables in `settings.py`, one additive human-confirmed migration, and
dashboard read-back only. Matches the 002/003 layout.

## Complexity Tracking

> No Constitution violations — section intentionally empty.

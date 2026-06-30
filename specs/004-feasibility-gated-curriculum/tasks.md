---
description: "Task list for 004 Feasibility-Gated Curriculum (skill-adjacent task bias)"
---

# Tasks: Feasibility-Gated Curriculum (skill-adjacent task bias)

**Input**: Design documents from `/specs/004-feasibility-gated-curriculum/`

**Prerequisites**: plan.md, spec.md, research.md (R1–R4), data-model.md, contracts/selection.contract.md

**Tests**: REQUESTED. The contract has test-backed invariants and plan.md lists explicit unit + integration suites — test tasks are included and gate each story.

**Organization**: by user story. US1 = feasibility-gated adjacency selection (P1, the lever); US2 = anti-reward-hacking guards (co-equal P1, ship together); US3 = verdict legibility (P2). Selection (US1) + guards (US2) are interdependent — the cohort quota in `run()` belongs to US2 — so US1 and US2 share Foundational and land together; US3 is read-back only.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different file, no incomplete dependency)
- **[Story]**: US1 = adjacency/feasibility selection; US2 = guards; US3 = dashboard verdict
- Exact paths included. Repo root = `<repo-root>`.

## Path conventions

Single Python project. Source `fenrir/`, tests `tests/unit/` + `tests/integration/`, migrations `infra/migrations/`, dashboard `dashboard/provisioning/dashboards/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: tunables both lanes need. No behavior change yet.

- [X] T001 [P] Add 004 tunables to `fenrir/settings.py` as pydantic-settings fields matching existing style (lines 51–76): `ADJACENCY_STRENGTH: float = 0.6`, `ADJACENCY_FEASIBILITY_FLOOR: float = 0.80` (= `RETRIEVAL_SIM_FLOOR`, so the adjacent band is exactly "will retrieve, not trivial" — research.md/R2 floor reconciliation), `ADJACENCY_TRIVIAL_CEIL: float = 0.92`, `EXTERNAL_MIN_FRACTION: float = 0.30`. Each with the documented default + one-line comment from data-model.md/research.md (R2/R3/R4). All overridable via `infra/.env`. **Naming**: use these full `ADJACENCY_`-prefixed names everywhere; the contract's `FEASIBILITY_FLOOR`/`TRIVIAL_CEIL` are shorthand for `ADJACENCY_FEASIBILITY_FLOOR`/`ADJACENCY_TRIVIAL_CEIL` (I3).

**Checkpoint**: settings expose all four knobs; no selection behavior changed yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the additive schema + task vectors both lanes and the audit depend on. Blocks US1 and US2. Human-confirmed migration (Constitution XII).

- [X] T002 Write additive migration `infra/migrations/0006_curriculum_adjacency.sql`: `ALTER TABLE benchmark_tasks ADD COLUMN IF NOT EXISTS embedding vector(768)`; `CREATE INDEX IF NOT EXISTS bench_embedding_ivf ON benchmark_tasks USING ivfflat (embedding vector_cosine_ops)`; `ALTER TABLE tasks ADD COLUMN IF NOT EXISTS selected_via TEXT`; `ALTER TABLE tasks ADD COLUMN IF NOT EXISTS adjacent_skill_id UUID`. All nullable, no default, no drop, no cascade (data-model.md §additive, Constitution VI). Header comment notes human-confirm-before-apply (XII).
- [X] T003 Add training-pool embedding backfill as a new `fenrir/bootstrap/backfill_embeddings.py` (U2: pick the dedicated module, not inline in `__main__.py`), invoked from `bootstrap/__main__.py`: for every `benchmark_tasks WHERE pool='training' AND embedding IS NULL`, write `embed(content)` via `fenrir.memory.embed.embed`/`to_pgvector`. Idempotent (skips already-embedded). Leaves `evaluation`/`transfer` rows NULL — the "embedded ⇒ training" invariant (data-model.md, pool isolation III).
- [X] T004 [P] Create `fenrir/curriculum.py` scaffold: module docstring referencing `contracts/selection.contract.md`; `@dataclass Selection(task: BenchTask, selected_via: str, adjacent_skill_id: str | None)`; `select(conn, *, force_external: bool, seed: int | None = None) -> Selection` signature with `NotImplementedError` body. U1 (cycle resolution): keep `BenchTask` defined in `fenrir/core.py` and `from fenrir.core import BenchTask` inside `curriculum.py`; `core.py` calls `curriculum.select` only inside `select_task`/`run` (function-local import if a module-level cycle appears), so there is no import-time cycle.

**Checkpoint**: migration written (apply is a deploy step, T021); backfill ready; `curriculum.select` exists as a typed stub. US1 and US2 can now proceed.

---

## Phase 3: User Story 1 — Feasibility-gated, skill-adjacent selection (Priority: P1) 🎯 MVP

**Goal**: replace the uniform-random draw with an adjacency lane that prefers tasks in the *adjacent* band and never emits an infeasible or trivially-covered task. `core.select_task` becomes a thin caller.

**Independent Test**: seed a known skill set; run selection one cohort gate-ON (adjacency) and once gate-OFF (forced uniform) over the same pool; assert gate-ON coverage strictly higher and **0 infeasible tasks** proposed, while gate-OFF reproduces ~baseline coverage.

### Tests for User Story 1 (write first, must FAIL before impl) ⚠️

- [X] T005 [P] [US1] Unit test adjacency-band classification in `tests/unit/test_adjacency_band.py`: a pure `classify(cosine, floor, ceil) -> {'infeasible','adjacent','trivial'}` helper; assert `c<floor→infeasible`, `floor≤c<ceil→adjacent`, `c≥ceil→trivial`; boundary values land in the documented band (selection.contract C2, R2).
- [X] T006 [P] [US1] Unit test knob semantics in `tests/unit/test_adjacency_strength.py`: with `ADJACENCY_STRENGTH=0` the ranker is uniform over the adjacent band; with `=1` it returns the max-cosine candidate (ties → lower `used_count`, then seeded random); monotone sharpening in between (selection.contract C3, R4).
- [X] T007 [P] [US1] Integration test gate-ON > gate-OFF coverage in `tests/integration/test_coverage_gate.py` (uses `migrated_conn`): seed skills + a training pool with embeddings spanning bands; run `select(force_external=False)` repeatedly (gate ON) and `force_external=True` (gate OFF) over the same pool with a fixed seed; assert gate-ON fraction of adjacent-band picks strictly exceeds gate-OFF (US1 Independent Test, SC-001).
- [X] T008 [P] [US1] Integration test feasibility gate in `tests/integration/test_feasibility_gate.py`: seed a pool where some tasks are below `FEASIBILITY_FLOOR` and some above `TRIVIAL_CEIL`; assert the adjacency lane (`force_external=False`) never returns an infeasible or trivially-covered task across many draws (SC-006, C2).

### Implementation for User Story 1

- [X] T009 [US1] In `fenrir/curriculum.py` implement adjacency scoring: for the unsolved training candidates (`pool='training'`, not-yet-succeeded, `embedding IS NOT NULL`), compute each candidate's **max cosine to `skills WHERE state IN ('stable','testing')`** via one pgvector query (`1 - (b.embedding <=> s.embedding)` cross join, or a per-candidate `ORDER BY embedding <=> ... LIMIT 1`), returning `(task, best_cosine, best_skill_id)`. No lexical lane, no model call (R1, C7).
- [X] T010 [US1] In `fenrir/curriculum.py` implement the band classify + feasibility gate using settings floors/ceil; keep only the **adjacent** band as adjacency-lane candidates (C2). On empty candidate set, signal exhaustion to the caller (return a sentinel so `select` can fall back — C5).
- [X] T011 [US1] In `fenrir/curriculum.py` implement the `ADJACENCY_STRENGTH`-weighted pick over the adjacent band (R4): `0`→uniform, `1`→argmax cosine with `used_count`/seeded-random tiebreak, intermediate→cosine-sharpened weighted sample using stdlib `random` seeded by `seed`. Return `Selection(task, 'adjacency', best_skill_id)`.
- [X] T012 [US1] Implement the external lane in `fenrir/curriculum.py`: lift the existing uniform query from `core.select_task` (`pool='training'`, unsolved, under-practiced ASC + `random()`) verbatim into a helper; `select(force_external=True)` returns `Selection(task, 'external', None)`; `select(force_external=False)` runs the adjacency lane and on exhaustion falls back to this helper returning `Selection(task, 'fallback', None)` (C5).
- [X] T013 [US1] Rewire `fenrir/core.py:select_task` to a thin wrapper that calls `curriculum.select(conn, force_external=...)` and returns the `BenchTask` (preserve the existing `BenchTask | None` contract for `run_iteration`). Thread `selected_via` + `adjacent_skill_id` through to `_new_task_row` (see T016).

**Checkpoint**: adjacency lane + feasibility gate live; `core` selects via curriculum; US1 tests green. MVP is testable in isolation by forcing `EXTERNAL_MIN_FRACTION` 0/1.

---

## Phase 4: User Story 2 — Anti-reward-hacking guards preserved (Priority: P1)

**Goal**: the cohort still draws ≥30% external, never touches the eval pool, ranks with no novelty term, and the curriculum stays a separate instance. Guards ship with US1.

**Independent Test**: run a cohort and assert (a) ≥30% external-lane tasks; (b) 0 `is_eval=TRUE` selected; (c) the objective has no novelty term (two equal-`(band,cosine)` candidates ranked indifferently); attempting to select an eval-pool task is rejected.

### Tests for User Story 2 (write first, must FAIL before impl) ⚠️

- [X] T014 [P] [US2] Unit test external-quota arithmetic in `tests/unit/test_external_quota.py`: for cohort sizes `n` and `EXTERNAL_MIN_FRACTION`, assert the slot planner yields ≥`ceil(frac·n)` external slots for every `n` (not just in expectation), incl. small `n` (C4, SC-005).
- [X] T015 [P] [US2] Unit test no-novelty objective in `tests/unit/test_no_novelty.py`: feed the ranker two adjacent candidates identical in `(band, cosine)` but maximally different in content/"newness"; assert the ranker is indifferent (no distance-from-seen/entropy term influences the score) (FR-006, C3).
- [X] T016 [P] [US2] Integration test guards-every-cohort in `tests/integration/test_guards.py` (uses `migrated_conn`): run a cohort via `core.run(n)`; assert from `tasks` `avg(selected_via='external') ≥ 0.30`, `count(*) FILTER (WHERE is_eval) = 0`, `count(*) FILTER (WHERE benchmark_pool<>'training') = 0` (SC-005, C1/C4). Also assert an explicit attempt to select an `evaluation`-pool row is rejected by both lanes.
- [X] T017 [P] [US2] Integration test cold-start/exhaustion fallback in `tests/integration/test_fallback.py`: with an empty `skills` table, `core.run(50)` still produces 50 valid tasks all marked `selected_via IN ('external','fallback')`; never returns fewer than requested while unsolved training tasks remain (FR-008, C5).

### Implementation for User Story 2

- [X] T018 [US2] In `fenrir/core.py:run(n)` add the per-cohort external quota (C4): plan `ceil(EXTERNAL_MIN_FRACTION·n)` external slots deterministically across the `n` iterations (e.g. evenly interleaved), pass `force_external` per slot into `select_task`→`curriculum.select`. Keep the per-iteration try/except and consolidation cadence unchanged.
- [X] T019 [US2] In `fenrir/core.py:_new_task_row` persist the audit (FR-003, C6): extend the INSERT to write `selected_via` and `adjacent_skill_id` (passed down from T013). Confirm the INSERT still sets `is_eval=false`, `benchmark_pool='training'` (III) — guards enforced at the write boundary.
- [X] T020 [US2] Add a module-level note + assertion in `fenrir/curriculum.py` that `select` reads only `skills` + `benchmark_tasks` (no `tasks.result`/prediction/judge columns) — separation of powers (VIII, C7) — and makes **zero LLM/proxy calls** (G2: budget cap respected by construction, FR-012/IX; the one task embed is local). Defensive: both lane queries hard-filter `pool='training'`/exclude `is_eval` so an eval row cannot be returned even if called wrongly (C1).

**Checkpoint**: guards enforced on 100% of cohorts; US1+US2 land together as the shippable unit.

---

## Phase 5: User Story 3 — The compounding verdict is readable (Priority: P2)

**Goal**: confirm the existing board reads correctly under the new policy; add only the missing per-cohort series cut. No new board.

**Independent Test**: run a short multi-cohort series gate-ON; confirm coverage, reuse, skill-covered-vs-cold escalation, and overall escalation are each queryable per cohort and render as a trend — including a flat (negative) result.

- [X] T021 [US3] Apply migration `0006` on <host> **after human confirmation** (XII) and run the T003 backfill; verify with `SELECT pool, count(*) FILTER (WHERE embedding IS NOT NULL), count(*) FROM benchmark_tasks GROUP BY pool` that all training rows are embedded and eval rows are NULL (quickstart Prerequisites).
- [X] T022 [P] [US3] Verify the 🧩 coverage + 🎯 skill-covered-vs-cold panels in `dashboard/provisioning/dashboards/overview.json` read correctly under the new policy (they key off `retrieval_skill_id`/`retrieval_abstraction_id`/`escalated`, all still written) — adjust only the panel descriptions if the curriculum changes their interpretation (US3 Acceptance 1).
- [X] T023 [US3] Add the missing **per-cohort series** cut to `dashboard/provisioning/dashboards/learning.json` (or overview.json): coverage, reuse, skill-covered-vs-cold escalation gap, overall escalation as per-cohort trends via the `grafana_ro` role; each verdict signal queryable per cohort — reuse tracking coverage (SC-003), skill-covered escalation separating below cold (SC-002), overall escalation trending down (SC-004); ensure a flat series renders plainly as a recorded negative (SC-007, C9). No new dashboard file.

**Checkpoint**: the four verdict signals are legible per cohort; a negative result is as readable as a positive one.

---

## Phase 6: Polish & Cross-Cutting

- [X] T024 [P] Update `OPS.md` (and `infra/.env.example` if present) with the four new tunables + the gate-ON/gate-OFF run recipe from `quickstart.md`.
- [ ] T025 Run the full gate before push: `ruff check .`, `pytest tests/unit tests/integration -k "adjacency or external_quota or no_novelty or coverage or guards or fallback or feasibility"`, `python3 scripts/spec_coverage.py`, `python3 scripts/spec_snapshot.py --check` — all green (ragnarok CI gates).
- [ ] T026 Kick the ~8–13 cohort series via the existing `fenrir-cohort.timer` on <host> + manual `--run N` batches; record the verdict honestly in `backlog.md`: coverage trend (SC-001), reuse cross-check tracking coverage (SC-003), skill-covered-below-cold escalation separation (SC-002), overall escalation trending down (SC-004) — flat is a valid recorded outcome (FR-011, SC-007).

---

## Dependencies & completion order

- **Setup (T001)** → blocks the lanes (knobs).
- **Foundational (T002–T004)** → blocks US1 + US2. T002 (migration) and T003 (backfill) before any adjacency cosine works; T004 (scaffold) before T009–T013.
- **US1 (T005–T013)** + **US2 (T014–T020)** are co-equal P1 and land together: US2's quota (T018) and audit write (T019) depend on US1's `curriculum.select` (T009–T013) and the rewired `core.select_task` (T013). Tests (T005–T008, T014–T017) written first, must fail.
- **US3 (T021–T023)** depends on the migration applied (T021) and the policy live (US1+US2). Read-back only.
- **Polish (T024–T026)** last; T026 needs everything merged + deployed.

**Story independence**: US1 is testable alone by setting `EXTERNAL_MIN_FRACTION` to 0 (pure adjacency) / 1 (pure uniform). US3 is pure read-back. US1+US2 are the shippable unit (guards must ship with the bias, spec US2 "Why this priority").

## Parallel opportunities

- T001 ∥ (nothing else in Setup).
- Within Foundational: T004 ∥ T002/T003 (different files).
- All test tasks marked [P] within a story run in parallel (distinct files): T005∥T006∥T007∥T008; T014∥T015∥T016∥T017.
- Implementation tasks in US1 are mostly sequential (same file `curriculum.py` + `core.py`): T009→T010→T011, T012, then T013.
- T022 ∥ T024 (different files).

## Suggested MVP scope

**US1 + US2 together** (T001–T020): the feasibility-gated adjacency selection with its guards. This is the smallest shippable unit that moves coverage *and* keeps the learning signal trustworthy. US3 (T021–T023) makes the verdict legible and is a fast follow once cohorts run.

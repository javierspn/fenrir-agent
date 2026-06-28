---
description: "Task list for 003 Memory Consolidation Replay (hippocampal two-stage)"
---

# Tasks: Memory Consolidation Replay (hippocampal two-stage)

**Input**: Design documents from `/specs/003-memory-consolidation-replay/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (significance, decay, consolidation)

**Tests**: REQUESTED. Each contract has a Tests section and plan.md lists explicit suites — test tasks are included and gate each story.

**Organization**: by user story (A → P1, B → P2, C → P3). Increments land in order; B and C assume A merged. Each story independently mergeable + testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different file, no incomplete dependency)
- **[Story]**: US1=A (bookmark), US2=B (decay), US3=C (replay)
- Exact paths included. Repo root = `<repo-root>`.

## Path conventions

Single Python project. Source `fenrir/`, tests `tests/unit/` + `tests/integration/`, migrations `infra/migrations/`, dashboard `dashboard/provisioning/dashboards/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: tunables + test scaffold all three increments need. No behavior change yet.

- [X] T001 [P] Add increment-A/B/C tunables to `fenrir/settings.py` as pydantic-settings fields matching existing style (lines 37–61): `W_FAIL=0.2`, `W_UNVERIFIED=0.1`, `W_ESCALATED=1.5`, `W_CRYSTALLIZED=2.0` (A); `DECAY_HALFLIFE_DAYS=7.0` (B); `CLUSTER_SIM_FLOOR=0.85`, `REPLAY_BUDGET=64`, `STRENGTH_PER_REPLAY=0.1`, `COHERENCE_MAX_SPREAD=0.25`, `EFFECTIVE_SALIENCE_FLOOR=0.05` (C). Each with the documented default from data-model.md.
- [X] T002 [P] Create `tests/unit/` package (only `tests/integration/` exists today): add `tests/unit/__init__.py` so unit suites for A/B can live there; confirm `tests/conftest.py` `migrated_conn` fixture is importable from `tests/unit/`.

**Checkpoint**: settings expose all knobs; unit test dir exists.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: none beyond Setup. This feature has no cross-story foundational layer — A is itself the foundation US2/US3 weight on, so it is delivered as Phase 3 (US1). No separate Phase 2 work.

**Checkpoint**: proceed directly to US1 after Setup.

---

## Phase 3: User Story 1 — A: One significance bookmark at encoding (Priority: P1) 🎯 MVP

**Goal**: exactly one definition of significance; `value` is a live signal from `(verdict, escalated, crystallized)`, never the inert constant. Fixes the 1.0-vs-0.5 drift and the `bump` off-by-one.

**Independent Test**: three verified successes with identical PE/use — from-scratch, escalated, crystallized — produce strictly ordered `importance` (skill ≥ teacher ≥ scratch); all three salience entry points return identical scores for identical inputs.

### Tests for User Story 1 (write first, must FAIL before impl) ⚠️

- [X] T003 [P] [US1] Unit test `value()` ordering table in `tests/unit/test_value_ordering.py`: assert `value(SUCCEEDED, crystallized=True) ≥ value(SUCCEEDED, escalated=True) ≥ value(SUCCEEDED) > value(FAILED) ≥ value(UNVERIFIED)`; zero in any factor floors significance (product form). (significance.contract Invariant 3, SC-002)
- [X] T004 [P] [US1] Single-definition test in `tests/integration/test_single_salience.py` (DB-backed — `recompute()`/`bump()` need a connection, so integration not unit): for random `(prediction_error, value, retrieval_count)`, assert `salience()`, the `recompute()` path, and `bump_retrieval_count()` path all yield the identical score — no divergent formula remains. (significance.contract Invariant 1, SC-001)
- [X] T005 [P] [US1] Integration test live-value in `tests/integration/test_bookmark_value.py` (uses `migrated_conn`): write three episodes with equal PE/use differing only in escalated/crystallized; assert stored `importance` strictly ordered and `count(*) WHERE importance=1.0` on new rows ≈ 0. (Acceptance 2/3)

### Implementation for User Story 1

- [X] T006 [US1] In `fenrir/memory/salience.py` add `value(verdict, *, escalated, crystallized) -> float = base(verdict) × (W_ESCALATED if escalated else 1) × (W_CRYSTALLIZED if crystallized else 1)`, `base(SUCCEEDED)=1.0 / FAILED=W_FAIL / UNVERIFIED=W_UNVERIFIED`, reading weights from settings. (significance.contract Interface)
- [X] T007 [US1] In `fenrir/memory/salience.py` make `recompute()` (line 20) and `bump_retrieval_count()` (line 32) **call** `salience()` instead of inline SQL arithmetic — delete the line 24–25 (`COALESCE(...,0.5)`) and line 38–40 (`retrieval_count + 2` off-by-one) duplicate formulas so there is one definition; keep the Python `salience()` signature (line 14). (significance.contract Invariant 1; fixes 1.0-vs-0.5 drift + off-by-one)
- [X] T008 [US1] In `fenrir/core.py` **move the episode write to after the crystallize step** (currently write at line 173, crystallized known at line 179) and pass `importance=value(verdict, escalated=escalated, crystallized=crystallized)` into `Episode`, so `value()` is computed once with all three signals at write time — single write, single definition, no post-write recompute, deterministic. (Resolves the research R1 crystallized-timing note; significance.contract Invariant 2)
- [X] T009 [US1] Verify `fenrir/memory/episodes.py` `Episode.importance` (line 17–23) + `write_episode` (line 26) store the passed value and compute salience via the shared `salience()` (line 29) — no change expected beyond confirming it no longer relies on the `1.0` default; adjust only if it inlines arithmetic.

**Checkpoint**: A is mergeable. Single salience definition, live value ordering, no inert 1.0. **STOP and VALIDATE** per quickstart §A.

---

## Phase 4: User Story 2 — B: Passive forgetting via decay (Priority: P2)

**Goal**: effective significance fades with age at read time; stored bookmark immutable (additive); reactivation reverses fade; anchors exempt; rate tunable + observable.

**Independent Test**: two equal-salience rows, advance simulated `now`, reactivate one — idle `effective_salience` strictly lower; anchor row flat at any age; decayed rows still fully queryable; reactivation bounces effective back to stored.

### Tests for User Story 2 (write first, must FAIL before impl) ⚠️

- [X] T010 [P] [US2] Unit test decay math in `tests/unit/test_decay.py`: `effective_salience()` monotonic in age, equals stored salience at age 0, halves at `DECAY_HALFLIFE_DAYS`; NULL `last_reactivated_at` falls back to `created_at`. (decay.contract Invariant 2)
- [X] T011 [P] [US2] Integration test in `tests/integration/test_decay_behavior.py` (`migrated_conn`): equal-salience pair → idle < reactivated; decayed row still `SELECT`-returns in full (no delete/hide, SC-004); reactivation resets age; Python `effective_salience` and the SQL expression agree within float tolerance. (decay.contract Tests, Acceptance 1/2/5)
- [X] T012 [P] [US2] Integration test anchor-exemption in `tests/integration/test_anchor_no_decay.py`: an `long_term_memory` row `is_anchor=true, decay_rate=0` is unchanged at arbitrary age; STM carries no anchors. (decay.contract Invariant 3, SC-003)

### Implementation for User Story 2

- [X] T013 [US2] Write migration `infra/migrations/0004_consolidation_replay.sql` following the `-- NNNN_name.sql — desc` header + idempotent (`IF NOT EXISTS`) convention of 0001–0003: `ALTER TABLE short_term_memory ADD COLUMN IF NOT EXISTS last_reactivated_at timestamptz;` — nullable, NO default, NO backfill, NO drop/cascade; restate the D1 additive invariant in the header. (decay.contract Invariant 6, FR-012)
- [X] T014 [US2] **HUMAN-CONFIRM GATE (Constitution XII)**: present `0004` diff for explicit human approval before any apply; do not apply to <host> until confirmed. Record confirmation in the task note. — **CONFIRMED + APPLIED 2026-06-28**: javier approved; applied to live `fenrir_core` via `<host>` (ALTER ADD COLUMN `last_reactivated_at timestamptz` nullable + `schema_migrations` row `0004` recorded so the B image deploy skips re-apply). Verified column present + tracked.
- [X] T015 [US2] In `fenrir/memory/salience.py` add pure `effective_salience(salience, last_reactivated_at, created_at, *, now) -> float = salience × exp(-ln2 × age_days / DECAY_HALFLIFE_DAYS)`, `age_days = (now - COALESCE(last_reactivated_at, created_at))` fractional days; never mutate stored salience. Provide the matching SQL expression (decay.contract SQL form) as a module constant/string for reuse by consolidation + dashboard so Python and SQL stay identical. (decay.contract Interface, Invariant 1)
- [X] T016 [US2] In `fenrir/memory/retrieval.py` (`retrieve()` line 34, episode_ids line 59) set `last_reactivated_at = now()` for surfaced episodes (alongside the existing `bump_retrieval_count` call from core.py:126) — reactivation feeds reversibility. (decay.contract Invariant 4, FR-009)
- [X] T017 [P] [US2] In `dashboard/provisioning/dashboards/learning.json` add a timeseries panel "effective_salience vs episode age" using the postgres `fenrir_core` read-only datasource + the shared decay SQL expression (T015). (FR-011, SC-007 curve b)

**Checkpoint**: B mergeable after A. Idle < active, anchors flat, nothing deleted, reactivation reverses, decay panel renders. **STOP and VALIDATE** per quickstart §B.

---

## Phase 5: User Story 3 — C: Consolidation as competitive replay over clusters (Priority: P3)

**Goal**: replace top-K scan→copy with cluster → weighted-with-replacement replay → merge each cluster into ONE abstraction with replay-accrued strength; per-cluster gate + over-merge guard; additive + idempotent; pool-isolated.

**Independent Test**: K near-duplicates + noise → exactly 1 abstraction linked to all K; strength = draws × STRENGTH_PER_REPLAY; higher-significance cluster gets more draws under fixed seed; regressing cluster skipped; incoherent cluster split; re-run is a no-op; eval pool never read.

### Tests for User Story 3 (write first, must FAIL before impl) ⚠️

- [X] T018 [P] [US3] Unit test weighted sampling in `tests/unit/test_replay_sampling.py`: seeded `random` with-replacement draw over weighted clusters is reproducible (fixed seed → same draw sequence), higher-weight cluster gets ≥ draws, terminates under fixed budget even when few clusters / budget > mass (edge case). (consolidation.contract Invariant 3/8)
- [X] T019 [P] [US3] Integration test merge-to-one in `tests/integration/test_cluster_merge.py` (`migrated_conn`): seed K near-duplicate verified successes + unrelated noise (training pool, with embeddings) → exactly ONE `long_term_memory` row, `array_length(source_memories,1)=K`; sources marked `consolidated`, zero deletions. (SC-005, FR-015/020)
- [X] T020 [P] [US3] Integration test strength + competition in `tests/integration/test_replay_strength.py`: abstraction `strength = draws × STRENGTH_PER_REPLAY` and `reinforcement_count = draws` (not constant 0.5); hi-significance cluster shows ≥ `reinforcement_count` than lo under same seed. (SC-005/006, FR-016)
- [X] T021 [P] [US3] Integration test gates in `tests/integration/test_replay_gates.py`: a deliberately-regressing cluster is skipped (members stay `raw`); a two-distinct-method cluster is split, not collapsed (over-merge guard). (FR-017/018, Acceptance 4)
- [X] T022 [P] [US3] Integration test idempotency + pool isolation in `tests/integration/test_replay_idempotent.py`: re-run pass → no new/duplicate abstractions, zero deletions; an eval-pool row present in DB is never read (assert via guard/query). Extends existing `test_consolidation_gate.py`/`test_no_episode_delete.py` coverage. Also assert the **empty-candidate** path (all episodes below `EFFECTIVE_SALIENCE_FLOOR` / no raw rows) returns a successful empty `{merged:0,...}` run, not an error. (SC-004/009, FR-020/021; spec edge cases L161-162)
- [X] T022b [P] [US3] Integration test **reuse instrumentation** in `tests/integration/test_abstraction_reuse.py`: insert a consolidated `long_term_memory` abstraction, run `retrieve()` on a query semantically near it, assert (a) the abstraction is surfaced in the retrieved set, and (b) a countable reuse signal is recorded that the reuse panel (T030) reads. This is the headline SC-008 metric — its data path must exist before the panel can show a non-flat curve. (SC-008, FR-013-adjacent)

### Implementation for User Story 3

- [X] T023 [US3] Rewrite `fenrir/consolidation/sleep.py` `run(conn, *, replay_budget=None, seed=None) -> dict` per consolidation.contract Algorithm: (1) candidate query — `consolidation_status='raw'` AND `effective_salience ≥ EFFECTIVE_SALIENCE_FLOOR`, training/held-out pool only (replaces the line 96–102 `ORDER BY salience DESC LIMIT` scan). Returns `{clusters, merged, replays, drift_flagged, skipped_gate, seed}`.
- [X] T024 [US3] In `sleep.py` add greedy agglomerative clustering by `embedding` cosine ≥ `CLUSTER_SIM_FLOOR`; over-merge guard splits any cluster whose internal max pairwise cosine distance > `COHERENCE_MAX_SPREAD` back to singletons before gating. O(n²) acceptable at hundreds-scale. (consolidation.contract Algorithm 2/3, FR-013/018)
- [X] T025 [US3] In `sleep.py` per-cluster predictability gate: call existing `predictability_improves(conn, member_ids)` (line 38, `avg_pe<0.9`) on the full member set before first merge; fail → skip cluster, members stay `raw`. (consolidation.contract Algorithm 4, FR-017)
- [X] T026 [US3] In `sleep.py` competitive replay: seed stdlib `random` (`seed` arg or logged random), weight each surviving cluster by Σ member `effective_salience` (reuse T015 helper), draw `REPLAY_BUDGET` times with replacement; ties broken by cluster id for determinism. (consolidation.contract Algorithm 5, FR-014, SC-006)
- [X] T027 [US3] In `sleep.py` merge-to-one + strength accrual: first draw → INSERT one `long_term_memory` (`source_memories`=all member ids, `strength=STRENGTH_PER_REPLAY`, `reinforcement_count=1`, `memory_type='semantic'`, `abstraction_level≥2`); subsequent draws → `strength += STRENGTH_PER_REPLAY`, `reinforcement_count += 1`, `last_reinforced_at=now()`. Note: current insert (line 115–118) writes constant `strength=0.5` and no `reinforcement_count` — replace it. (consolidation.contract Algorithm 5, FR-015/016)
- [X] T028 [US3] In `sleep.py` on each draw refresh members' `short_term_memory.last_reactivated_at=now()` (feeds B reversibility); after merges mark sources `consolidated` + `consolidated_at` (keep line 122–126 additive UPDATE, never delete); keep `_drift_flag()` (line 129) unchanged per FR-019. (consolidation.contract Algorithm 6/7, FR-019/020)
- [X] T028b [US3] **Reuse instrumentation (G1 — fixes the SC-008 headline data gap).** In `fenrir/memory/retrieval.py` (`retrieve()` line 34) add a lane that surfaces `long_term_memory` consolidated abstractions (today `retrieve()` reads only `skills` + `short_term_memory`, so abstraction reuse is never observed) and record a countable per-abstraction reuse signal each time one is applied to a later task. Prefer a no-schema sink (reuse the 002 retrieval-event mechanism behind the existing "retrieval share" panel, scoped to `memory_type='semantic'`/`abstraction_level≥2`); **if no countable sink exists without a column, STOP and surface it** — a second additive column is a fresh Constitution-XII human-confirm decision, not an autonomous add. Feeds the T030 reuse curve. (SC-008)
- [X] T029 [US3] Log the replay `seed` (+ effective `replay_budget`) on the `consolidation_runs` row via the existing run-note/level path (data-model.md §consolidation_runs) so a pass is reproducible for audit — no new column. (research Cross-cutting reproducibility)
- [X] T030 [P] [US3] In `dashboard/provisioning/dashboards/learning.json` add two panels: (a) "abstraction strength vs reinforcement_count", (b) "reuse rate of consolidated abstractions over time" (the headline compounding curve) reading the reuse signal recorded in T028b. Same `fenrir_core` read-only datasource. (SC-007 curves a/c, SC-008)

**Checkpoint**: C mergeable after A+B. K→1 with full source list, strength accrues, competition monotonic, gate+guard reject bad merges, re-run no-op, pool isolated. **STOP and VALIDATE** per quickstart §C.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T031 [P] Run the full quickstart.md validation on <host> (`ssh <host>`) for A, B, C in order; record pass/fail per section.
- [ ] T032 [P] Confirm scope discipline (Constitution XI / FR-023): `git diff` touches only `fenrir/memory/`, `fenrir/consolidation/`, `fenrir/core.py` (write relocation + value), `fenrir/settings.py`, `infra/migrations/0004_*`, `dashboard/.../learning.json`, `tests/` (and bookkeeping `specs/003-*/` + `BACKLOG.md`, which are exempt from the source-scope fence). Verifier/oracle (`fenrir/verify*`), budget, sandbox untouched (FR-022).
- [ ] T033 [P] Run `scripts/spec_snapshot.py --write` to refresh the BACKLOG.md implementation snapshot with 003 task count.
- [ ] T034 Full suite green on <host> (real Docker + testcontainers): `pytest tests/unit tests/integration` — all new + existing suites pass.

---

## Dependencies & Execution Order

### Phase / story dependencies

- **Setup (Phase 1)**: no dependency — start immediately. T001, T002 parallel.
- **No Phase 2** (A is the foundation).
- **US1 / A (Phase 3)**: after Setup. The MVP. Blocks B and C (both weight on the bookmark).
- **US2 / B (Phase 4)**: after US1 merged (decay multiplies the A salience). T013→T014 (human gate)→apply; T015 independent of migration; T016/T017 after T015.
- **US3 / C (Phase 5)**: after US1 + US2 (effective_salience helper T015 is reused by replay weighting). Within: T023→T024→T025→T026→T027→T028 sequential (same file `sleep.py`); T028b (retrieval.py — reuse instrumentation) independent of the sleep.py chain, parallel; T029 after T027; T030 after T028b (needs the reuse signal).
- **Polish (Phase 6)**: after all desired stories.

### Within each story

- Tests written and FAILING before implementation.
- Same-file tasks are sequential (all `sleep.py` impl tasks T023–T028); cross-file tasks marked [P].

### Parallel opportunities

- Setup: T001 ∥ T002.
- All test tasks within a story are [P] (distinct files): {T003,T004,T005}; {T010,T011,T012}; {T018,T019,T020,T021,T022,T022b}.
- Dashboard panel tasks (T017, T030) [P] with their story's impl.
- Polish T031/T032/T033 [P].

---

## Parallel Example: User Story 3 tests

```bash
# Launch all US3 test tasks together (distinct files):
Task: "Unit test weighted sampling in tests/unit/test_replay_sampling.py"
Task: "Integration test merge-to-one in tests/integration/test_cluster_merge.py"
Task: "Integration test strength+competition in tests/integration/test_replay_strength.py"
Task: "Integration test gates in tests/integration/test_replay_gates.py"
Task: "Integration test idempotency+pool isolation in tests/integration/test_replay_idempotent.py"
```

---

## Implementation Strategy

### MVP first (User Story 1 / A only)

1. Phase 1 Setup (T001–T002).
2. Phase 3 US1 (T003–T009): one salience definition + live value.
3. **STOP and VALIDATE** quickstart §A — single definition, value ordering, no inert 1.0.
4. Merge A on its own (independently valuable: fixes the standing correctness bug).

### Incremental delivery

1. Setup → A → validate → merge (MVP, the bookmark bug fix).
2. B (decay) → human-confirm 0004 → validate → merge (reversible forgetting + panel).
3. C (competitive replay) → validate → merge (the prize: generalization + reuse curve).
4. Each increment mergeable alone; B/C assume A.

---

## Notes

- [P] = different file, no incomplete dependency.
- One migration only (0004), human-confirmed before apply (Constitution XII) — T014 is a hard gate.
- A and C add NO schema (live LTM/STM columns already carry strength/reinforcement_count/source_memories/is_anchor).
- Eval pool never read or mutated (FR-021/SC-009) — asserted in T022.
- Verifier/oracle, budget cap, sandbox untouched (FR-022/023) — confirmed in T032.
- Reuse instrumentation (T028b) must land before the T030 reuse panel — without surfacing LTM abstractions in `retrieve()`, the curve is structurally flat regardless of learning (analyze G1). A flat curve *after* instrumentation is an accepted, honestly-reported negative result (SC-008).
- Commit after each task or logical group; stop at each checkpoint to validate the story independently.

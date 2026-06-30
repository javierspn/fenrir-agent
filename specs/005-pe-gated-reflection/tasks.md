# Tasks: PE-gated meta-reflection (005)

**Feature**: `005-pe-gated-reflection` | **Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

Tests-first per story. `[P]` = parallelizable (different file, no incomplete dep). Stories are
independently testable. Deploy/<host> tasks (migration apply, dashboard) are split out at the end,
like 004's T021–T026 — they need live prod + human confirmation (XII).

Reuse, don't rebuild: `fenrir.predict.prediction_error`, the budget proxy egress + graceful
suppression (`fenrir/llm/`, the `refused` branch), `fenrir.skills.{admit,crystallize}` + skill
versioning, `fenrir.memory.episodes`. New code is one module + one wiring point + one migration.

---

## Phase 1: Setup

- [X] T001 Add the four tunables to `fenrir/settings.py`: `REFLECT_ENABLED=True`, `REFLECT_PE_LOW=0.3`, `REFLECT_PE_HIGH=0.5`, `REFLECT_EDIT_PE_MAX=0.75`, `REFLECT_MODEL_ROLE="reflector"`; validate `REFLECT_PE_LOW <= REFLECT_PE_HIGH` at load (FR-011, R1/R2).
- [X] T002 [P] Write additive migration `infra/migrations/0007_reflection.sql` per [data-model.md](data-model.md): `tasks.reflection_tier/reflection_outcome/reflection_skill_id` (+CHECKs, FK no-cascade, index `tasks_reflection_tier`) and the `reflections` table (+indexes). One tx, idempotent (`IF NOT EXISTS`). Do NOT apply here (deploy task T024).

**Checkpoint**: settings + migration exist; `curriculum`/loop untouched. Stories can proceed.

---

## Phase 2: Foundational (blocks all stories)

- [X] T003 Create `fenrir/reflect.py` skeleton: `tier(pe, s) -> str` (pure) and `reflect(conn, ctx) -> ReflectResult` stub (returns tier only), with `ReflectCtx`/`ReflectResult` shapes per [contracts/reflect.md](contracts/reflect.md). No writes yet.
- [X] T004 [P] Add `tests/unit/test_reflect.py` scaffolding + `tests/integration/test_reflect_loop.py` scaffolding (fixtures: settings, a fake/recording proxy, pgvector container marker `FENRIR_STACK_UP`).

**Checkpoint**: module + test files importable; `tier()` callable.

---

## Phase 3: User Story 1 — Reflection effort tracks surprise (Priority: P1) 🎯 MVP

**Goal**: PE gate with `none`/`cheap` behavior + per-task audit column, wired into the loop.
**Independent test**: run a mixed-PE cohort → tiers track PE; `none` makes no LLM call.

- [X] T005 [P] [US1] Unit: `tier(pe, escalated, s)` — `escalated→full` regardless of PE (F1); else `PE<0.3→none`, `0.3≤PE<0.5→cheap`, `PE≥0.5→full`, inclusive-up; determinism; settings rejects `LOW>HIGH` (FR-001). Assert `{escalated}∪{pe>=HIGH}` matches today's crystallize predicate (SC-008). Must fail first.
- [X] T006 [P] [US1] Unit: `none` tier ⇒ `llm_called==False` and NO `reflections` row, only `tasks.reflection_tier='none'` (FR-002, SC-002). Must fail first.
- [X] T007 [P] [US1] Unit: `cheap` tier ⇒ no LLM call, writes a `reflections` row with a templated note + `tasks.reflection_tier='cheap'` (FR-003, R4). Must fail first.
- [X] T008 [US1] Implement `reflect()` `none`/`cheap` branches + the `tasks` reflection-column write (own statement, committed independently of the task row). Honor `REFLECT_ENABLED` off-switch.
- [X] T009 [US1] Wire `reflect(conn, ctx)` into `fenrir/core.run_iteration` AFTER the task UPDATE+commit (step 7) and AFTER crystallize (step 8), BEFORE the episode write (step 9); build `ReflectCtx` from existing locals (R6). A reflect failure must not roll back the task (FR-012).
- [X] T010 [US1] Integration: a `--run` over mixed-PE tasks records one tier per task; tier distribution correlates with PE; per-task average reflection cost flat as low-PE volume grows (SC-001, SC-002).

**Checkpoint**: gate live; low-surprise tasks add zero model cost; today's behavior preserved on `none`.

---

## Phase 4: User Story 2 — High-PE reflection improves the skill library (Priority: P1)

**Goal**: `full` tier runs one budgeted LLM pass → skill edit-or-create, with suppression + guards.
**Independent test**: high-PE win adjacent to a skill → new version; cold/large-PE → new skill.

- [X] T011 [P] [US2] Unit: edit-vs-create rule — verified win + matched `retrieval_skill_id` + PE<`REFLECT_EDIT_PE_MAX`(0.95)→`edited`; cold or PE≥max→`created` (FR-005, R3). Include a PE=0.92 matched case to prove the edit path is reachable on the live bimodal distribution (U3). Must fail first.
- [X] T012 [P] [US2] Unit: `full` on unverified/failed verdict ⇒ lesson recorded, `outcome='none'`, NO skill write (FR-006, II/IV). Must fail first.
- [X] T013 [P] [US2] Unit: budget refused ⇒ downgrade to cheap note, `outcome='suppressed'`, zero spend, iteration completes (FR-007, IX, R5). Must fail first.
- [X] T014 [P] [US2] Unit: `is_eval=True` ⇒ tier recorded but NO skill write/edit/consolidate at any PE (FR-009, III). Must fail first.
- [X] T015 [US2] Implement `full` branch in `reflect()`: one proxy call via `REFLECT_MODEL_ROLE` to extract the lesson; route through the budget proxy with the `refused`→suppressed path (reuse escalation pattern). Assert reflection writes NO verdict/selection — it never grades its own output or influences task choice (FR-008, VIII; C5).
- [X] T016 [US2] Implement the **create** path: reuse `fenrir.skills.crystallize.make_candidate` + `admit.admit` (self_test admission) so `full` subsumes today's crystallization create-trigger (R2 — no double-write; crystallize step 8 now flows through reflect).
- [X] T017 [US2] Implement the **edit** path: write a NEW skill version for `retrieval_skill_id` via existing skill versioning (VII); prior version retained; link `reflection_skill_id` + `reflections.skill_id`.
- [X] T018 [US2] Guard order in `reflect()`: `is_eval` read-only short-circuit FIRST, then verified-win check, then edit/create; wrap body so any error ⇒ `outcome='none'`, never raises (FR-012).
- [X] T019 [US2] Integration: high-PE win adjacent to a seeded skill ⇒ new version; cold high-PE ⇒ new skill; tiny `DAILY_BUDGET_USD` ⇒ `suppressed`; eval batch ⇒ zero skill mutation (SC-003, SC-004, SC-005, SC-006).

**Checkpoint**: surprise turns into skill edits/creates within budget; held-out stays clean.

---

## Phase 5: User Story 3 — The gate is observable and honest (Priority: P2)

**Goal**: complete the audit so every task's tier + outcome is queryable; flat renders plainly.

- [X] T020 [P] [US3] Ensure `reflections` rows carry `prediction_error`, `tier`, `outcome`, `skill_id`, `created_at`; `tasks.reflection_outcome`/`reflection_skill_id` populated for `full` (FR-010).
- [X] T021 [P] [US3] Add the per-cohort tier-vs-PE SQL from [quickstart.md](quickstart.md) to the repo (e.g. `dashboard/queries/reflection_tiers.sql` or quickstart-referenced) for the later board cut; verify it runs read-only via `grafana_ro` (SC-001/SC-007).
- [X] T022 [US3] Integration: a cohort with no high-PE events records all `none`/`cheap`, zero `full`, no error — a legible recorded negative (SC-007, FR-014).
- [X] T023 [US3] Off-switch integration: `REFLECT_ENABLED=false` ⇒ verdicts + throughput identical to pre-feature; crystallization still fires via the wrapped path (SC-008).

**Checkpoint**: verdict legible per cohort; off-state proven inert.

---

## Phase 6: Polish & cross-cutting

- [X] T024 [P] Document the 5 tunables + the reflection tiers in `OPS.md` (and `infra/.env.example` if thresholds are env-exposed); note the bimodal-PE rationale (R1).
- [X] T025 Run the full pre-push gate: `ruff check .`, `mypy fenrir`, `pytest tests/unit tests/integration -k reflect`, `python3 scripts/spec_coverage.py`, `python3 scripts/spec_snapshot.py --check` — all green.

---

## Deploy / <host> (live prod — human-confirmed, XII; separate from code)

- [X] T026 [US3] Apply migration `0007` on <host> **after human confirmation** (XII): `git pull`, recompose `fenrir --build`, `python -m fenrir.db migrate`; verify the new columns + `reflections` table exist and are empty.
- [X] T027 [US3] Run a live `--run 50` cohort; confirm with the T021 SQL that tiers populate and at least one `edited`/`created` appears on a high-PE cohort (SC-001/SC-004 in prod).
- [X] T028 [US3] Add the reflection-tier per-cohort panel to the engineer "Learning" dashboard (ragnarok `learning.json`) and mirror to cosmos (datasource `fenrir_core`→`fenrir-pg`); flat renders plainly (SC-007). No new board.

---

## Dependencies & order

- Setup (T001–T002) → Foundational (T003–T004) → US1 (T005–T010) → US2 (T011–T019) → US3 (T020–T023) → Polish (T024–T025) → Deploy (T026–T028).
- US1 is the MVP (gate + none/cheap + wiring). US2 adds the payoff (full + edit/create). US3 is read-back. US2 depends on US1's `reflect()` + wiring; US3 depends on US1/US2 writes.
- **Story independence**: US1 testable alone with thresholds set so nothing reaches `full`. US3 is pure read-back.

## Parallel opportunities

- T002 ∥ T001; T004 ∥ T003.
- Unit tests T005–T007 (US1) parallel; T011–T014 (US2) parallel.
- T020 ∥ T021; T024 ∥ code tasks.

## FR / SC coverage

- FR-001→T005; FR-002→T006/T010; FR-003→T007; FR-004→T015; FR-005→T011/T016/T017; FR-006→T012;
  FR-007→T013/T015; FR-008→T015 (explicit no-verdict/no-selection assertion); FR-009→T014/T018; FR-010→T020;
  FR-011→T001; FR-012→T009/T018; FR-013→(additive, T002); FR-014→T022.
- SC-001→T010/T021; SC-002→T006/T010; SC-003→T019; SC-004→T019/T027; SC-005→T014/T019;
  SC-006→T013/T019; SC-007→T022/T028; SC-008→T023.

## Suggested MVP

**US1 (T001–T010)**: the PE gate + none/cheap + loop wiring + audit column — the smallest slice that
makes reflection effort track surprise and is measurable. US2 (the edit/create payoff) is the
fast-follow that delivers compounding value.

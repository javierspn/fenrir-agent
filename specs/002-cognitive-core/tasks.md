---
description: "Task list for 002-cognitive-core implementation"
---

# Tasks: Cognitive Core Loop (math pilot) — 002

**Input**: Design documents in `specs/002-cognitive-core/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md
**Tests**: INCLUDED — the feature's deliverable is an instrumented, verified measurement; every user
story has an Independent Test and success criteria (SC-001..010), so test tasks are first-class.
**Organization**: by user story (US1/US2 = P1 MVP; US3/US4/US5 = P2). Reuses the live 01-infra
substrate; the only schema change is the additive `0003` migration.

## Format: `[ID] [P?] [Story?] Description`
- **[P]**: parallelizable (different files, no incomplete-task dependency)
- **[Story]**: US1..US5 (user-story phases only)
- All paths are repo-root-relative.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: dependencies, settings, package skeletons, new runtime surfaces wired into the stack.

- [x] T001 [P] Add runtime deps to `pyproject.toml`: `anthropic`, `fastapi`, `uvicorn[standard]`, `redis` (keep existing `sympy`/`httpx`/`psycopg`)
- [x] T002 [P] Extend `fenrir/settings.py` with cognitive knobs (research.md R1–R11): `SMALL_MODEL=qwen2.5`, `EMBED_MODEL=nomic-embed-text`, `TEACHER_MODEL=claude-opus-4-8`, `ESCALATE_CONFIDENCE=0.55`, `CRYSTALLIZE_PE=0.5`, `CONSOLIDATION_EVERY_N_ITERS=50`, `HELDOUT_FRACTION=0.1`, `RETRIEVAL_SIM_FLOOR=0.80`, `PROXY_LOCAL_SLOTS=2`, `SANDBOX_TIMEOUT=10`
- [x] T003 [P] Create `fenrir/sandbox/Dockerfile.sandbox` — minimal `python:3.12-slim` + `sympy`, non-root, read-only rootfs, no network tooling
- [x] T004 [P] Create package skeletons (`__init__.py`) for `fenrir/{memory,consolidation,skills,llm,verify,sandbox}/`
- [x] T005 Add a `fenrir` service to `infra/docker-compose.yml` (loop + proxy; expose `:8080` on the internal network only; mount `/var/run/docker.sock` for sandbox spawning; `depends_on: [postgres, redis]`; `restart: unless-stopped`; NO neo4j)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: substrate every user story needs — migration, proxy, budget, sandbox, verifier, retrieval, salience/episodes.

**⚠️ CRITICAL**: no user-story work begins until this phase is complete.

- [x] T006 Author `infra/migrations/0003_cognitive_core.sql` — additive columns `tasks.solve_path` + `tasks.retrieval_skill_id` (FK, no cascade), `short_term_memory.importance` + `retrieval_frequency`, `benchmark_tasks.held_out`, partial index `idx_benchmark_held_out`; record version `0003` (data-model.md)
- [x] T007 Apply `0003` via `python -m fenrir.db migrate` (human-confirmed, Constitution XII) and extend `tests/integration/test_schema.py` + `test_migrations.py` to assert the five columns, the index, and `schema_migrations` row `0003`
- [x] T008 [P] Implement `fenrir/llm/budget.py` — redis fast counter + Postgres `budget_tracking` source-of-truth (rehydrate on restart, D10); pre-call gate refuses frontier when `spend + projected ≥ daily_budget_usd`, never raises cap
- [x] T009 Implement `fenrir/llm/router.py` — route `model_class=small`→Ollama `qwen2.5`, `model_class=frontier`→Anthropic `claude-opus-4-8` (adaptive thinking, `effort:"high"`, no `budget_tokens`/sampling); compute frontier `cost_usd` from usage (depends on T002)
- [x] T010 Implement `fenrir/llm/proxy.py` — FastAPI `POST /llm` + `GET /healthz`; semaphore (`PROXY_LOCAL_SLOTS`), per-call timeout, budget gate via T008 (depends on T008, T009) — contract: `contracts/llm-proxy.contract.md`
- [x] T011 [P] Implement `fenrir/sandbox/runner.py` — spawn ephemeral `--network none` container from `fenrir-sandbox` image, CPU/mem/time caps, return `SandboxResult` (depends on T003) — contract: `contracts/sandbox.contract.md`
- [x] T012 Implement `fenrir/verify/sympy_oracle.py` — symbolic-equivalence verdict `succeeded|failed|unverified`, executed inside the sandbox via T011 (depends on T011) — contract: `contracts/verifier.contract.md`
- [x] T013 [P] Implement `fenrir/memory/retrieval.py` — lexical `ts_rank_cd(content_fts,…)` + vector pgvector cosine over both memory tables + skills; applicability at `RETRIEVAL_SIM_FLOOR` (contract: `contracts/retrieval.contract.md`)
- [x] T014 [P] Implement `fenrir/memory/salience.py` — `salience = prediction_error × importance × retrieval_frequency`; bump `retrieval_frequency` on retrieval (depends on T006)
- [x] T015 [P] Implement `fenrir/memory/episodes.py` — additive `short_term_memory` episode writer (task, prediction, verdict, PE, solve-path join), computes salience via T014 (depends on T014)
- [x] T040 [P] Create `tests/integration/test_sandbox_isolation.py` — assert the `--network none` sandbox blocks egress and **fails closed** on any socket/DNS attempt; verdict process independent of solver (FR-011, Constitution X/VIII; depends on T011/T012) — *added post-`/speckit-analyze` (G1/X1)*

**Checkpoint**: substrate ready — user stories can begin.

---

## Phase 3: User Story 1 — Solve-verify-store one task end-to-end (Priority: P1) 🎯 MVP

**Goal**: one training task through predict → retrieve → solve(local) → sympy-verify → PE → additive episode, eval pool untouched.

**Independent Test**: feed one known training task, run one iteration; assert a prediction row written before the attempt, verdict solely from sympy, an episode with a PE value, zero evaluation-pool reads/writes (SC-001).

### Tests for User Story 1
- [x] T016 [P] [US1] `tests/integration/test_loop_heartbeat.py` — predict-before-solve, sympy-only success, episode persisted with PE (SC-001); also assert the **unverified** path (sympy times out/can't parse) records `unverified`, is excluded from success metrics, and does not crystallize (FR-015, edge case)
- [x] T017 [P] [US1] `tests/integration/test_verifier_independent.py` — success verdicts trace only to sympy; verifier process independent of solver (SC-002, FR-014)
- [x] T018 [P] [US1] `tests/integration/test_pool_no_leak.py` — selector reads only `pool='training'`; zero evaluation reads/writes (FR-001, III)

### Implementation for User Story 1
- [x] T019 [US1] Implement `fenrir/predict.py` — write `predicted_confidence` + predicted outcome BEFORE solving; compute `prediction_error` (verification delta + calibration gap) after verdict; update `confidence_calibration` (FR-004/005, depends on T012)
- [x] T020 [US1] Implement `fenrir/core.py` loop runner (one iteration): `select_task(training)` — selection predicate prefers **unsolved / under-practiced** tasks (no or low prior `tasks` attempts; never repeats trivially, FR-002) → predict (T019) → retrieve (T013) → solve via proxy `model_class=small` (T010) → verify in sandbox (T012) → PE → write episode (T015); set `tasks.solve_path` (depends on T010, T012, T013, T015, T019) — contract: `contracts/loop.contract.md`
- [x] T021 [US1] Add CLI entry `python -m fenrir.core --once` / `--run N` to `fenrir/core.py`; enforce ≥30% benchmark-sourced selection (FR-003)

**Checkpoint**: US1 fully functional — the irreducible heartbeat.

---

## Phase 4: User Story 2 — Crystallize a verified, executable, self-tested skill (Priority: P1)

**Goal**: high-PE solved task → skill as code + self_test, admitted only after an independent pass; next similar task solved via retrieval.

**Independent Test**: run a solved high-PE task through crystallization; assert a `skills` row `skill_kind='code'` + `self_test`, admitted only after the independent pass; a second similar task records `solve_path='retrieval'` (SC-003/009).

### Tests for User Story 2
- [x] T022 [P] [US2] `tests/integration/test_crystallize_admit.py` — admitted skills are code+self_test, `state='stable'` only after the independent pass; failing self_test → rejected (SC-003, US2.2)
- [x] T023 [P] [US2] `tests/integration/test_no_crystallize_lowpe.py` — zero crystallizations on correctly-predicted (low-PE) tasks (SC-006, IV)
- [x] T024 [P] [US2] `tests/integration/test_retrieval_solvepath.py` — second similar task → `solve_path='retrieval'`, `retrieval_skill_id` set (SC-009); also assert a **retrieved skill that fails verification** on the current task is recorded as a negative episode WITHOUT corrupting the skill's record (edge case)

### Implementation for User Story 2
- [x] T025 [P] [US2] Implement `fenrir/skills/crystallize.py` — distil high-PE verified solve into `skill_kind='code'` + `self_test` candidate via proxy crystallizer role (FR-022)
- [x] T026 [US2] Implement `fenrir/skills/admit.py` — independent pass (run code+self_test in sandbox via T011; re-solve originating task); admit→`stable` only on pass; version-before-modify (`skill_versions`); small PE→new version, large PE→new skill + `contradicts` edge in `graph_updates` (FR-023/024, depends on T011, T025)
- [x] T027 [US2] Wire crystallization into `fenrir/core.py` — gate on `prediction_error ≥ CRYSTALLIZE_PE` AND verified; never on low-PE; on retrieved-skill solve set `solve_path='retrieval'` + execute skill in sandbox (`kind=skill_apply`) (depends on T020, T026)

**Checkpoint**: US1 + US2 work — compounding mechanism in place.

---

## Phase 5: User Story 3 — Escalate to the frontier teacher only when stuck (Priority: P2)

**Goal**: low-confidence/cold/high-PE tasks route to `claude-opus-4-8` via the proxy; escalation rate-tracked; budget cap never exceeded.

**Independent Test**: force a low-confidence task → routes to teacher via proxy, `escalated=true`; a confident task does NOT escalate; with the daily cap exhausted, escalation is suppressed and `sum(cost_usd) ≤ daily_budget_usd` (SC-008).

### Tests for User Story 3
- [x] T028 [P] [US3] `tests/integration/test_escalation_budget.py` — low-conf escalates via proxy; confident does not; budget cap never exceeded; exhaustion suppresses escalation (SC-008, FR-010/012)

### Implementation for User Story 3
- [x] T029 [US3] Add the escalation router to `fenrir/core.py` — when small-model confidence < `ESCALATE_CONFIDENCE` OR cold retrieval: call proxy `model_class=frontier`, set `tasks.escalated=true`; suppress when the proxy refuses on budget exhaustion (depends on T010, T020)

**Checkpoint**: escalation-rate curve has its signal.

---

## Phase 6: User Story 4 — Regulated consolidation ("sleep") in salience order (Priority: P2)

**Goal**: on a cadence, process episodes salience-descending; merge an abstraction only if it improves a held-out (training-pool) set; sources marked consolidated, never deleted.

**Independent Test**: seed varied-salience episodes; run consolidation; assert salience-descending order, a non-improving abstraction rejected by the predictability gate, zero source episodes hard-deleted (SC-007).

### Tests for User Story 4
- [x] T030 [P] [US4] `tests/integration/test_consolidation_gate.py` — salience order; gate rejects non-improving merge; held-out drawn from training pool only; zero hard deletes (SC-007, III, V)

### Implementation for User Story 4
- [x] T031 [US4] Mark the held-out slice: set `benchmark_tasks.held_out=true` on `HELDOUT_FRACTION` of TRAINING-pool rows only (never evaluation) (depends on T006)
- [x] T032 [US4] Implement `fenrir/consolidation/sleep.py` — scan unconsolidated episodes salience-descending; build abstraction; predictability gate on held-out slice; merge → NEW `long_term_memory` row + `source_memories`; set `consolidated_at` (no delete); record `consolidation_runs` (depends on T015, T031) — contract: `contracts/consolidation.contract.md`
- [x] T033 [US4] Trigger consolidation from `fenrir/core.py` every `CONSOLIDATION_EVERY_N_ITERS` (depends on T020, T032)
- [x] T041 [US4] Implement anchor-based drift smoke-test in `fenrir/consolidation/sleep.py` — treat `long_term_memory.is_anchor=true` rows as non-decaying ground truth; after each merge, flag any abstraction that contradicts/warps away from an anchor (do not auto-delete — flag for human review) (FR-026; depends on T032) — *added post-`/speckit-analyze` (G2)*

**Checkpoint**: durable compounding memory in place.

---

## Phase 7: User Story 5 — Track everything on the learning dashboard (Priority: P2)

**Goal**: Grafana "Learning" dashboard shows the three curves + supporting panels via `grafana_ro`, with the contamination caveat.

**Independent Test**: with a cohort of completed iterations, all panels render real values via the read-only role; placeholder removed (SC-010).

### Implementation for User Story 5
- [x] T034 [US5] Replace `dashboard/provisioning/dashboards/learning.json` — three curves (cost/solved-task, escalation rate, retrieval-vs-from-scratch share) + episode/skill counts, pool occupancy, consolidation events, PE histogram; all SQL via `grafana_ro` (FR-027/029, SC-004, contract: `contracts/dashboard.contract.md`)
- [x] T035 [US5] Add the contamination caveat annotation to every accuracy/generalization panel (`contamination_unsafe`); verify panels render through `grafana_ro` only (FR-030, SC-010)

**Checkpoint**: the measurement is observable; flat escalation is a visible, valid negative result (SC-005).

---

## Phase 8: Polish & Cross-Cutting Concerns

- [x] T036 [P] Run `quickstart.md` end-to-end on <host> (apply migration → proxy/sandbox up → `--once` → cohort → all 9 integration suites green: heartbeat, verifier-independent, pool-no-leak, sandbox-isolation, crystallize-admit, no-crystallize-lowpe, retrieval-solvepath, escalation-budget, consolidation-gate)
- [x] T037 [P] `ruff` + `mypy` + `bandit` clean on all new `fenrir/` modules
- [x] T038 [P] Update `BACKLOG.md` next-session pointer → `/speckit-analyze` then `/speckit-implement`
- [x] T039 Confirm the contamination caveat is surfaced on ANY reported accuracy/generalization result, not just the dashboard (FR-030)

---

## Dependencies & Execution Order

### Phase dependencies
- **Setup (P1)**: no deps — start immediately.
- **Foundational (P2)**: after Setup — **BLOCKS all user stories**.
- **User Stories (P3+)**: after Foundational. US1→US2 share `core.py` (US2 wires into US1's loop). US3/US4 also extend `core.py` (sequence after US1 to avoid same-file churn). US5 is independent (dashboard JSON only).
- **Polish (P8)**: after desired stories complete.

### User-story dependencies
- **US1 (P1)**: after Foundational. The MVP.
- **US2 (P1)**: after US1 (wires crystallization into `core.py`).
- **US3 (P2)**: after US1 (adds escalation branch to `core.py`); independent of US2.
- **US4 (P2)**: after US1 (cadence trigger in `core.py`); independent of US2/US3.
- **US5 (P2)**: after US1 produces a cohort; otherwise independent (no `core.py` change).

### Parallel opportunities
- All `[P]` Setup tasks (T001–T004) together.
- Foundational `[P]` tasks T008, T011, T013, T014 run together; T015 after T014; T010 after T008+T009; T012 after T011.
- All `[P]` test tasks within a story run together (T016–T018; T022–T024).
- US5 (T034) can proceed in parallel with US3/US4 once US1 has produced data.

---

## Parallel Example: User Story 1

```bash
# Tests for US1 together:
Task: "test_loop_heartbeat.py"        # T016
Task: "test_verifier_independent.py"  # T017
Task: "test_pool_no_leak.py"          # T018
```

---

## Implementation Strategy

### MVP first (US1 + US2 = the P1 hypothesis core)
1. Phase 1 Setup → Phase 2 Foundational (CRITICAL — blocks all).
2. Phase 3 US1 → **STOP, validate** the heartbeat (SC-001/002) on <host>.
3. Phase 4 US2 → validate crystallization + retrieval reuse (SC-003/006/009). This is the minimum that can prove/falsify the thesis.

### Incremental delivery
US1 → US2 → US3 (escalation signal) → US4 (consolidation) → US5 (dashboard). Each adds a curve/mechanism without breaking the prior; a flat escalation curve at US3+ is a recorded negative result, not a regression.

---

## Notes
- `[P]` = different files, no incomplete-task dependency.
- Migration `0003` is human-confirmed (Constitution XII) — T007 is not autonomous.
- Verification always runs in the `--network none` sandbox (Constitution II/VIII/X).
- Commit after each task or logical group; PR per phase matches the repo's enforced flow.
- A flat escalation rate is a **valid negative result** — never "fix" it to pass a test.

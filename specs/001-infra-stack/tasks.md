---
description: "Task list for 001-infra-stack implementation"
---

# Tasks: Infrastructure Stack & Bootstrap (01-infra)

**Input**: Design documents from `/specs/001-infra-stack/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: INCLUDED — the spec's quickstart and plan explicitly define a pytest integration suite
mapping 1:1 to the Success Criteria (SC-001…SC-012). Each test is written to FAIL first.

**Organization**: Tasks grouped by user story (US1, US2, US3) for independent implementation/testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on incomplete tasks)
- **[Story]**: US1 / US2 / US3 (Setup, Foundational, Polish carry no story label)
- Paths are repo-root-relative; layout per plan.md (single project: `infra/`, `fenrir/`,
  `benchmark_loader/`, `dashboard/`, `tests/`).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project skeleton + dependency manifest.

- [x] T001 Create the source tree per plan.md: `infra/{migrations,seeds,backup}/`, `fenrir/bootstrap/`, `benchmark_loader/templates/`, `dashboard/provisioning/{datasources,dashboards}/`, `tests/integration/`
- [x] T002 [P] Create `infra/.env.example` listing all 6 required vars with placeholders only (DB_PASSWORD, GRAFANA_DB_RO_PASSWORD, GRAFANA_PASSWORD, ANTHROPIC_API_KEY, OLLAMA_HOST, OWNER_TELEGRAM_CHAT_ID) per env.contract.md / FR-019
- [x] T003 [P] Create `pyproject.toml` with the bootstrap/loader deps per research R13: `psycopg[binary]`, `httpx`, `datasets`, `huggingface-hub`, `pydantic-settings`, `sympy`, and dev deps `pytest`, `testcontainers`
- [x] T004 [P] Create thin package skeleton: `fenrir/__init__.py`, `fenrir/bootstrap/__init__.py` (no cognitive modules — plan Structure Decision)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Env validation, migration applier, and the baseline schema — every user story depends on these.

**⚠️ CRITICAL**: No user-story work begins until this phase is complete.

- [x] T005 Implement `fenrir/settings.py` — `pydantic-settings` BaseSettings loading the 6 required vars; missing/empty → raise naming the variable (FR-019/020, SC-008; research R9)
- [x] T006 Implement `fenrir/db.py` — psycopg connection + ordered-`.sql` migration applier: applies `infra/migrations/NNNN_*.sql` in lexical order, one transaction each, records applied version in `schema_migrations`, re-apply is a no-op (research R1; schema.contract.md)
- [x] T007 Write `infra/migrations/0001_baseline_schema.sql` — the authoritative **14 tables** from data-model.md with all columns/indexes: D1–D4 fields; `content_fts` generated tsvector + GIN on both memory tables (D5); `skills.skill_kind`+`self_test` (D6); D8 eval substrate (`eval_runs`, `tasks.{eval_run_id,is_eval,escalated}`, `benchmark_tasks.{contamination_safe,perturbation_of}`); `ivfflat` cosine indexes; salience-ordered index; `system_state`; `schema_migrations`; the `grafana_ro` read-only role (SELECT-only + `ALTER DEFAULT PRIVILEGES`); CHECK on `benchmark_tasks.pool`; CHECK on `graph_updates.trigger` (incl. `bootstrap_seed`) + UNIQUE`(from_node,relation_type,to_node)`; D1 no-`ON DELETE CASCADE` header comment (data-model.md, schema.contract.md, research R2/R2b/R4/R5/R11)
- [x] T008 Implement `tests/conftest.py` — testcontainers Postgres (pgvector) fixture for schema-level tests + a docker-compose fixture for stack-level tests (plan Testing)

**Checkpoint**: Schema applies cleanly to a fresh DB; env validation fails fast. User stories can begin.

---

## Phase 3: User Story 1 - Stand up the data stack from zero (Priority: P1) 🎯 MVP

**Goal**: One command brings up a healthy, persistent stack (relational+vector store, cache, dashboard); schema present; dashboard connects read-only; survives restart and power loss; nightly backup recoverable.

**Independent Test**: On a clean host with `.env` filled, `docker compose up -d` → all healthy; `test_schema` passes; dashboard connects as `grafana_ro`; hard-kill + restart loses no committed data; backup restores to identical counts.

### Tests for User Story 1 (write first, must FAIL)

- [x] T009 [P] [US1] `tests/integration/test_schema.py` — all 14 tables + required columns/indexes + `grafana_ro` role exist after migration (SC-002)
- [x] T010 [P] [US1] `tests/integration/test_no_episode_delete.py` — no FK cascade or schema path hard-deletes `short_term_memory`; stack contains 0 graph-DB services (SC-007)
- [x] T011 [P] [US1] `tests/integration/test_grafana_ro_readonly.py` — `grafana_ro` can SELECT; any INSERT/UPDATE/DELETE/DDL through it is rejected (SC-012)
- [x] T012 [P] [US1] `tests/integration/test_restart_persist.py` — `docker compose restart` preserves all stateful data; all services return healthy (SC-001, SC-006)
- [x] T013 [P] [US1] `tests/integration/test_power_loss.py` — `docker compose kill` mid-write + restart: committed rows intact, interrupted migration re-applies cleanly, and the budget counter equals the Postgres source of truth (reconciled, not double-counted) — assert the source-of-truth guarantee, AND that flushing the cache before restart still yields the correct counter (SC-010, FR-002a)
- [x] T014 [P] [US1] `tests/integration/test_backup_restore.py` — `pg_backup.sh` writes an artifact to a separate location; restoring into a fresh DB yields identical row counts (SC-009, FR-002b)
- [x] T015 [P] [US1] `tests/integration/test_env_failfast.py` — a missing required var causes a fast, named failure; no insecure default start (SC-008)

### Implementation for User Story 1

- [x] T016 [US1] `infra/docker-compose.yml` — services postgres(pgvector/pgvector:pg16), redis:7-alpine(`--appendonly yes --appendfsync everysec` — insurance only, non-authoritative), grafana(`grafana/grafana:11.4.0`, pinned — never `:latest`), one-shot benchmark-loader; **NO neo4j**; `restart: unless-stopped` on long-running services; healthchecks; named volumes `postgres_data`/`redis_data`/`grafana_data`; `fsync`/`synchronous_commit` left ON; comment: `postgres_data` on local fsync-honoring disk (FR-001/002/002a/003, SC-001/006/007; research R12)
- [x] T017 [P] [US1] `dashboard/provisioning/datasources/postgres.yaml` — datasource connecting as `grafana_ro` with `GRAFANA_DB_RO_PASSWORD`, never the owning role (FR-004/004a; research R10)
- [x] T018 [P] [US1] `dashboard/provisioning/dashboards/learning.json` — minimal "Learning" dashboard placeholder (existence + connection only; panels later) (FR-004)
- [x] T019 [P] [US1] `infra/backup/pg_backup.sh` — nightly `pg_dump` to a separate disk/host target (FR-002b, D10)

**Checkpoint**: MVP — the substrate exists, is healthy, durable, and read-only-observable, before any bootstrap data.

---

## Phase 4: User Story 2 - Idempotent bootstrap seeds the starting state (Priority: P1)

**Goal**: Bootstrap makes local models available, seeds anchors + starting relations, loads and partitions math benchmarks, and marks the system bootstrapped. Re-runs change nothing; interrupted runs resume.

**Independent Test**: On a fresh DB, `python -m fenrir.bootstrap` seeds 50–100 anchors, ≥20 relations, disjoint 70/30 pools, models available, marker set. Second run = zero row changes. Killed mid-run + re-run completes the rest without duplication.

### Tests for User Story 2 (write first, must FAIL)

- [x] T020 [P] [US2] `tests/integration/test_idempotency.py` — second full bootstrap run = identical row counts/contents across every table (SC-003); a marker-present run is a no-op; a partial run (no marker) resumes (FR-017/018); a simulated dataset-fetch failure leaves the system **un-bootstrapped** (no marker) so a retry completes it (spec edge case)
- [x] T021 [P] [US2] `tests/integration/test_anchors.py` — 50–100 anchors, 100% `is_anchor` at `strength=1.0`/`decay_rate=0`; a decay pass alters 0 (SC-004)
- [x] T022 [P] [US2] `tests/integration/test_pools_disjoint.py` — 0 problems in both pools AND realized training share 70% ±5pp (SC-005)
- [x] T023 [P] [US2] `tests/integration/test_models_available.py` — every required model (reasoning + embedding) responds to a probe via `OLLAMA_HOST` (SC-011, FR-013)
- [x] T024 [P] [US2] `tests/integration/test_relations_seed.py` — ≥20 `graph_updates` rows with `trigger='bootstrap_seed'`, endpoints resolved to anchor ids, idempotent on re-run (FR-015)

### Implementation for User Story 2

- [x] T025 [P] [US2] `infra/seeds/anchors_math.yaml` — 50–100 invariant math facts, each with a stable natural key (data-model Seeds; FR-014)
- [x] T026 [P] [US2] `infra/seeds/relations_seed.yaml` — ≥20 obvious starting relations referencing anchor natural keys (FR-015)
- [x] T027 [P] [US2] `fenrir/bootstrap/models.py` — pull `qwen2.5`, `llama3.1`, `nomic-embed-text` via `OLLAMA_HOST`; failure reports model/host and does NOT mark bootstrapped (FR-013; research R8)
- [x] T028 [P] [US2] `fenrir/bootstrap/anchors.py` — seed anchors from yaml: `is_anchor=TRUE, strength=1.0, decay_rate=0, memory_type='semantic', domain='mathematics'`, `INSERT … ON CONFLICT (natural_key) DO NOTHING` (FR-014)
- [x] T029 [US2] `fenrir/bootstrap/relations.py` — seed relations into `graph_updates` `trigger='bootstrap_seed'`; resolve endpoint natural keys → `long_term_memory.id`; `ON CONFLICT (from_node,relation_type,to_node) DO NOTHING` (FR-015) — depends on T028
- [x] T030 [P] [US2] `benchmark_loader/load.py` — download math datasets (GSM8K, MATH; Project Euler optional), partition by deterministic hash `% 100 < 70` → training else evaluation (disjoint), set `contamination_safe=FALSE`, populate `difficulty` from source level (FR-016, SC-005; research R7)
- [x] T031 [P] [US2] `benchmark_loader/Dockerfile` — one-shot loader image referenced by the compose `benchmark-loader` service
- [x] T032 [US2] `fenrir/bootstrap/__main__.py` — `python -m fenrir.bootstrap` entrypoint implementing bootstrap.contract sequence: **marker-gated global guard** (`system_state('bootstrapped')` present → exit 0, NOT row count) → models → anchors → relations → benchmarks → upsert marker; each sub-step independently idempotent (FR-012/017/018; bootstrap.contract.md) — depends on T027/T028/T029/T030

**Checkpoint**: Stack is seeded and measurable; bootstrap is idempotent and resumable.

---

## Phase 5: User Story 3 - Evolve the schema safely over time (Priority: P2)

**Goal**: Versioned migrations apply additively; existing files immutable; applied set tracked so nothing runs twice.

**Independent Test**: Apply to a fresh DB → baseline recorded. Apply again → no-op. Add a new migration → only it applies.

### Tests for User Story 3 (write first, must FAIL)

- [x] T033 [P] [US3] `tests/integration/test_migrations.py` — fresh apply records `0001`; second apply is a no-op (no version re-run); adding `0002` applies only `0002` and records it (US3 acceptance)

### Implementation for User Story 3

- [x] T034 [US3] `infra/migrations/0002_example_additive.sql` — a small additive sample migration (new column/index only, no destructive ops) proving the additive-evolution pattern end-to-end with the applier (FR-010 spirit)
- [x] T035 [US3] `infra/migrations/README.md` — document the immutability rule (never edit an applied migration; new structure ships only as a new `NNNN_*.sql`) (research R1, schema.contract.md)

**Checkpoint**: Schema can evolve safely; all three stories independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T036 [P] Wire `infra/backup/pg_backup.sh` to a systemd timer (or cron) unit + document the schedule and the separate backup target (D10)
- [x] T037 [P] Reserve the deferred eval-bench scaffolding: create `benchmark_loader/perturb.py` and `benchmark_loader/templates/.gitkeep` as **stubs marked NOT-built** (eval-bench sub-step / bootstrap 5b — spec Out of Scope; EVAL_PROTOCOL §7). Do not implement perturbation logic.
- [x] T038 [P] `README.md` — bring-up + migrate + bootstrap instructions mirroring quickstart.md
- [x] T039 Run `quickstart.md` end-to-end and confirm every SC check (SC-001…SC-012) passes on a clean host

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: depends on Setup; **blocks all user stories**.
- **US1 / US2 / US3 (Phases 3–5)**: each depends only on Foundational. US2's bootstrap and US1's compose both rely on the baseline schema (T007) and applier (T006). Stories are otherwise independently testable.
- **Polish (Phase 6)**: depends on US1+US2 (backup/quickstart) and US3 (migration docs).

### Key cross-task dependencies

- T006, T007 → everything (schema + applier).
- T008 (conftest) → all test tasks.
- T032 (bootstrap entrypoint) → T027, T028, T029, T030.
- T029 (relations) → T028 (anchors must exist to resolve endpoints).
- T013/T014/T012 (US1 durability/restart tests) → T016 (compose) + T019 (backup script).
- T033 (migration test) → T006 + T034.

### Parallel Opportunities

- Setup: T002, T003, T004 in parallel.
- US1 tests T009–T015 all [P]; US1 impl T017/T018/T019 [P] (T016 compose is the shared file — not [P]).
- US2 tests T020–T024 all [P]; US2 impl T025/T026/T027/T028/T030/T031 [P] (T029, T032 sequential).
- Once Foundational completes, **US1 and US2 can be built in parallel** (different file sets).

---

## Parallel Example: User Story 2

```bash
# Tests first (all fail), in parallel:
Task: "test_idempotency.py"  Task: "test_anchors.py"  Task: "test_pools_disjoint.py"
Task: "test_models_available.py"  Task: "test_relations_seed.py"

# Then independent impl files in parallel:
Task: "seeds/anchors_math.yaml"  Task: "seeds/relations_seed.yaml"
Task: "bootstrap/models.py"  Task: "bootstrap/anchors.py"
Task: "benchmark_loader/load.py"  Task: "benchmark_loader/Dockerfile"
# (relations.py after anchors.py; __main__.py last)
```

---

## Implementation Strategy

### MVP (User Story 1 only)

1. Phase 1 Setup → 2. Phase 2 Foundational (schema + applier) → 3. Phase 3 US1.
4. **STOP & VALIDATE**: stack healthy, schema present, read-only dashboard, survives restart + power-loss, backup restores.
5. This is a demonstrable substrate even before any seeded data.

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. US1 → durable, observable stack (MVP).
3. US2 → seeded + measurable (bootstrap).
4. US3 → safe schema evolution.
5. Polish → backup automation, README, full quickstart validation.

---

## Out of Scope (do NOT create tasks for)

- `perturb.py` perturbation logic, the contamination-safe **frozen eval set**, and the held-out
  `transfer` pool — deferred to the eval-bench sub-step (bootstrap 5b); EVAL_PROTOCOL M4 inactive
  until then (spec Out of Scope). T037 reserves stubs only.
- Cognitive logic, consolidation, LLM router/semaphore, sandboxes, the deferred Neo4j graph DB and
  curiosity curriculum (spec Out of Scope, D4).
- Multi-node `OLLAMA_HOST` node-list (D9 / BACKLOG P4.4).

---

## Notes

- [P] = different files, no incomplete dependency. [Story] = traceability to spec user stories.
- Write each test to FAIL before implementing its target.
- Commit after each task or logical group.
- Every task traces to a requirement/SC — cross-check against `/speckit-analyze` before `/speckit-implement`.

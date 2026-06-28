# Feature Specification: Infrastructure Stack & Bootstrap (01-infra)

**Feature Branch**: `001-infra-stack`

**Created**: 2026-06-24

**Status**: Approved (ready for `/speckit-tasks`)

**Input**: User description: "Feature 01-infra: the foundational infrastructure stack for Fenrir, brought up before any cognitive code (PROJECT_RAGNAROK.md §12, §13). Data stack + idempotent bootstrap; Neo4j deferred per constitution XI / D4; episodes additive; budget tracked from day one. Out of scope: cognitive logic, consolidation, LLM router, sandboxes."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Stand up the data stack from zero (Priority: P1)

The operator runs a single command on a fresh host and gets a running, persistent
data layer: a relational+vector store, a cache, and a metrics dashboard. Everything
the cognitive system will later depend on exists and is reachable, with no cognitive
code involved yet.

**Why this priority**: Nothing else in the project can be built or tested until the
data layer exists. This is the literal foundation (build order step 1).

**Independent Test**: On a clean machine with the prerequisites, bring the stack up;
confirm every service reports healthy and the database accepts connections. Delivers
value as a verifiable substrate even before bootstrap data exists.

**Acceptance Scenarios**:

1. **Given** a host with the container runtime and an `.env` filled from the template,
   **When** the operator brings the stack up, **Then** the vector store, cache, and
   dashboard all reach a healthy state and persist their data across a restart.
2. **Given** the stack is up, **When** the operator inspects the database, **Then**
   every entity defined in the data schema exists with the expected columns and
   indexes, including the prediction-error, salience, and retrieval-count fields.
3. **Given** the stack is up, **When** the operator opens the dashboard, **Then** it
   connects to the database through a **read-only** role (SELECT only) — a write attempt
   through that role is rejected.

---

### User Story 2 - Idempotent bootstrap seeds the starting state (Priority: P1)

The operator runs a bootstrap step that prepares the system's initial knowledge: it
makes the local reasoning/embedding models available, seeds the invariant reference
facts (anchors), loads and splits the benchmark problem sets, and marks the system as
bootstrapped. Running it a second time changes nothing.

**Why this priority**: Without seeded anchors and partitioned benchmarks, no learning
or evaluation can occur. Idempotency is required because bootstrap will be re-run on
every redeploy and must never corrupt or duplicate state.

**Independent Test**: Run bootstrap on a fresh database; verify anchors, benchmark
partitions, and the bootstrapped marker exist. Run it again; verify row counts and
state are byte-for-byte unchanged.

**Acceptance Scenarios**:

1. **Given** an empty long-term store, **When** bootstrap runs, **Then** 50–100
   invariant math anchors exist, each flagged as an anchor with maximum strength and
   exempt from decay.
2. **Given** an empty benchmark store, **When** bootstrap runs, **Then** the math
   datasets are loaded and partitioned into a training pool and an evaluation pool with
   no problem appearing in both.
3. **Given** a previously bootstrapped system, **When** bootstrap runs again, **Then**
   it detects the existing state and exits without adding, modifying, or deleting any
   rows.
4. **Given** bootstrap is interrupted partway, **When** it is re-run, **Then** it
   completes the remaining work without duplicating already-seeded data.

---

### User Story 3 - Evolve the schema safely over time (Priority: P2)

As later features need schema changes, the operator applies versioned migrations.
Existing migrations are never edited; new structure arrives only as new, ordered
migration files. The applied set is tracked so the same migration never runs twice.

**Why this priority**: The system is self-modifying and long-lived; schema history must
be auditable and reproducible. This is required before any feature mutates the schema,
but the initial stack can ship with just the baseline migration.

**Independent Test**: Apply migrations to a fresh database, then apply again; the second
run is a no-op. Add a new migration; only it applies.

**Acceptance Scenarios**:

1. **Given** a fresh database, **When** migrations are applied, **Then** the full
   baseline schema is created and recorded as applied.
2. **Given** an up-to-date database, **When** migrations are applied again, **Then**
   nothing changes and no existing migration file is re-executed.

---

### Edge Cases

- **Missing/invalid `.env`**: bootstrap and stack startup fail fast with a clear message
  naming the missing variable, never starting with insecure defaults.
- **Local model host unreachable**: bootstrap surfaces the failure to pull models and
  reports which model/host failed, rather than marking the system bootstrapped.
- **Benchmark source unavailable**: bootstrap reports the dataset that could not be
  fetched and leaves the system un-bootstrapped so a retry can complete it.
- **Partial seed already present** (anchors yes, benchmarks no): bootstrap completes the
  missing portion without re-seeding the present portion (per-section idempotency).
- **Anchor decay attempt**: any later process that tries to decay an anchor is a no-op;
  anchors remain at maximum strength.
- **Destructive-delete attempt on episodes**: the schema provides no path that
  hard-deletes source episodes (constitution VI / D1); only marking-consolidated and
  decay are possible.
- **Unexpected power-off mid-write**: on power return the host boots, services auto-restart, and
  the relational store replays its write-ahead log — committed data is intact, an interrupted
  migration rolls back and re-applies, and the budget counter is reconciled from the relational
  store (cache state is non-authoritative — a full cache loss is harmless). No manual recovery, no
  corruption, no silent budget over-count.

## Requirements *(mandatory)*

### Functional Requirements

**Stack & persistence**

- **FR-001**: The system MUST provide a reproducible, single-command bring-up of the
  full data stack: a relational store with vector-similarity support, a cache, and a
  metrics dashboard.
- **FR-002**: The system MUST persist all stateful data across restarts and redeploys.
- **FR-002a**: The system MUST survive an **unexpected power loss** with no loss of committed data
  and no manual recovery: the relational store relies on its crash-safe write-ahead log with
  synchronous commit enabled (never disabled); the cache is treated as **non-authoritative** (its
  only durability-critical value, the budget counter, has the relational store as source of truth
  and is **reconciled from it on restart**, so even a full cache loss loses zero durable data —
  cache AOF persistence, if enabled, is insurance only, never the source of truth); and every
  long-running service auto-restarts when the host powers back on.
- **FR-002b**: The system MUST take a periodic (at least nightly) backup of the relational store to
  a location separate from its primary volume, to recover from corruption, disk failure, or
  accidental volume deletion — cases a power-loss-safe WAL does not cover.
- **FR-003**: Each service MUST expose a health signal, and bring-up MUST be considered
  complete only when all services are healthy.
- **FR-004**: The dashboard MUST read metrics directly from the relational store.
- **FR-004a**: The dashboard MUST connect through a dedicated **read-only** role (SELECT only),
  provisioned in the baseline schema — never the owning/superuser role. Its credential is a
  distinct configuration value.

**Schema (per data schema §13)**

- **FR-005**: The system MUST create all entities defined in `data-model.md` (the authoritative
  list — 14 tables): short-term memory, long-term memory, skills, skill versions, tasks,
  meta-reflections, consolidation runs, budget tracking, graph-update audit, benchmark tasks,
  confidence calibration, eval runs (FR-005b), system state (FR-017), and the schema-migration
  tracking table.
- **FR-006**: Short-term memory MUST include the surprise/priority fields — a salience
  score, a prediction-error value, and a retrieval count — and MUST be indexed to allow
  salience-ordered selection (constitution IV/V, D2/D3).
- **FR-006a**: Both memory stores MUST carry a full-text index (a generated text-search column
  plus a matching index) over their content, providing the lexical-retrieval substrate for the
  later parallel-convergent selector (§5 lane 2). This feature ships the index only; the
  retrieval lane and its fusion/rerank are cognitive-phase scope.
- **FR-005a**: The `skills` entity MUST carry a skill-kind discriminator and a self-test field,
  so that later features can store skills as executable, self-verified code (D6). This feature
  ships the columns only; the verification/crystallization logic is cognitive-phase scope.
- **FR-005b**: The schema MUST provide the **evaluation substrate** (D8) so learning can later be
  measured on the dashboard: an `eval_runs` ledger (run id, arm, eval-set id, model/library
  version, accuracy), task tagging (`eval_run_id`, `is_eval`, `escalated`), and benchmark
  contamination flags (`contamination_safe`, `perturbation_of`). Tables/columns only; the eval
  harness and metrics are cognitive-phase (see `EVAL_PROTOCOL.md`). `is_eval = TRUE` tasks are
  read-only by contract — never consolidated (extends constitution III).
- **FR-007**: Tasks MUST record a pre-solve predicted confidence and a post-solve
  prediction-error value (D3).
- **FR-008**: Meta-reflections MUST record a prediction-error value and an update-mode
  field distinguishing edit-existing from create-new (reconsolidation, D3).
- **FR-009**: Long-term memory MUST support an anchor flag and a strength value, and
  anchors MUST be excluded from all decay (constitution; anchors never decay).
- **FR-010**: The schema MUST be additive with respect to episodes: there MUST be no
  operation, trigger, or cascade that hard-deletes source short-term episodes
  (constitution VI / D1). Consolidation marks them; it never deletes them.
- **FR-011**: Budget tracking MUST exist and be writable from day one, with a daily
  budget value and per-day usage counters (constitution IX).

**Bootstrap**

- **FR-012**: The system MUST provide an idempotent bootstrap that is safe to run
  repeatedly; on an already-bootstrapped system it MUST make no changes.
- **FR-013**: Bootstrap MUST make the required local reasoning and embedding models
  available before proceeding.
- **FR-014**: Bootstrap MUST seed 50–100 invariant math anchors, each flagged as an
  anchor, at maximum strength, exempt from decay.
- **FR-015**: Bootstrap MUST seed **at least 20** obvious starting relations among the seeded
  anchors (e.g. `is-a`, `prerequisite-of`, `generalizes`), sufficient to mitigate the empty-graph
  cold-start, WITHOUT introducing the deferred graph database. Stored as `graph_updates` rows
  (`trigger='bootstrap_seed'`) in Postgres.
- **FR-016**: Bootstrap MUST download the math benchmark datasets and partition them into
  a training pool (≈70%) and an evaluation pool (≈30%) such that no problem appears in
  both pools (constitution III). The realized training share MUST fall within **±5 percentage
  points** of 70%.
- **FR-017**: Bootstrap MUST record a durable "bootstrapped" marker (`system_state`) upon
  successful completion, and MUST treat **that marker** as the authoritative signal that bootstrap
  is already done. A populated long-term store alone MUST NOT be treated as completion — a partial,
  interrupted run leaves rows but no marker and MUST resume (FR-018).
- **FR-018**: Each bootstrap sub-step (models, anchors, relations, benchmarks) MUST be
  independently idempotent so an interrupted run resumes without duplication.

**Configuration & scope**

- **FR-019**: The system MUST provide an example configuration listing every required
  secret/setting: database (owner) password, the dashboard read-only DB password, the dashboard
  admin password, the external-API key, the local model host, and the owner notification chat
  identifier — with no real secret values.
- **FR-020**: Stack startup and bootstrap MUST fail fast with an actionable message when a
  required configuration value is missing.
- **FR-021**: The deferred graph database MUST NOT be part of the core stack
  (constitution XI / D4). Anchors stay; the graph does not.
- **FR-022**: The pilot scope is mathematics only; bootstrap MUST seed only math anchors
  and load only math benchmarks (constitution I).

### Key Entities *(include if feature involves data)*

- **Short-term memory**: a high-resolution recent experience; carries content,
  importance, **salience**, **prediction-error**, **retrieval-count**, and a
  consolidation status. Ordered by salience for downstream selection. Never hard-deleted.
- **Long-term memory**: a slowly-decaying episodic or semantic memory; carries strength,
  reinforcement count, decay behavior, abstraction level, and an **anchor** flag.
- **Anchor**: a special long-term memory representing an invariant truth (e.g. a fixed
  math fact); maximum strength, never decays; used later as a drift reference.
- **Skill / Skill version**: a stored procedure and its immutable version history
  (versioning is required before modification — constitution VII).
- **Task**: a unit of work; records source, pool (training/evaluation), pre-solve
  **predicted confidence**, and post-solve **prediction error**.
- **Meta-reflection**: the post-task learning record; carries **prediction error** and an
  **update-mode** (edit-existing / create-new / none).
- **Budget record**: per-day cost and usage with a daily cap.
- **Benchmark task**: a benchmark problem with its pool assignment and ground truth.
- **Confidence calibration**: per-domain predicted-vs-actual success used as a
  prediction-error signal.
- **System state**: the durable bootstrap marker (authoritative completion signal — FR-017).
- **Consolidation run**: a record of a (later) consolidation pass — counts, cost, insights.
  Substrate only; no consolidation logic in this feature.
- **Graph-update audit**: an append-only relation/edge log (no graph DB); also holds the
  bootstrap-seeded starting relations (FR-015, `trigger='bootstrap_seed'`).
- **Eval run**: a controlled measurement-run ledger (arm, eval-set, model/library version,
  accuracy) backing the learning dashboard (FR-005b; see `EVAL_PROTOCOL.md`).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From a clean host, a single bring-up command yields all services healthy in
  one attempt, with zero manual post-steps beyond filling configuration.
- **SC-002**: 100% of the defined schema entities and their required columns/indexes exist
  after migration — the **14 tables in `data-model.md`** (authoritative set) — verifiable by
  inspection, including salience, prediction-error, retrieval-count, predicted-confidence, and
  update-mode.
- **SC-003**: Running bootstrap a second time produces zero row changes across every table
  (identical counts and contents before and after).
- **SC-004**: After bootstrap, between 50 and 100 anchors exist, 100% flagged as anchors at
  maximum strength, and 0 are altered by a subsequent decay pass.
- **SC-005**: 0 problems appear in both the training and evaluation pools after partition, **and**
  the realized training share is 70% ±5 percentage points.
- **SC-006**: All stateful data survives a full stack restart (0 data loss).
- **SC-007**: The core stack contains 0 graph-database services (deferred), and 0 schema
  paths can hard-delete a source episode.
- **SC-008**: A missing required configuration value causes a fast, named failure 100% of
  the time (never a silent insecure start).
- **SC-009**: After the scheduled backup job runs, a backup artifact exists at a location
  separate from the primary volume, and restoring it into a fresh database yields identical row
  counts to the source (FR-002b).
- **SC-010**: After a hard-kill mid-write (simulated power loss) and auto-restart, 100% of
  committed rows are intact, an interrupted migration re-applies cleanly to the same end state,
  the cache rehydrates, and the budget counter is not double-counted (FR-002a) — 0 corruption, 0
  manual recovery.
- **SC-011**: After bootstrap, every required local model (reasoning + embedding) responds to a
  probe through `OLLAMA_HOST` (FR-013) — positive availability, not only the unreachable-host
  failure path.
- **SC-012**: The dashboard's database role can execute SELECT but a write (INSERT/UPDATE/DELETE
  or DDL) through that role is rejected 100% of the time (FR-004a).

## Assumptions

- A single host (<host> primary) runs the stack; multi-node overflow and the local model
  runner are external and reachable, not provisioned by this feature.
- The local model runner is already installed natively on the host (it runs outside the
  container stack for hardware access); bootstrap only pulls models into it.
- Benchmark datasets are publicly downloadable; "≈70/30" split tolerates dataset-level
  rounding as long as pools are disjoint.
- "Obvious starting relations" are stored within the relational store (not the deferred
  graph) for the pilot.
- The owner notification channel identifier is captured in configuration now even though
  the notification interface itself is out of scope.
- Exact decay/strength formulas, embedding dimensionality, and model identifiers follow
  the master design document and are settled at planning time, not in this spec.

## Out of Scope

- Cognitive logic (orchestration, context building, retry loop, meta-reflection runtime).
- Consolidation / "sleep" processing.
- The LLM router and semaphore.
- Execution sandboxes and the internal LLM proxy.
- The deferred knowledge-graph database and the curiosity curriculum (Phase 2, D4).
- Dashboards' specific panels (the dashboard exists and connects; panel design is later).
- The held-out **transfer** pool (`pool='transfer'`, EVAL_PROTOCOL M4): the column is reserved in
  schema, but the transfer set is built in the deferred eval-bench sub-step (bootstrap step 5b);
  M4 stays inactive until then. This feature seeds only training/evaluation.
- The contamination-safe **frozen eval set** (`perturb.py` + post-cutoff ingest, bootstrap step
  5b) — spec'd now, built when the eval harness is stood up.
- Multi-node model routing (a node list vs the single `OLLAMA_HOST`) — deferred per D9 (P4).

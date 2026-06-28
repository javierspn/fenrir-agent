# Phase 1 Data Model — Cognitive Core Loop (002)

**Principle: additive only.** The 01-infra `0001_baseline_schema.sql` already provisioned the D1–D8
columns this loop needs. This feature **reuses** them and adds **five columns across three tables** in
one human-confirmed migration. No drops, no `ON DELETE CASCADE`, no overwrite (Constitution VI/VII/XII).

---

## Entity ↔ table mapping (what already exists vs what's added)

### Task attempt / iteration → `tasks` (reuse + 2 additive columns)

One loop iteration reads/updates one `tasks` row. Existing columns cover almost all of it.

| Need (spec) | Column | Status |
|---|---|---|
| predicted confidence (before solve) | `predicted_confidence` | ✅ exists |
| prediction error (after verify) | `prediction_error` | ✅ exists |
| escalation flag | `escalated` (BOOLEAN) | ✅ exists |
| verifier verdict | `verified` + `status` | ✅ exists |
| model used / cost | `llm_used`, `tokens_used`, `cost_usd` | ✅ exists |
| pool guard | `benchmark_pool`, `benchmark_id`, `is_eval` | ✅ exists |
| **solve path (retrieval vs scratch)** | `solve_path` TEXT NULL | ➕ **add** |
| **which skill was applied** | `retrieval_skill_id` UUID NULL → `skills.id` | ➕ **add** |

`solve_path ∈ {retrieval, scratch}` (NULL until solved) is the raw material of the
retrieval-vs-from-scratch curve (FR-008/027). `retrieval_skill_id` is an optional FK (no cascade)
linking the attempt to the surfaced skill for SC-009 verification.

### Prediction → `tasks.predicted_confidence` + `tasks.prediction_error` (reuse) and `confidence_calibration` (reuse)

Predict-before-solve writes `predicted_confidence` (and a predicted outcome flag derivable from it)
**before** the attempt; after sympy verdict, `prediction_error` is computed (R5) and a
`confidence_calibration` bucket row is updated (existing table). No new columns.

### Episode (short-term, additive) → `short_term_memory` (reuse + 2 additive columns)

Every attempt persists one additive episode.

| Need (spec) | Column | Status |
|---|---|---|
| content / embedding / fts | `content`, `embedding` (768), `content_fts` | ✅ exists |
| salience | `salience` | ✅ exists |
| prediction error | `prediction_error` | ✅ exists |
| consolidated marker (no delete) | `consolidation_status`, `consolidated_at`, `consolidation_level_reached` | ✅ exists |
| task linkage | `task_id` | ✅ exists |
| **importance factor** | `importance` REAL DEFAULT 1.0 | ➕ **add** |
| **retrieval frequency factor** | `retrieval_frequency` INT DEFAULT 0 | ➕ **add** |

`salience = prediction_error × importance × retrieval_frequency` (FR-018, R6). `retrieval_frequency`
increments whenever the episode is surfaced by retrieval. Solve-path / escalation for the episode are
read from the joined `tasks` row (no duplication).

### Abstraction (long-term) → `long_term_memory` (reuse, no change)

Consolidation writes a **new** `long_term_memory` row (`memory_type`, `abstraction_level`,
`source_memories` UUID[] pointing back to the merged episodes, `strength`, `is_anchor=false`). The
predictability gate is logic, not schema. Sources are marked consolidated, never deleted (D1/VI).

### Skill → `skills` + `skill_versions` (reuse, no change)

Crystallized skill: `skill_kind='code'`, `self_test` populated, `state` lifecycle
(`draft→testing→stable`), `version`, `parent_skills`, `pending_evaluation`/`evaluate_at`. Admission
flips state to `stable` only after the independent pass (SC-003). Versioning writes a `skill_versions`
row before any change (VII). All columns already exist.

### Salience → derived (no table)

Computed from `prediction_error × importance × retrieval_frequency`, stored in
`short_term_memory.salience`; consolidation orders by it (the existing
`(consolidation_level_reached, salience DESC)` index serves the salience-descending scan).

### Escalation event → `tasks.escalated` + `tasks.cost_usd` + `budget_tracking` (reuse)

No separate table: an escalation is a `tasks` row with `escalated=true`, its `cost_usd`, and the
`budget_tracking` daily aggregate. The escalation-rate curve is `count(escalated)/count(*)` over time.

### Anchor → `long_term_memory.is_anchor` (reuse)

Seeded anchors (`is_anchor=true`, `decay_rate=0`) are the non-decaying drift smoke-test (FR-026). The
loop reads them; it never decays or merges them.

### Metric series → `tasks` + `consolidation_runs` + `eval_runs` (reuse)

All three curves reconstruct from existing per-iteration columns:
- **cost per solved task** ← `tasks.cost_usd` where `verified` over time
- **escalation rate** ← `tasks.escalated` over time
- **retrieval-vs-from-scratch share** ← the new `tasks.solve_path` over time

`consolidation_runs` records each sleep pass; `eval_runs` (arm `fenrir_full` / `rag_recall_only` /
`base_no_memory`) is available for later contrast but is not driven in this feature.

### Held-out gate set → `benchmark_tasks.held_out` (1 additive column)

| Need | Column | Status |
|---|---|---|
| pool membership | `pool ∈ {training, evaluation, transfer}` | ✅ exists |
| contamination caveat | `contamination_safe` | ✅ exists |
| **predictability-gate held-out slice** | `held_out` BOOLEAN DEFAULT false | ➕ **add** |

`held_out=true` is set on `HELDOUT_FRACTION` of **training-pool** rows only (R8). The gate evaluates
on these; the evaluation pool is never read (III).

---

## Additive migration — `infra/migrations/0003_cognitive_core.sql`

```sql
-- 0003_cognitive_core.sql  (additive only; human-confirmed per Constitution XII / FR-025)
-- Adds the five columns the cognitive loop needs on top of the 01-infra schema.
-- No drops, no ON DELETE CASCADE, no data rewrite.

BEGIN;

-- Iteration solve-path + applied-skill linkage (retrieval-vs-from-scratch curve, SC-009)
ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS solve_path TEXT
        CHECK (solve_path IN ('retrieval', 'scratch')),
    ADD COLUMN IF NOT EXISTS retrieval_skill_id UUID
        REFERENCES skills(id);            -- no ON DELETE CASCADE (D1/VI)

-- Salience factors the baseline schema didn't already carry (salience, prediction_error exist)
ALTER TABLE short_term_memory
    ADD COLUMN IF NOT EXISTS importance REAL NOT NULL DEFAULT 1.0,
    ADD COLUMN IF NOT EXISTS retrieval_frequency INTEGER NOT NULL DEFAULT 0;

-- Predictability-gate held-out slice, carved from the TRAINING pool only (Constitution III)
ALTER TABLE benchmark_tasks
    ADD COLUMN IF NOT EXISTS held_out BOOLEAN NOT NULL DEFAULT false;

-- Index to scan the held-out training slice cheaply during consolidation
CREATE INDEX IF NOT EXISTS idx_benchmark_held_out
    ON benchmark_tasks (pool, held_out) WHERE held_out = true;

INSERT INTO schema_migrations (version, name)
VALUES ('0003', 'cognitive_core_additive_columns')
ON CONFLICT (version) DO NOTHING;

COMMIT;
```

**Application**: via the existing `python -m fenrir.db migrate` applier. Because it touches schema, it
is applied with **human confirmation** (Constitution XII / FR-025) — not run autonomously by the loop.
The migration is idempotent (`IF NOT EXISTS`) and power-loss-safe (single transaction, D10).

---

## Invariants preserved

- **No hard delete of episodes** — consolidation only sets `consolidated_at`; the new `retrieval_skill_id`
  FK deliberately omits `ON DELETE CASCADE` (VI/D1, SC-007).
- **Eval pool isolation** — `held_out` lives only on training-pool rows; the loop's task selector filters
  `pool='training'` and never reads `pool='evaluation'` (III, FR-001).
- **Skill versioning** — every skill mutation writes `skill_versions` first; contradicts links go in
  `graph_updates`, no skill overwrite (VII, FR-024).
- **Additive growth** — five new columns, one new partial index, zero drops.

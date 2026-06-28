# Phase 1 Data Model: 01-infra

Authoritative column list for the baseline migration `0001_baseline_schema.sql`. Mirrors
PROJECT_RAGNAROK.md §13 with the D1–D4 additions called out as **(D#)**. All `embedding`
columns are `vector(768)` with an `ivfflat (… vector_cosine_ops)` index. Both memory tables
also carry a generated `content_fts tsvector` + `gin` index — the lexical substrate for the
§5 parallel-convergent selector's BM25-style lane (built now; the lane itself is cognitive-phase).

> **D1 invariant (constitution VI):** no table below uses `ON DELETE CASCADE` toward
> `short_term_memory`; no migration/trigger deletes episodes. Enforced + tested.

## short_term_memory
| column | type | notes |
|---|---|---|
| id | UUID PK | `gen_random_uuid()` |
| content | TEXT NOT NULL | |
| embedding | vector(768) | ivfflat cosine index |
| created_at | TIMESTAMPTZ | default now() |
| session_id, task_id | UUID | |
| domain | TEXT | |
| importance | FLOAT | default 0.5 |
| **salience** | FLOAT | **(D2/D3)** default 0.5; f(prediction_error, importance, retrieval_count) |
| **prediction_error** | FLOAT | **(D3)** NULL until task resolved |
| **retrieval_count** | INTEGER | **(D3)** default 0; feeds salience + emergent decay |
| consolidation_status | TEXT | default 'raw' |
| consolidation_level_reached | INTEGER | default 0 (0 raw,1 light,2 medium,3 deep) |
| consolidation_locked_at | TIMESTAMPTZ | optimistic lock, default NULL |
| consolidated_at | TIMESTAMPTZ | marker only — episode is NOT deleted (D1) |
| content_fts | tsvector | generated `to_tsvector('simple', content)` STORED; §5 lexical lane |

Indexes: `ivfflat(embedding vector_cosine_ops)`; `gin(content_fts)` (§5 lane 2 lexical);
`(consolidation_level_reached, created_at)`;
**`(consolidation_level_reached, salience DESC)` (D2 salience-ordered)**; `(domain)`.

## long_term_memory
| column | type | notes |
|---|---|---|
| id | UUID PK | |
| content | TEXT NOT NULL | |
| embedding | vector(768) | ivfflat cosine index |
| memory_type | TEXT NOT NULL | episodic \| semantic \| procedural_hint |
| domain | TEXT | |
| abstraction_level | INTEGER | default 1 (1 instance…4 meta) |
| strength | FLOAT | default 0.5 |
| reinforcement_count | INTEGER | default 1 |
| last_reinforced_at | TIMESTAMPTZ | default now() |
| decay_rate | FLOAT | default 0.01; **anchors = 0** |
| created_at | TIMESTAMPTZ | default now() |
| source_memories | UUID[] | provenance (additive lineage, D1) |
| is_anchor | BOOLEAN | default FALSE; **anchors TRUE, never decay** |
| content_fts | tsvector | generated `to_tsvector('simple', content)` STORED; §5 lexical lane |

Indexes: `ivfflat(embedding)`; `gin(content_fts)` (§5 lane 2 lexical);
`(memory_type, domain, strength)`; `(is_anchor)`.

## skills / skill_versions
`skills`: id, name UNIQUE, description, content (SKILL.md **or** executable code — D6),
**`skill_kind` ('code'|'text', default 'code')**, **`self_test`** (runnable check; §3 self-verify
gate — D6), embedding(768), domain, category,
state ('draft'|'testing'|'stable'|'deprecated'), abstraction_level, version, use_count,
success_count, failure_count, patch_count, strength, timestamps, created_by, parent_skills,
pending_evaluation, evaluate_at. Indexes: ivfflat(embedding); (state, domain, strength);
(pending_evaluation, evaluate_at).
`skill_versions`: id, skill_id→skills, version, content, state, strength, created_at,
created_by, change_reason. (Constitution VII — versioned before modification.)

## tasks
Standard §13 columns plus **(D3)**:
| column | type | notes |
|---|---|---|
| **predicted_confidence** | FLOAT | **(D3)** recorded BEFORE solving (Phase 1 prediction) |
| **prediction_error** | FLOAT | **(D3)** post-verification surprise; gates reflection + salience |
Others: id, content, domain, source ('user'|'curriculum'|'benchmark'), benchmark_id,
benchmark_pool, complexity, status, attempt_count, max_attempts, result, verified,
verification_method, llm_used, tokens_used, cost_usd, timestamps, skills_used[], memories_used[].
**(D8 eval substrate):** `eval_run_id UUID` (NULL = normal/training task), `is_eval BOOLEAN`
(TRUE = read-only measurement; consolidation MUST skip — extends constitution III),
`escalated BOOLEAN` (routed to big model; carries the **D7** escalation-rate metric on the **D8** eval substrate).
Indexes: (status, source, created_at); (benchmark_pool, domain); (eval_run_id).

## meta_reflections
| column | type | notes |
|---|---|---|
| id | UUID PK | |
| task_id | UUID → tasks | |
| succeeded | BOOLEAN | |
| confidence | FLOAT | |
| **prediction_error** | FLOAT | **(D3)** |
| **update_mode** | TEXT | **(D3)** edit_existing \| create_new \| none (reconsolidation) |
| failure_points | TEXT[] | |
| pattern, generalizable, skill_worthy, skill_name | | |
| memory_worthy, improves_existing_skill | | |
| meta_insight | TEXT | |
| created_at | TIMESTAMPTZ | |
| processed | BOOLEAN | default FALSE |

## consolidation_runs
id, level ('light'|'medium'|'deep'|'abstract'), started_at, completed_at,
memories_processed, skills_created, skills_patched, memories_elevated, memories_archived,
llm_used, cost_usd, insights TEXT[].

## budget_tracking  *(constitution IX — writable day one)*
id, date DATE default today UNIQUE, llm_cost_usd default 0, tasks_executed,
consolidations_run, daily_budget_usd default 2.00, concurrent_peak, rate_limit_hits.
`daily_budget_usd` is a **hard cap**, not projected spend (projected infra cost lives in
PROJECT_RAGNAROK §16).

## graph_updates  *(audit only — no Neo4j; relations live in Postgres, D4)*
id, trigger ('bootstrap_seed'|'meta_reflection'|'task_failure'|'consolidation_deep'), from_node UUID,
relation_type TEXT, to_node UUID, confidence FLOAT, created_at.
**Unique** `(from_node, relation_type, to_node)` so the FR-015 relation seed is idempotent
(`ON CONFLICT DO NOTHING`). `bootstrap_seed` is the trigger value for relations written at bootstrap.

## benchmark_tasks
id, benchmark TEXT, **pool TEXT ('training'|'evaluation'|'transfer')**, difficulty, domain,
content, ground_truth, used_count, last_used_at.
**(D8):** `contamination_safe BOOLEAN` (post-cutoff or perturbed → not in base-model pretraining),
`perturbation_of TEXT` (source template id if procedurally perturbed, else NULL).
**Invariant (constitution III):** a given problem id appears in exactly one pool.
**Note:** `pool='transfer'` is **reserved** for the held-out transfer sub-domain (EVAL_PROTOCOL M4).
01-infra bootstrap (step 5) seeds only `training`/`evaluation`; the `transfer` set is built in the
deferred eval-bench sub-step (bootstrap step 5b). **M4 is inactive until that set ships.**

## eval_runs  *(D8 — controlled measurement; see EVAL_PROTOCOL.md)*
| column | type | notes |
|---|---|---|
| id | UUID PK | |
| eval_set | TEXT NOT NULL | frozen set id, e.g. 'math_L4to5_holdout_v1' |
| arm | TEXT NOT NULL | base_no_memory \| fenrir_full \| rag_recall_only |
| model_id | TEXT NOT NULL | base model + version (model swap is visible) |
| library_sha | TEXT | skill-library snapshot at run time (NULL for base arm) |
| started_at, completed_at | TIMESTAMPTZ | |
| n_problems, n_correct | INTEGER | |
| accuracy | FLOAT | stored for fast dashboard reads |
| notes | TEXT | |
Index: (eval_set, arm, started_at). Holds NO problem content — pure run ledger; the Grafana
"Learning" dashboard reads accuracy-by-arm-over-time from here (FR-004).

## confidence_calibration  *(D3 signal source)*
domain, confidence_bucket, predicted_success, actual_success, sample_count, calibration_error.

## system_state  *(bootstrap marker)*
| column | type | notes |
|---|---|---|
| key | TEXT PK | e.g. 'bootstrapped' |
| value | TEXT | |
| updated_at | TIMESTAMPTZ | default now() |

## schema_migrations  *(migration tracking)*
| column | type | notes |
|---|---|---|
| version | TEXT PK | e.g. '0001' |
| name | TEXT | |
| applied_at | TIMESTAMPTZ | default now() |

## Roles (not tables)
- **grafana_ro** → a `LOGIN` role with **`GRANT SELECT` only** (no INSERT/UPDATE/DELETE/DDL),
  created in the baseline migration and used by the Grafana datasource (FR-004/FR-004a). Password
  from `GRAFANA_DB_RO_PASSWORD`. The owning/superuser role (`DB_PASSWORD`) is never wired to the
  dashboard. `GRANT SELECT ON ALL TABLES … ` + `ALTER DEFAULT PRIVILEGES … GRANT SELECT` so future
  tables stay readable.

## Seeds (not tables)
- **anchors_math.yaml** → 50–100 `long_term_memory` rows, `is_anchor=TRUE`, `strength=1.0`,
  `decay_rate=0`, `memory_type='semantic'`, `domain='mathematics'`. Each has a stable
  natural key for `ON CONFLICT DO NOTHING`.
- **relations_seed.yaml** → ≥20 obvious starting relations as `graph_updates` rows with
  `trigger='bootstrap_seed'` (NO graph DB). Endpoints are written as anchor **natural keys** and
  resolved to the `long_term_memory.id` of the matching anchor at seed time; idempotent via the
  `(from_node, relation_type, to_node)` unique key.

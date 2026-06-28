-- 0001_baseline_schema.sql — Fenrir 01-infra baseline (authoritative: data-model.md, 14 tables).
--
-- D1 INVARIANT (constitution VI): no table here uses ON DELETE CASCADE toward
-- short_term_memory, and no migration/trigger ever deletes a source episode.
-- Consolidation only MARKS episodes (consolidated_at) — it never removes them.
--
-- Idempotent: re-applying is a no-op (IF NOT EXISTS throughout); the applier also
-- records the version in schema_migrations so it never re-runs (research R1).

CREATE EXTENSION IF NOT EXISTS vector;

-- Migration tracker (applier also ensures this; kept here so a manual apply is whole).
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    TEXT PRIMARY KEY,
    name       TEXT,
    applied_at TIMESTAMPTZ DEFAULT now()
);

-- 1. short_term_memory ------------------------------------------------------
CREATE TABLE IF NOT EXISTS short_term_memory (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content                     TEXT NOT NULL,
    embedding                   vector(768),
    created_at                  TIMESTAMPTZ DEFAULT now(),
    session_id                  UUID,
    task_id                     UUID,
    domain                      TEXT,
    importance                  FLOAT DEFAULT 0.5,
    salience                    FLOAT DEFAULT 0.5,   -- (D2/D3)
    prediction_error            FLOAT,               -- (D3) NULL until task resolved
    retrieval_count             INTEGER DEFAULT 0,   -- (D3)
    consolidation_status        TEXT DEFAULT 'raw',
    consolidation_level_reached INTEGER DEFAULT 0,   -- 0 raw,1 light,2 medium,3 deep
    consolidation_locked_at     TIMESTAMPTZ,
    consolidated_at             TIMESTAMPTZ,         -- marker only — episode is NOT deleted (D1)
    content_fts                 tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED
);
CREATE INDEX IF NOT EXISTS stm_embedding_ivf  ON short_term_memory USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS stm_fts_gin        ON short_term_memory USING gin (content_fts);
CREATE INDEX IF NOT EXISTS stm_level_created  ON short_term_memory (consolidation_level_reached, created_at);
CREATE INDEX IF NOT EXISTS stm_level_salience ON short_term_memory (consolidation_level_reached, salience DESC);  -- (D2)
CREATE INDEX IF NOT EXISTS stm_domain         ON short_term_memory (domain);

-- 2. long_term_memory -------------------------------------------------------
CREATE TABLE IF NOT EXISTS long_term_memory (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content             TEXT NOT NULL,
    embedding           vector(768),
    memory_type         TEXT NOT NULL,              -- episodic | semantic | procedural_hint
    domain              TEXT,
    abstraction_level   INTEGER DEFAULT 1,          -- 1 instance .. 4 meta
    strength            FLOAT DEFAULT 0.5,
    reinforcement_count INTEGER DEFAULT 1,
    last_reinforced_at  TIMESTAMPTZ DEFAULT now(),
    decay_rate          FLOAT DEFAULT 0.01,         -- anchors = 0
    created_at          TIMESTAMPTZ DEFAULT now(),
    source_memories     UUID[],                     -- provenance (additive lineage, D1)
    is_anchor           BOOLEAN DEFAULT FALSE,      -- anchors TRUE, never decay
    natural_key         TEXT UNIQUE,                -- stable key for seed ON CONFLICT
    content_fts         tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED
);
CREATE INDEX IF NOT EXISTS ltm_embedding_ivf ON long_term_memory USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS ltm_fts_gin       ON long_term_memory USING gin (content_fts);
CREATE INDEX IF NOT EXISTS ltm_type_dom_str  ON long_term_memory (memory_type, domain, strength);
CREATE INDEX IF NOT EXISTS ltm_is_anchor     ON long_term_memory (is_anchor);

-- 3. skills -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS skills (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name               TEXT UNIQUE,
    description        TEXT,
    content            TEXT,                          -- SKILL.md or executable code (D6)
    skill_kind         TEXT DEFAULT 'code',           -- 'code' | 'text' (D6)
    self_test          TEXT,                          -- runnable check (D6)
    embedding          vector(768),
    domain             TEXT,
    category           TEXT,
    state              TEXT DEFAULT 'draft',          -- draft|testing|stable|deprecated
    abstraction_level  INTEGER DEFAULT 1,
    version            INTEGER DEFAULT 1,
    use_count          INTEGER DEFAULT 0,
    success_count      INTEGER DEFAULT 0,
    failure_count      INTEGER DEFAULT 0,
    patch_count        INTEGER DEFAULT 0,
    strength           FLOAT DEFAULT 0.5,
    created_at         TIMESTAMPTZ DEFAULT now(),
    updated_at         TIMESTAMPTZ DEFAULT now(),
    created_by         TEXT,
    parent_skills      UUID[],
    pending_evaluation BOOLEAN DEFAULT FALSE,
    evaluate_at        TIMESTAMPTZ,
    CONSTRAINT skills_kind_chk CHECK (skill_kind IN ('code', 'text'))
);
CREATE INDEX IF NOT EXISTS skills_embedding_ivf ON skills USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS skills_state_dom_str ON skills (state, domain, strength);
CREATE INDEX IF NOT EXISTS skills_pending_eval  ON skills (pending_evaluation, evaluate_at);

-- 4. skill_versions (constitution VII — versioned before modification) -------
CREATE TABLE IF NOT EXISTS skill_versions (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_id      UUID REFERENCES skills(id),
    version       INTEGER,
    content       TEXT,
    state         TEXT,
    strength      FLOAT,
    created_at    TIMESTAMPTZ DEFAULT now(),
    created_by    TEXT,
    change_reason TEXT
);

-- 5. tasks ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tasks (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content              TEXT,
    domain               TEXT,
    source               TEXT,                       -- user | curriculum | benchmark
    benchmark_id         TEXT,
    benchmark_pool       TEXT,
    complexity           TEXT,
    status               TEXT,
    attempt_count        INTEGER DEFAULT 0,
    max_attempts         INTEGER DEFAULT 3,
    result               TEXT,
    verified             BOOLEAN,
    verification_method  TEXT,
    llm_used             TEXT,
    tokens_used          INTEGER,
    cost_usd             FLOAT,
    created_at           TIMESTAMPTZ DEFAULT now(),
    updated_at           TIMESTAMPTZ DEFAULT now(),
    skills_used          UUID[],
    memories_used        UUID[],
    predicted_confidence FLOAT,                       -- (D3) recorded BEFORE solving
    prediction_error     FLOAT,                       -- (D3) post-verification surprise
    -- (D8 eval substrate)
    eval_run_id          UUID,                        -- NULL = normal/training task
    is_eval              BOOLEAN DEFAULT FALSE,       -- TRUE = read-only; consolidation MUST skip
    escalated            BOOLEAN DEFAULT FALSE        -- D7 escalation-rate metric on D8 substrate
    -- NOTE: no FK to short_term_memory with ON DELETE CASCADE (D1).
);
CREATE INDEX IF NOT EXISTS tasks_status_src     ON tasks (status, source, created_at);
CREATE INDEX IF NOT EXISTS tasks_pool_domain    ON tasks (benchmark_pool, domain);
CREATE INDEX IF NOT EXISTS tasks_eval_run       ON tasks (eval_run_id);

-- 6. meta_reflections -------------------------------------------------------
CREATE TABLE IF NOT EXISTS meta_reflections (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id                UUID REFERENCES tasks(id),
    succeeded              BOOLEAN,
    confidence             FLOAT,
    prediction_error       FLOAT,                     -- (D3)
    update_mode            TEXT,                      -- (D3) edit_existing|create_new|none
    failure_points         TEXT[],
    pattern                TEXT,
    generalizable          BOOLEAN,
    skill_worthy           BOOLEAN,
    skill_name             TEXT,
    memory_worthy          BOOLEAN,
    improves_existing_skill BOOLEAN,
    meta_insight           TEXT,
    created_at             TIMESTAMPTZ DEFAULT now(),
    processed              BOOLEAN DEFAULT FALSE,
    CONSTRAINT meta_update_mode_chk CHECK (update_mode IN ('edit_existing', 'create_new', 'none'))
);

-- 7. consolidation_runs -----------------------------------------------------
CREATE TABLE IF NOT EXISTS consolidation_runs (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    level              TEXT,                          -- light|medium|deep|abstract
    started_at         TIMESTAMPTZ,
    completed_at       TIMESTAMPTZ,
    memories_processed INTEGER,
    skills_created     INTEGER,
    skills_patched     INTEGER,
    memories_elevated  INTEGER,
    memories_archived  INTEGER,
    llm_used           TEXT,
    cost_usd           FLOAT,
    insights           TEXT[]
);

-- 8. budget_tracking (constitution IX — writable day one) --------------------
CREATE TABLE IF NOT EXISTS budget_tracking (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date              DATE DEFAULT CURRENT_DATE UNIQUE,
    llm_cost_usd      FLOAT DEFAULT 0,
    tasks_executed    INTEGER DEFAULT 0,
    consolidations_run INTEGER DEFAULT 0,
    daily_budget_usd  FLOAT DEFAULT 2.00,            -- hard cap, not projected spend
    concurrent_peak   INTEGER DEFAULT 0,
    rate_limit_hits   INTEGER DEFAULT 0
);

-- 9. graph_updates (audit only — no Neo4j; relations in Postgres, D4) --------
CREATE TABLE IF NOT EXISTS graph_updates (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trigger       TEXT NOT NULL,
    from_node     UUID,
    relation_type TEXT,
    to_node       UUID,
    confidence    FLOAT,
    created_at    TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT graph_trigger_chk CHECK (
        trigger IN ('bootstrap_seed', 'meta_reflection', 'task_failure', 'consolidation_deep')
    ),
    CONSTRAINT graph_edge_uniq UNIQUE (from_node, relation_type, to_node)
);

-- 10. benchmark_tasks -------------------------------------------------------
CREATE TABLE IF NOT EXISTS benchmark_tasks (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    benchmark          TEXT,
    problem_id         TEXT UNIQUE,                   -- stable id from source; partition key
    pool               TEXT,                          -- training | evaluation | transfer
    difficulty         TEXT,
    domain             TEXT,
    content            TEXT,
    ground_truth       TEXT,
    used_count         INTEGER DEFAULT 0,
    last_used_at       TIMESTAMPTZ,
    contamination_safe BOOLEAN DEFAULT FALSE,         -- (D8)
    perturbation_of    TEXT,                          -- (D8) source template id, else NULL
    CONSTRAINT bench_pool_chk CHECK (pool IN ('training', 'evaluation', 'transfer'))
);
CREATE INDEX IF NOT EXISTS bench_pool_domain ON benchmark_tasks (pool, domain);

-- 11. eval_runs (D8 — controlled measurement; EVAL_PROTOCOL.md) --------------
CREATE TABLE IF NOT EXISTS eval_runs (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    eval_set     TEXT NOT NULL,
    arm          TEXT NOT NULL,                       -- base_no_memory|fenrir_full|rag_recall_only
    model_id     TEXT NOT NULL,
    library_sha  TEXT,
    started_at   TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ,
    n_problems   INTEGER,
    n_correct    INTEGER,
    accuracy     FLOAT,
    notes        TEXT
);
CREATE INDEX IF NOT EXISTS eval_runs_set_arm ON eval_runs (eval_set, arm, started_at);

-- 12. confidence_calibration (D3 signal source) -----------------------------
CREATE TABLE IF NOT EXISTS confidence_calibration (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    domain            TEXT,
    confidence_bucket TEXT,
    predicted_success FLOAT,
    actual_success    FLOAT,
    sample_count      INTEGER,
    calibration_error FLOAT
);

-- 13. system_state (bootstrap marker — authoritative completion, FR-017) -----
CREATE TABLE IF NOT EXISTS system_state (
    key        TEXT PRIMARY KEY,                      -- e.g. 'bootstrapped'
    value      TEXT,
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- 14. schema_migrations: created above.

-- Read-only datasource role (FR-004a). Cluster-global; created once, granted
-- SELECT now + via ALTER DEFAULT PRIVILEGES for future tables. Password is set
-- from env by fenrir/db.py (not embeddable in static SQL).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grafana_ro') THEN
        CREATE ROLE grafana_ro NOLOGIN;
    END IF;
END $$;
GRANT USAGE ON SCHEMA public TO grafana_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO grafana_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO grafana_ro;

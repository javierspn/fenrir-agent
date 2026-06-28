"""SC-002 — all 14 tables + required columns/indexes + grafana_ro role exist."""
from __future__ import annotations

EXPECTED_TABLES = {
    "short_term_memory", "long_term_memory", "skills", "skill_versions", "tasks",
    "meta_reflections", "consolidation_runs", "budget_tracking", "graph_updates",
    "benchmark_tasks", "eval_runs", "confidence_calibration", "system_state",
    "schema_migrations",
}


def _cols(conn, table):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
            (table,),
        )
        return {r[0] for r in cur.fetchall()}


def test_all_14_tables_exist(migrated_conn):
    with migrated_conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        )
        present = {r[0] for r in cur.fetchall()}
    assert EXPECTED_TABLES <= present, EXPECTED_TABLES - present


def test_surprise_priority_columns(migrated_conn):
    stm = _cols(migrated_conn, "short_term_memory")
    assert {"salience", "prediction_error", "retrieval_count", "content_fts"} <= stm
    ltm = _cols(migrated_conn, "long_term_memory")
    assert {"is_anchor", "strength", "decay_rate", "content_fts", "natural_key"} <= ltm


def test_d6_d8_substrate_columns(migrated_conn):
    assert {"skill_kind", "self_test"} <= _cols(migrated_conn, "skills")
    assert {"eval_run_id", "is_eval", "escalated"} <= _cols(migrated_conn, "tasks")
    assert {"contamination_safe", "perturbation_of"} <= _cols(migrated_conn, "benchmark_tasks")


def test_key_indexes_exist(migrated_conn):
    with migrated_conn.cursor() as cur:
        cur.execute("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
        idx = {r[0] for r in cur.fetchall()}
    for needed in ("stm_fts_gin", "stm_level_salience", "ltm_fts_gin", "eval_runs_set_arm"):
        assert needed in idx, needed


def test_grafana_ro_role_exists(migrated_conn):
    with migrated_conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = 'grafana_ro'")
        assert cur.fetchone() is not None


def test_0003_cognitive_core_columns(migrated_conn):
    """002 (T007): the additive 0003 migration applied — solve_path/retrieval_skill_id on
    tasks, held_out on benchmark_tasks, the partial index, and the migration row."""
    assert {"solve_path", "retrieval_skill_id"} <= _cols(migrated_conn, "tasks")
    assert "held_out" in _cols(migrated_conn, "benchmark_tasks")
    with migrated_conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_indexes WHERE indexname = 'idx_benchmark_held_out'")
        assert cur.fetchone() is not None
        cur.execute("SELECT 1 FROM schema_migrations WHERE version = '0003'")
        assert cur.fetchone() is not None
        # retrieval_skill_id FK must NOT cascade-delete (D1/VI)
        cur.execute(
            "SELECT confdeltype FROM pg_constraint WHERE conname LIKE '%retrieval_skill_id%'"
        )
        row = cur.fetchone()
        assert row is None or row[0] != "c"   # 'c' = CASCADE; must not be cascade

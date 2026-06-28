"""US1 heartbeat (T016): predict-before-solve, sympy-only success, additive episode,
unverified excluded. SC-001/002, FR-004/015.
"""
from __future__ import annotations

from fenrir import core
from fenrir.memory import retrieval
from fenrir.verify import sympy_oracle


def _seed_benchmark(conn, problem_id, pool, content, gt):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO benchmark_tasks (benchmark, problem_id, pool, difficulty, domain, "
            " content, ground_truth) VALUES ('gsm8k', %s, %s, 'easy', 'math', %s, %s)",
            (problem_id, pool, content, gt),
        )
    conn.commit()


def _patch_externals(monkeypatch, answer):
    def fake_proxy(task_id, model_class, prompt, role="solver"):
        if "CONFIDENCE" in prompt:
            return {"text": "CONFIDENCE: 0.9", "model": "qwen2.5", "cost_usd": 0.0}
        return {"text": f"ANSWER: {answer}", "model": "qwen2.5", "cost_usd": 0.0}

    monkeypatch.setattr(core, "proxy_call", fake_proxy)
    # verify via the pure sympy verdict (no docker in CI)
    monkeypatch.setattr(core, "verify_in_sandbox",
                        lambda c, g: sympy_oracle.verdict(c, g))
    # cold retrieval (no Ollama embeddings)
    monkeypatch.setattr(retrieval, "retrieve",
                        lambda conn, q, limit=5: retrieval.Retrieved())


def test_heartbeat_predict_solve_verify_store(migrated_conn, monkeypatch):
    conn = migrated_conn
    _seed_benchmark(conn, "train-1", "training", "2+2", "4")
    _seed_benchmark(conn, "eval-1", "evaluation", "9+9", "18")
    _patch_externals(monkeypatch, answer="4")

    res = core.run_iteration(conn)
    assert res is not None

    with conn.cursor() as cur:
        cur.execute(
            "SELECT predicted_confidence, verified, status, prediction_error, benchmark_id "
            "FROM tasks ORDER BY created_at DESC LIMIT 1"
        )
        conf, verified, status, pe, bench_id = cur.fetchone()
        assert conf is not None        # prediction recorded BEFORE solving (FR-004)
        assert verified is True and status == "succeeded"   # sympy-confirmed (SC-002)
        assert pe is not None          # prediction error computed (FR-005)
        assert bench_id == "train-1"   # training pool only (FR-001)

        cur.execute("SELECT count(*) FROM short_term_memory WHERE prediction_error IS NOT NULL")
        assert cur.fetchone()[0] >= 1  # additive episode with PE (FR-016)

        # evaluation pool provably untouched (SC-001, III)
        cur.execute("SELECT count(*) FROM tasks WHERE benchmark_id = 'eval-1'")
        assert cur.fetchone()[0] == 0


def test_unverified_not_a_success(migrated_conn, monkeypatch):
    """sympy can't parse → unverified, excluded from success (FR-015, edge case)."""
    conn = migrated_conn
    _seed_benchmark(conn, "train-u", "training", "weird", "???")
    _patch_externals(monkeypatch, answer="???")

    core.run_iteration(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT status, verified FROM tasks ORDER BY created_at DESC LIMIT 1")
        status, verified = cur.fetchone()
    assert status == "unverified" and verified is False


def test_textually_plausible_but_wrong_is_failed(migrated_conn, monkeypatch):
    """Wrong math answer → failed regardless of confidence (US1.3, FR-013)."""
    conn = migrated_conn
    _seed_benchmark(conn, "train-w", "training", "2+2", "4")
    _patch_externals(monkeypatch, answer="5")
    core.run_iteration(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT status, verified FROM tasks ORDER BY created_at DESC LIMIT 1")
        status, verified = cur.fetchone()
    assert status == "failed" and verified is False

"""US2 (T024): a similar task is solved via retrieval/skill-application (solve_path
recorded); a retrieved skill that fails on the current task becomes a negative episode
without corrupting the skill record. SC-009, edge case.
"""
from __future__ import annotations

from fenrir import core
from fenrir.memory import retrieval
from fenrir.verify import sympy_oracle


def _seed(conn, pid, content, gt):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO benchmark_tasks (benchmark, problem_id, pool, difficulty, domain, "
            " content, ground_truth) VALUES ('gsm8k', %s, 'training', 'easy', 'math', %s, %s)",
            (pid, content, gt),
        )
    conn.commit()


def _seed_skill(conn):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO skills (name, content, skill_kind, self_test, state, version, strength, "
            " created_by) "
            "VALUES ('s_apply','def solve():return 4','code','t','stable',1,0.7,'seed') "
            "RETURNING id, content, version"
        )
        row = cur.fetchone()
    conn.commit()
    return str(row[0]), row[1], row[2]


def _patch(monkeypatch, skill_id, answer):
    def fake_proxy(task_id, model_class, prompt, role="solver"):
        if "CONFIDENCE" in prompt:
            return {"text": "CONFIDENCE: 0.9", "model": "qwen2.5", "cost_usd": 0.0}
        return {"text": f"ANSWER: {answer}", "model": "qwen2.5", "cost_usd": 0.0}

    monkeypatch.setattr(core, "proxy_call", fake_proxy)
    monkeypatch.setattr(core, "verify_in_sandbox", lambda c, g: sympy_oracle.verdict(c, g))
    monkeypatch.setattr(
        retrieval, "retrieve",
        lambda conn, q, limit=5: retrieval.Retrieved(
            top_skill=retrieval.SkillHit(skill_id, "s_apply", 0.95, 0.0)
        ),
    )


def test_similar_task_solved_via_retrieval(migrated_conn, monkeypatch):
    conn = migrated_conn
    _seed(conn, "r-1", "2+2", "4")
    skill_id, _, _ = _seed_skill(conn)
    _patch(monkeypatch, skill_id, answer="4")

    res = core.run_iteration(conn)
    assert res["solve_path"] == "retrieval"
    with conn.cursor() as cur:
        cur.execute(
            "SELECT solve_path, retrieval_skill_id FROM tasks ORDER BY created_at DESC LIMIT 1"
        )
        sp, rsid = cur.fetchone()
    assert sp == "retrieval" and str(rsid) == skill_id


def test_retrieved_skill_failure_is_negative_episode_not_corruption(migrated_conn, monkeypatch):
    conn = migrated_conn
    _seed(conn, "r-2", "2+2", "4")
    skill_id, orig_content, orig_version = _seed_skill(conn)
    _patch(monkeypatch, skill_id, answer="5")   # wrong → fails verification

    core.run_iteration(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM tasks ORDER BY created_at DESC LIMIT 1")
        assert cur.fetchone()[0] == "failed"
        # negative episode recorded
        cur.execute("SELECT count(*) FROM short_term_memory")
        assert cur.fetchone()[0] >= 1
        # the retrieved skill record is UNCHANGED (not corrupted)
        cur.execute("SELECT content, version FROM skills WHERE id=%s", (skill_id,))
        content, version = cur.fetchone()
    assert content == orig_content and version == orig_version

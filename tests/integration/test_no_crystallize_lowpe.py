"""US2 (T023): crystallization fires ONLY on high-PE tasks; zero on tasks the system
already predicted correctly (low PE). SC-006, Constitution IV.
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


def test_low_pe_correct_prediction_does_not_crystallize(migrated_conn, monkeypatch):
    conn = migrated_conn
    _seed(conn, "lp-1", "2+2", "4")
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO skills (name, content, skill_kind, self_test, state, version, strength, "
            " created_by) "
            "VALUES ('s_seed','def solve():return 4','code','t','stable',1,0.5,'seed') "
            "RETURNING id"
        )
        skill_id = str(cur.fetchone()[0])
    conn.commit()

    def fake_proxy(task_id, model_class, prompt, role="solver"):
        # high confidence + correct → low prediction error
        if "CONFIDENCE" in prompt:
            return {"text": "CONFIDENCE: 0.95", "model": "qwen2.5", "cost_usd": 0.0}
        return {"text": "ANSWER: 4", "model": "qwen2.5", "cost_usd": 0.0}

    monkeypatch.setattr(core, "proxy_call", fake_proxy)
    monkeypatch.setattr(core, "verify_in_sandbox", lambda c, g: sympy_oracle.verdict(c, g))
    # provide a top_skill so the path is local (not escalated) and confident
    monkeypatch.setattr(
        retrieval, "retrieve",
        lambda conn, q, limit=5: retrieval.Retrieved(
            top_skill=retrieval.SkillHit(skill_id, "s_seed", 0.95, 0.0)
        ),
    )

    res = core.run_iteration(conn)
    assert res["verdict"] == "succeeded"
    assert res["prediction_error"] < 0.5      # low surprise
    assert res["crystallized"] is False
    assert res["solve_path"] == "retrieval"
    with conn.cursor() as cur:
        # only the pre-seeded skill exists; the low-PE solve crystallized nothing (SC-006)
        cur.execute("SELECT count(*) FROM skills")
        assert cur.fetchone()[0] == 1


def test_escalated_success_crystallizes(migrated_conn, monkeypatch):
    """A verified success the small model needed the teacher for (escalated, cold) IS a
    surprising win → crystallization fires (US2). Constitution IV is respected: escalation
    means it did NOT confidently predict success."""
    conn = migrated_conn
    _seed(conn, "esc-1", "13+8", "21")

    def fake_proxy(task_id, model_class, prompt, role="solver"):
        if "CONFIDENCE" in prompt:  # low confidence → escalate
            return {"text": "CONFIDENCE: 0.3", "model": "qwen2.5", "cost_usd": 0.0}
        return {"text": "ANSWER: 21", "model": "deepseek-chat", "cost_usd": 0.001}

    monkeypatch.setattr(core, "proxy_call", fake_proxy)
    monkeypatch.setattr(core, "verify_in_sandbox", lambda c, g: sympy_oracle.verdict(c, g))
    # cold retrieval (no skill)
    monkeypatch.setattr(retrieval, "retrieve", lambda conn, q, limit=5: retrieval.Retrieved())
    # stub crystallize + admit (no real proxy/sandbox in CI); assert the gate FIRES
    from fenrir.skills import admit, crystallize
    monkeypatch.setattr(
        crystallize, "make_candidate",
        lambda p, a, r: crystallize.SkillCandidate(
            "s_esc", "def solve():return 21", "def self_test():pass", p),
    )
    admitted = {}

    def _admit(conn, cand, originating, pe):
        admitted["called"] = True
        return True

    monkeypatch.setattr(admit, "admit", _admit)

    res = core.run_iteration(conn)
    assert res["verdict"] == "succeeded" and res["escalated"] is True
    assert res["crystallized"] is True          # surprising win → skill crystallized
    assert admitted.get("called") is True

"""005 PE-gated meta-reflection — integration (real pgvector via migrated_conn; migration 0007).

The full-tier create/edit path is exercised end-to-end against a real DB with the proxy
(make_candidate) and sandbox (admit's runner) stubbed, so we test the reflection wiring +
audit writes + admit's version-vs-create + the is_eval guard without needing Ollama/Docker.
"""
from __future__ import annotations

import pytest

from fenrir.reflect import ReflectCtx, reflect
from fenrir.skills.crystallize import SkillCandidate
from fenrir.verify.sympy_oracle import FAILED, SUCCEEDED

pytestmark = pytest.mark.usefixtures("migrated_conn")


def _task(conn, *, is_eval=False) -> str:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO tasks (content, domain, source, benchmark_pool, status, is_eval, "
            " predicted_confidence) "
            "VALUES ('2+2?', 'math', 'benchmark', %s, 'in_progress', %s, 0.2) RETURNING id",
            ("evaluation" if is_eval else "training", is_eval),
        )
        tid = cur.fetchone()[0]
    conn.commit()
    return str(tid)


@pytest.fixture()
def stub_skill(monkeypatch):
    """make_candidate → trivial reproducing candidate; sandbox.run → success payload."""
    from fenrir.sandbox import runner
    from fenrir.skills import crystallize

    monkeypatch.setattr(crystallize, "make_candidate", lambda p, a, r: SkillCandidate(
        name="skill_two_plus_two", code="def solve():\n    return '4'\n",
        self_test="def self_test():\n    assert str(solve())=='4'\n", problem=p))

    class _Res:
        timed_out = False
        payload = {"ok": True, "answer": "4", "err": ""}
    monkeypatch.setattr(runner, "run", lambda *a, **k: _Res())


def _ctx(tid, **over):
    base = dict(task_id=tid, prediction_error=0.9, verdict=SUCCEEDED, solve_path="scratch",
                escalated=False, is_eval=False, retrieval_skill_id=None, problem_text="2+2?",
                candidate_answer="4", solve_text="2+2=4", ground_truth="4")
    base.update(over)
    return ReflectCtx(**base)


def _count(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()[0]


def test_full_create_writes_skill_and_audit(migrated_conn, stub_skill):
    tid = _task(migrated_conn)
    r = reflect(migrated_conn, _ctx(tid))                       # cold high-PE win → create
    assert r.tier == "full" and r.outcome == "created" and r.skill_id
    assert _count(migrated_conn, "SELECT count(*) FROM skills WHERE name='skill_two_plus_two'") == 1
    assert _count(migrated_conn, "SELECT count(*) FROM reflections WHERE task_id=%s", (tid,)) == 1
    assert _count(
        migrated_conn,
        "SELECT count(*) FROM tasks WHERE id=%s AND reflection_outcome='created'", (tid,)) == 1


def test_full_edit_versions_existing(migrated_conn, stub_skill):
    reflect(migrated_conn, _ctx(_task(migrated_conn)))         # create v1
    tid2 = _task(migrated_conn)
    r = reflect(migrated_conn, _ctx(tid2, prediction_error=0.6))  # PE<0.75 → admit versions (edit)
    assert r.outcome == "edited"
    # versioned in place, not duplicated (VII)
    assert _count(migrated_conn, "SELECT version FROM skills WHERE name='skill_two_plus_two'") == 2


def test_is_eval_writes_no_skill(migrated_conn, stub_skill):
    tid = _task(migrated_conn, is_eval=True)
    r = reflect(migrated_conn, _ctx(tid, is_eval=True, escalated=True))
    assert r.outcome == "none" and r.skill_id is None
    assert _count(migrated_conn, "SELECT count(*) FROM skills") == 0   # III / SC-005


def test_none_tier_no_writes(migrated_conn, stub_skill):
    tid = _task(migrated_conn)
    r = reflect(migrated_conn, _ctx(tid, prediction_error=0.05))
    assert r.tier == "none"
    assert _count(migrated_conn, "SELECT count(*) FROM reflections WHERE task_id=%s", (tid,)) == 0
    assert _count(migrated_conn, "SELECT count(*) FROM skills") == 0


def test_full_failure_no_skill(migrated_conn, stub_skill):
    tid = _task(migrated_conn)
    r = reflect(migrated_conn, _ctx(tid, verdict=FAILED, prediction_error=1.0))
    assert r.tier == "full" and r.outcome == "none"
    assert _count(migrated_conn, "SELECT count(*) FROM skills") == 0   # II/IV
    assert _count(migrated_conn, "SELECT count(*) FROM reflections WHERE task_id=%s", (tid,)) == 1


def test_off_switch_no_audit_but_crystallizes(migrated_conn, stub_skill, monkeypatch):
    monkeypatch.setenv("REFLECT_ENABLED", "false")
    from fenrir.settings import get_settings
    get_settings.cache_clear()
    tid = _task(migrated_conn)
    reflect(migrated_conn, _ctx(tid, escalated=True))          # legacy crystallize fires
    assert _count(migrated_conn, "SELECT count(*) FROM reflections") == 0   # no audit (SC-008)
    assert _count(
        migrated_conn, "SELECT count(*) FROM skills WHERE name='skill_two_plus_two'") == 1
    get_settings.cache_clear()

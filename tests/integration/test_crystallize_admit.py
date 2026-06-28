"""US2 (T022): a skill is admitted (code+self_test, state=stable) only after the
independent pass; a failing self_test is rejected. SC-003, FR-022/023, VIII.
"""
from __future__ import annotations

from fenrir.skills import admit
from fenrir.skills.crystallize import SkillCandidate


def _candidate(name="skill_two_plus_two"):
    return SkillCandidate(
        name=name,
        code="def solve():\n    return '4'\n",
        self_test="def self_test():\n    assert str(solve()) == '4'\n",
    )


def test_admitted_only_after_independent_pass(migrated_conn, monkeypatch):
    conn = migrated_conn
    # independent pass succeeds and reproduces the verified answer
    monkeypatch.setattr(admit, "_run_candidate", lambda code, st: (True, "4"))
    ok = admit.admit(conn, _candidate(), originating=("4", "4"), pe=0.6)
    assert ok is True
    with conn.cursor() as cur:
        cur.execute(
            "SELECT skill_kind, self_test, state FROM skills WHERE name='skill_two_plus_two'"
        )
        kind, self_test, state = cur.fetchone()
    assert kind == "code" and self_test and state == "stable"


def test_failing_selftest_is_rejected(migrated_conn, monkeypatch):
    conn = migrated_conn
    monkeypatch.setattr(admit, "_run_candidate", lambda code, st: (False, ""))
    ok = admit.admit(conn, _candidate("skill_bad"), originating=("4", "4"), pe=0.6)
    assert ok is False
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM skills WHERE name='skill_bad'")
        assert cur.fetchone()[0] == 0


def test_reproduce_mismatch_is_rejected(migrated_conn, monkeypatch):
    """Self_test passes but the code does not reproduce the verified answer → reject."""
    conn = migrated_conn
    monkeypatch.setattr(admit, "_run_candidate", lambda code, st: (True, "5"))
    ok = admit.admit(conn, _candidate("skill_wrong"), originating=("4", "4"), pe=0.6)
    assert ok is False


def test_large_pe_creates_new_skill_with_contradicts(migrated_conn, monkeypatch):
    conn = migrated_conn
    monkeypatch.setattr(admit, "_run_candidate", lambda code, st: (True, "4"))
    admit.admit(conn, _candidate("skill_dup"), originating=("4", "4"), pe=0.6)
    # second admission of same name with LARGE pe → new skill + contradicts edge (VII/FR-024)
    admit.admit(conn, _candidate("skill_dup"), originating=("4", "4"), pe=0.9)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM skills WHERE name LIKE 'skill_dup%'")
        assert cur.fetchone()[0] == 2
        cur.execute("SELECT count(*) FROM graph_updates WHERE relation_type='contradicts'")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT count(*) FROM skill_versions")
        assert cur.fetchone()[0] >= 1   # version-before-modify

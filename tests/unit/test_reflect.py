"""005 PE-gated meta-reflection — pure/unit suite (no DB, no LLM).

Covers tier() banding + escalation override (F1), the LOW<=HIGH settings guard, exact
subsumption of today's crystallize trigger (SC-008), and the no-LLM reflect() branches
(none / cheap / is_eval read-only / off-switch) via a recording fake connection. The full
verified edit/create path needs the proxy + sandbox + DB → tests/integration/test_reflect_loop.py.
"""
from __future__ import annotations

import pytest

from fenrir.reflect import CHEAP, FULL, NONE, ReflectCtx, reflect, tier
from fenrir.verify.sympy_oracle import FAILED, SUCCEEDED


def _settings(monkeypatch, **over):
    from fenrir.settings import get_settings
    for k, v in over.items():
        monkeypatch.setenv(k, str(v))
    get_settings.cache_clear()
    return get_settings()


class _Cur:
    def __init__(self, store, fetch=None):
        self.store, self._fetch = store, fetch
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def execute(self, sql, params=None):
        self.store.append((sql, params))
    def fetchone(self):
        return self._fetch


class _Conn:
    def __init__(self, fetch=None):
        self.store: list = []
        self._fetch = fetch
    def cursor(self):
        return _Cur(self.store, self._fetch)
    def commit(self):
        pass
    def rollback(self):
        pass


def _ctx(**over):
    base = dict(task_id="t1", prediction_error=0.0, verdict=SUCCEEDED, solve_path="scratch",
                escalated=False, is_eval=False, retrieval_skill_id=None, problem_text="2+2?",
                candidate_answer="4", solve_text="...", ground_truth="4")
    base.update(over)
    return ReflectCtx(**base)


# --- tier() ---------------------------------------------------------------

def test_tier_bands(monkeypatch):
    s = _settings(monkeypatch, REFLECT_PE_LOW=0.3, REFLECT_PE_HIGH=0.5)
    assert tier(0.0, False, s) == NONE
    assert tier(0.29, False, s) == NONE
    assert tier(0.3, False, s) == CHEAP      # inclusive-up at LOW
    assert tier(0.49, False, s) == CHEAP
    assert tier(0.5, False, s) == FULL       # inclusive-up at HIGH
    assert tier(1.0, False, s) == FULL


def test_tier_escalated_forces_full(monkeypatch):
    s = _settings(monkeypatch, REFLECT_PE_LOW=0.3, REFLECT_PE_HIGH=0.5)
    assert tier(0.0, True, s) == FULL        # low PE but escalated (F1)
    assert tier(0.4, True, s) == FULL


def test_settings_rejects_low_gt_high(monkeypatch):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        _settings(monkeypatch, REFLECT_PE_LOW=0.9, REFLECT_PE_HIGH=0.1)


def test_subsumption_matches_legacy_crystallize(monkeypatch):
    """With REFLECT_PE_HIGH == CRYSTALLIZE_PE, full-tier on verified scratch wins is exactly
    today's crystallize predicate `escalated OR pe>=CRYSTALLIZE_PE` (SC-008, F1)."""
    s = _settings(monkeypatch, REFLECT_PE_HIGH=0.5, CRYSTALLIZE_PE=0.5)
    for pe in (0.0, 0.3, 0.49, 0.5, 0.9, 1.0):
        for esc in (False, True):
            legacy = esc or pe >= s.CRYSTALLIZE_PE          # verified scratch win assumed
            assert (tier(pe, esc, s) == FULL) == legacy


# --- reflect() no-LLM branches -------------------------------------------

def test_none_tier_no_llm_no_reflection_row(monkeypatch):
    _settings(monkeypatch, REFLECT_PE_LOW=0.3, REFLECT_PE_HIGH=0.5)
    conn = _Conn()
    r = reflect(conn, _ctx(prediction_error=0.05))
    assert r.tier == NONE and r.llm_called is False and r.outcome is None
    assert any("UPDATE tasks" in sql for sql, _ in conn.store)
    assert not any("INSERT INTO reflections" in sql for sql, _ in conn.store)  # SC-002/FR-002


def test_cheap_tier_writes_note_no_llm(monkeypatch):
    _settings(monkeypatch, REFLECT_PE_LOW=0.3, REFLECT_PE_HIGH=0.5)
    conn = _Conn()
    r = reflect(conn, _ctx(prediction_error=0.4))
    assert r.tier == CHEAP and r.llm_called is False
    inserts = [p for sql, p in conn.store if "INSERT INTO reflections" in sql]
    assert len(inserts) == 1 and inserts[0][1] == "cheap"  # tier param  # FR-003/R4


def test_is_eval_read_only_no_skill(monkeypatch):
    """Full-tier eval row: tier recorded, NO skill write, NO LLM (III/FR-009/SC-005)."""
    _settings(monkeypatch, REFLECT_PE_HIGH=0.5)
    conn = _Conn()
    r = reflect(conn, _ctx(prediction_error=1.0, escalated=True, is_eval=True))
    assert r.outcome == "none" and r.skill_id is None and r.llm_called is False
    assert not any("INSERT INTO skills" in sql for sql, _ in conn.store)


def test_full_failure_records_lesson_no_skill(monkeypatch):
    """Full-tier failed verdict: lesson only, no skill (II/IV/FR-006)."""
    _settings(monkeypatch, REFLECT_PE_HIGH=0.5)
    conn = _Conn()
    r = reflect(conn, _ctx(prediction_error=1.0, verdict=FAILED, solve_path="scratch"))
    assert r.tier == FULL and r.outcome == "none" and r.skill_id is None
    assert not any("INSERT INTO skills" in sql for sql, _ in conn.store)


def test_off_switch_no_audit(monkeypatch):
    """REFLECT_ENABLED=False + a non-crystallizing task ⇒ no audit writes at all (SC-008)."""
    _settings(monkeypatch, REFLECT_ENABLED=False)
    conn = _Conn()
    r = reflect(conn, _ctx(prediction_error=0.0, verdict=FAILED))
    assert r.tier == NONE
    assert not any("INSERT INTO reflections" in sql for sql, _ in conn.store)
    assert not any("reflection_tier" in sql for sql, _ in conn.store)

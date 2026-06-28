"""US3 (T028): low-confidence escalates; the daily budget cap is never exceeded and
suppresses escalation on exhaustion. SC-008, FR-010/012, Constitution IX.
"""
from __future__ import annotations

from fenrir.llm import budget


def test_local_calls_always_allowed(migrated_conn):
    conn = migrated_conn
    d = budget.check(conn, 0.0, frontier=False)
    assert d.allowed and d.reason == "local_free"


def test_frontier_allowed_under_cap(migrated_conn, monkeypatch):
    conn = migrated_conn
    # default daily_budget_usd is 2.00; no spend yet (redis missing → rehydrate from 0)
    monkeypatch.setattr(budget, "_redis", lambda: _FakeRedis())
    d = budget.check(conn, 0.05, frontier=True)
    assert d.allowed and d.reason == "ok"


def test_frontier_refused_when_cap_exhausted(migrated_conn, monkeypatch):
    conn = migrated_conn
    # drive recorded spend up to the cap in Postgres
    with conn.cursor() as cur:
        cur.execute("INSERT INTO budget_tracking (date, llm_cost_usd, daily_budget_usd) "
                    "VALUES (CURRENT_DATE, 2.0, 2.0) "
                    "ON CONFLICT (date) DO UPDATE SET llm_cost_usd=2.0, daily_budget_usd=2.0")
    conn.commit()
    monkeypatch.setattr(budget, "_redis", lambda: _FakeRedis(seed=2.0))
    d = budget.check(conn, 0.05, frontier=True)
    assert not d.allowed and d.reason == "daily_budget_exhausted"


class _FakeRedis:
    def __init__(self, seed=0.0):
        self._v = {}
        self._seed = seed

    def exists(self, k):
        return 1 if k in self._v else 0

    def set(self, k, v):
        self._v[k] = float(v)

    def get(self, k):
        return self._v.get(k, self._seed)

    def expireat(self, *a, **k):
        pass

    def incrbyfloat(self, k, v):
        self._v[k] = self._v.get(k, 0.0) + float(v)

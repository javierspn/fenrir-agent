"""Daily LLM budget — hard cap (002, T008). Constitution IX.

Source of truth is Postgres ``budget_tracking`` (one row per day, column
``daily_budget_usd`` default 2.00). Redis holds a fast spend counter that is
*rehydrated from Postgres on first use each day* — a full redis wipe loses zero
durable budget state (D10). The pre-call gate refuses frontier calls once the
cap would be exceeded; it NEVER raises the cap silently.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

import psycopg
import redis

from fenrir.settings import get_settings


@dataclass
class BudgetDecision:
    allowed: bool
    reason: str
    spent_usd: float
    cap_usd: float


def _today() -> str:
    return _dt.datetime.now(_dt.timezone.utc).date().isoformat()


def _redis() -> redis.Redis:
    s = get_settings()
    return redis.Redis(host=s.REDIS_HOST, port=s.REDIS_PORT, decode_responses=True)


def _ensure_day_row(conn: psycopg.Connection, day: str) -> tuple[float, float]:
    """Return (spent_today, cap) from Postgres, creating today's row if absent. The cap is
    synced to the operator setting DAILY_BUDGET_USD each call (changing .env applies same-day);
    spend (llm_cost_usd) is preserved."""
    cap = get_settings().DAILY_BUDGET_USD
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO budget_tracking (date, daily_budget_usd) VALUES (%s, %s) "
            "ON CONFLICT (date) DO UPDATE SET daily_budget_usd = EXCLUDED.daily_budget_usd",
            (day, cap),
        )
        cur.execute(
            "SELECT COALESCE(llm_cost_usd, 0), daily_budget_usd "
            "FROM budget_tracking WHERE date = %s",
            (day,),
        )
        row = cur.fetchone()
    conn.commit()
    return (float(row[0]), float(row[1]))


def _rehydrate(r: redis.Redis, day: str, spent: float) -> None:
    """Seed redis from the Postgres source-of-truth if the counter is missing (restart-safe)."""
    key = f"budget:{day}"
    if not r.exists(key):
        r.set(key, spent)
        r.expireat(key, int((_dt.date.fromisoformat(day) + _dt.timedelta(days=2)).strftime("%s")))


def check(conn: psycopg.Connection, projected_usd: float, *, frontier: bool) -> BudgetDecision:
    """Pre-call gate. Local (frontier=False) calls are free and always allowed.

    A frontier call is refused if ``spent + projected >= cap`` — escalation is then
    suppressed, never silently exceeded (FR-012, SC-008)."""
    day = _today()
    spent, cap = _ensure_day_row(conn, day)
    if not frontier:
        return BudgetDecision(True, "local_free", spent, cap)
    r = _redis()
    _rehydrate(r, day, spent)
    spent = float(r.get(f"budget:{day}") or spent)
    if spent + projected_usd >= cap:
        return BudgetDecision(False, "daily_budget_exhausted", spent, cap)
    return BudgetDecision(True, "ok", spent, cap)


def record(conn: psycopg.Connection, cost_usd: float, *, escalated: bool) -> None:
    """Post-call accounting: bump the redis counter and the Postgres source-of-truth."""
    day = _today()
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE budget_tracking SET llm_cost_usd = COALESCE(llm_cost_usd, 0) + %s, "
            "tasks_executed = COALESCE(tasks_executed, 0) + 1 WHERE date = %s",
            (cost_usd, day),
        )
    conn.commit()
    if cost_usd:
        _redis().incrbyfloat(f"budget:{day}", cost_usd)

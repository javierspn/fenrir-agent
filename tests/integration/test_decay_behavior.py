"""003 increment B — decay behavior on the live schema (decay.contract Tests; Acceptance 1/2/5).

Two equal-salience rows of equal age: the reactivated one outranks the idle one in effective
significance; every row stays fully queryable (additive, SC-004); reactivation reverses the
fade; and the Python effective_salience() agrees with the SQL expression to float tolerance.
"""
from __future__ import annotations

from fenrir.memory.salience import effective_salience, effective_salience_sql, reactivate


def _insert(conn, salience, *, age_days, reactivated_days_ago=None):
    react = (
        f"now() - interval '{reactivated_days_ago} days'"
        if reactivated_days_ago is not None
        else "NULL"
    )
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO short_term_memory "
            "(content, domain, task_id, prediction_error, importance, retrieval_count, "
            " salience, created_at, last_reactivated_at) "
            f"VALUES ('x','math', gen_random_uuid(), 0.5, 1.0, 0, %s, "
            f"        now() - interval '{age_days} days', {react}) RETURNING id",
            (salience,),
        )
        eid = cur.fetchone()[0]
    conn.commit()
    return eid


def _row_effective(conn, eid):
    expr = effective_salience_sql()
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT salience, created_at, last_reactivated_at, now() AS db_now, ({expr}) AS eff "
            "FROM short_term_memory WHERE id = %s",
            (eid,),
        )
        return cur.fetchone()


def test_idle_below_reactivated(migrated_conn):
    idle = _insert(migrated_conn, 2.0, age_days=30)                       # old, never touched
    active = _insert(migrated_conn, 2.0, age_days=30, reactivated_days_ago=0)  # just reactivated
    _, _, _, _, idle_eff = _row_effective(migrated_conn, idle)
    _, _, _, _, active_eff = _row_effective(migrated_conn, active)
    assert float(idle_eff) < float(active_eff)
    assert float(active_eff) > 1.9            # reactivated ≈ stored 2.0


def test_decay_never_deletes_or_hides(migrated_conn):
    eid = _insert(migrated_conn, 2.0, age_days=365)   # heavily decayed
    with migrated_conn.cursor() as cur:
        cur.execute("SELECT id, content, salience FROM short_term_memory WHERE id = %s", (eid,))
        row = cur.fetchone()
    assert row is not None and row[1] == "x"
    assert float(row[2]) == 2.0                # stored salience UNCHANGED (additive, VI)


def test_python_matches_sql(migrated_conn):
    eid = _insert(migrated_conn, 1.7, age_days=12)
    salience, created_at, last_react, db_now, eff_sql = _row_effective(migrated_conn, eid)
    eff_py = effective_salience(float(salience), last_react, created_at, now=db_now)
    assert eff_py == abs(float(eff_sql)) or abs(eff_py - float(eff_sql)) < 1e-9


def test_reactivation_reverses_fade(migrated_conn):
    eid = _insert(migrated_conn, 2.0, age_days=30)        # idle, faded
    _, _, _, _, before = _row_effective(migrated_conn, eid)
    reactivate(migrated_conn, [str(eid)])                # renewed relevance
    _, _, _, _, after = _row_effective(migrated_conn, eid)
    assert float(after) > float(before)
    assert float(after) > 1.9                            # bounced back toward stored 2.0

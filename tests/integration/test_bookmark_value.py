"""003 increment A — live value bookmark on the episode write (Acceptance 2/3, SC-002).

Three verified successes identical in (PE, use) but differing in escalated/crystallized must
land in short_term_memory with strictly ordered `importance` (skill ≥ teacher ≥ scratch), and
failures must rank below a from-scratch success — proving the value signal is live, not 1.0.
"""
from __future__ import annotations

from fenrir.memory import episodes
from fenrir.memory.salience import value
from fenrir.verify.sympy_oracle import FAILED, SUCCEEDED


def _write(conn, verdict, *, escalated, crystallized):
    ep = episodes.Episode(
        task_id="00000000-0000-0000-0000-000000000000",
        content=f"[{verdict}] 2+2 -> 4",
        domain="math",
        prediction_error=0.5,  # equal surprise across all three
        importance=value(verdict, escalated=escalated, crystallized=crystallized),
    )
    eid = episodes.write_episode(conn, ep)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT importance, salience FROM short_term_memory WHERE id = %s", (eid,)
        )
        return cur.fetchone()


def test_importance_strictly_ordered(migrated_conn):
    scratch_imp, scratch_sal = _write(migrated_conn, SUCCEEDED, escalated=False, crystallized=False)
    teacher_imp, teacher_sal = _write(migrated_conn, SUCCEEDED, escalated=True, crystallized=False)
    skill_imp, skill_sal = _write(migrated_conn, SUCCEEDED, escalated=True, crystallized=True)

    assert float(skill_imp) >= float(teacher_imp) >= float(scratch_imp)
    assert float(teacher_imp) > float(scratch_imp)
    # equal PE + use (retrieval_count=0) → salience ordering tracks importance ordering
    assert float(skill_sal) >= float(teacher_sal) >= float(scratch_sal)


def test_failure_ranks_below_scratch_success(migrated_conn):
    scratch_imp, _ = _write(migrated_conn, SUCCEEDED, escalated=False, crystallized=False)
    fail_imp, _ = _write(migrated_conn, FAILED, escalated=False, crystallized=False)
    assert float(fail_imp) < float(scratch_imp)


def test_value_not_inert_constant(migrated_conn):
    """Distinct outcomes must produce distinct stored importance (the bug was all 1.0)."""
    imps = {
        _write(migrated_conn, SUCCEEDED, escalated=True, crystallized=True)[0],
        _write(migrated_conn, SUCCEEDED, escalated=True, crystallized=False)[0],
        _write(migrated_conn, SUCCEEDED, escalated=False, crystallized=False)[0],
        _write(migrated_conn, FAILED, escalated=False, crystallized=False)[0],
    }
    assert len({float(i) for i in imps}) == 4

"""PE-gated meta-reflection (005, P1.2). Constitution IV/VI/VII/VIII/IX/III; D3 + D6.

Reflection effort concentrates where the system was surprised. Every task is tiered by
prediction-error magnitude (with escalation forcing the top tier), and effort is spent
accordingly:

  - ``none``  (PE < REFLECT_PE_LOW, not escalated): nothing extra — today's behavior.
  - ``cheap`` (LOW <= PE < HIGH): a templated structured note, NO model call.
  - ``full``  (PE >= HIGH, or escalated): one model pass that turns a *verified* win into a
    skill via the existing crystallize→admit path (admit handles version-vs-new-skill by PE);
    a failure/unverified outcome records a lesson only (no skill, II/IV).

The full tier is an exact superset of today's crystallize trigger
(``escalated OR pe>=CRYSTALLIZE_PE`` on verified scratch wins) when REFLECT_PE_HIGH==CRYSTALLIZE_PE
(F1/R2) — so turning reflection off leaves what-becomes-a-skill unchanged (SC-008).

Best-effort: reflection never raises into the loop; any error is caught and recorded as
``outcome='none'``. ``is_eval`` rows are read-only (III): tier recorded, never a skill write.
"""
from __future__ import annotations

from dataclasses import dataclass

import psycopg

from fenrir.settings import get_settings
from fenrir.verify.sympy_oracle import SUCCEEDED

NONE, CHEAP, FULL = "none", "cheap", "full"


@dataclass
class ReflectCtx:
    task_id: str
    prediction_error: float
    verdict: str
    solve_path: str
    escalated: bool
    is_eval: bool
    retrieval_skill_id: str | None
    problem_text: str
    candidate_answer: str
    solve_text: str
    ground_truth: str


@dataclass
class ReflectResult:
    tier: str
    outcome: str | None       # full only: edited | created | none | suppressed
    skill_id: str | None
    llm_called: bool


def tier(pe: float, escalated: bool, s) -> str:
    """Pure classifier. Escalation forces ``full`` (F1); otherwise PE bands (inclusive-up)."""
    if escalated:
        return FULL
    if pe < s.REFLECT_PE_LOW:
        return NONE
    if pe < s.REFLECT_PE_HIGH:
        return CHEAP
    return FULL


def _legacy_should_crystallize(ctx: ReflectCtx, s) -> bool:
    """Exactly today's crystallize trigger (002 core step 8) — used for the off-switch path."""
    return (
        ctx.verdict == SUCCEEDED
        and ctx.solve_path == "scratch"
        and (ctx.escalated or ctx.prediction_error >= s.CRYSTALLIZE_PE)
    )


def _cheap_note(ctx: ReflectCtx) -> str:
    return (
        f"[{ctx.verdict}] solve_path={ctx.solve_path} escalated={ctx.escalated} "
        f"retrieval_skill={'yes' if ctx.retrieval_skill_id else 'no'} pe={ctx.prediction_error:.2f}"
    )


def _budget_ok(conn: psycopg.Connection) -> bool:
    """IX guard: is today's spend still under the cap? (Cheap SQL; the reflector uses the free
    local model, so this rarely bites — defensive for a paid REFLECT_MODEL_ROLE.)"""
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(llm_cost_usd,0) < daily_budget_usd FROM budget_tracking "
                "WHERE date = CURRENT_DATE"
            )
            row = cur.fetchone()
        return True if row is None else bool(row[0])
    except Exception:
        return True  # never block on a metering read


def _set_task(conn, task_id, tier_val, outcome=None, skill_id=None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE tasks SET reflection_tier=%s, reflection_outcome=%s, reflection_skill_id=%s "
            "WHERE id=%s",
            (tier_val, outcome, skill_id, task_id),
        )
    conn.commit()


def _insert_reflection(conn, ctx, tier_val, *, lesson, outcome, skill_id) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO reflections (task_id, tier, prediction_error, lesson, outcome, skill_id) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (ctx.task_id, tier_val, ctx.prediction_error, lesson, outcome, skill_id),
        )
    conn.commit()


def _skill_id_by_name(conn, name: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM skills WHERE name=%s", (name,))
        row = cur.fetchone()
    return str(row[0]) if row else None


def _full_verified(conn, ctx: ReflectCtx) -> ReflectResult:
    """One model pass → crystallize→admit (admit owns version-vs-new-skill by PE). Returns the
    edited/created label + the skill id, or suppressed/none."""
    from fenrir.skills import admit, crystallize

    if not _budget_ok(conn):  # IX: downgrade to a cheap suppressed note, no model call
        _insert_reflection(conn, ctx, CHEAP, lesson=_cheap_note(ctx), outcome="suppressed",
                           skill_id=None)
        _set_task(conn, ctx.task_id, FULL, outcome="suppressed")
        return ReflectResult(FULL, "suppressed", None, False)

    cand = crystallize.make_candidate(ctx.problem_text, ctx.candidate_answer, ctx.solve_text)
    existed = _skill_id_by_name(conn, cand.name) is not None
    admitted = admit.admit(conn, cand, originating=(ctx.candidate_answer, ctx.ground_truth),
                           pe=ctx.prediction_error)
    if not admitted:
        _insert_reflection(conn, ctx, FULL, lesson=cand.code[:500], outcome="none", skill_id=None)
        _set_task(conn, ctx.task_id, FULL, outcome="none")
        return ReflectResult(FULL, "none", None, True)
    # admit versioned the existing skill (edit) when it existed + PE small; else created (new name).
    outcome = "edited" if existed else "created"
    skill_id = _skill_id_by_name(conn, cand.name)
    _insert_reflection(conn, ctx, FULL, lesson=cand.code[:500], outcome=outcome, skill_id=skill_id)
    _set_task(conn, ctx.task_id, FULL, outcome=outcome, skill_id=skill_id)
    return ReflectResult(FULL, outcome, skill_id, True)


def reflect(conn: psycopg.Connection, ctx: ReflectCtx) -> ReflectResult:
    """Tier the task by PE and spend reflection effort accordingly. Best-effort (never raises)."""
    s = get_settings()

    # Off-switch (SC-008): keep exactly today's crystallization, no tier audit.
    if not s.REFLECT_ENABLED:
        if not ctx.is_eval and _legacy_should_crystallize(ctx, s):
            try:
                from fenrir.skills import admit, crystallize
                cand = crystallize.make_candidate(ctx.problem_text, ctx.candidate_answer,
                                                  ctx.solve_text)
                admit.admit(conn, cand, originating=(ctx.candidate_answer, ctx.ground_truth),
                            pe=ctx.prediction_error)
            except Exception:
                conn.rollback()
        return ReflectResult(tier(ctx.prediction_error, ctx.escalated, s), None, None, False)

    t = tier(ctx.prediction_error, ctx.escalated, s)
    try:
        if t == NONE:
            _set_task(conn, ctx.task_id, NONE)
            return ReflectResult(NONE, None, None, False)

        # III — eval rows are read-only: record the tier, never write a skill.
        if ctx.is_eval:
            _set_task(conn, ctx.task_id, t, outcome="none")
            _insert_reflection(conn, ctx, t if t == CHEAP else FULL, lesson=None, outcome="none",
                               skill_id=None)
            return ReflectResult(t, "none", None, False)

        if t == CHEAP:
            _set_task(conn, ctx.task_id, CHEAP)
            _insert_reflection(conn, ctx, CHEAP, lesson=_cheap_note(ctx), outcome=None,
                               skill_id=None)
            return ReflectResult(CHEAP, None, None, False)

        # FULL
        if ctx.verdict == SUCCEEDED:
            return _full_verified(conn, ctx)
        # failure/unverified full: lesson only, no skill (II/IV), no extra model call (cost).
        _set_task(conn, ctx.task_id, FULL, outcome="none")
        _insert_reflection(conn, ctx, FULL, lesson=_cheap_note(ctx), outcome="none", skill_id=None)
        return ReflectResult(FULL, "none", None, False)
    except Exception:
        conn.rollback()
        try:
            _set_task(conn, ctx.task_id, t, outcome="none")
        except Exception:
            conn.rollback()
        return ReflectResult(t, "none", None, False)

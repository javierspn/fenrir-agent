"""Cognitive loop runner — one iteration over one training task (002, T020/T021).

predict → retrieve → solve(local) → escalate-if-stuck → verify(sympy sandbox) →
prediction-error → additive episode → crystallize-if-high-PE → consolidate-on-cadence.
The measurement is the deliverable. Contracts: contracts/loop.contract.md
Constitution: III (pool isolation), IV (PE gate), II (sympy), VI (additive), X (proxy egress).
"""
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass

import httpx
import psycopg

from fenrir.db import connect
from fenrir.memory import episodes, retrieval, salience
from fenrir.predict import Prediction, parse_prediction, prediction_error
from fenrir.settings import get_settings
from fenrir.verify.sympy_oracle import (
    SUCCEEDED,
    UNVERIFIED,
    canonical_answer,
    verify_in_sandbox,
)

_ANSWER_RE = re.compile(r"ANSWER:\s*(.+)", re.IGNORECASE)


@dataclass
class BenchTask:
    benchmark_pk: str
    problem_id: str
    content: str
    ground_truth: str
    domain: str


# ---------------------------------------------------------------------------
# proxy egress — ALL model calls go through fenrir:8080/llm (Constitution X)
# ---------------------------------------------------------------------------
def proxy_call(task_id: str, model_class: str, prompt: str, *, role: str = "solver") -> dict:
    s = get_settings()
    resp = httpx.post(
        f"{s.LLM_PROXY_URL}/llm",
        json={"task_id": task_id, "role": role, "model_class": model_class,
              "prompt": prompt, "max_tokens": 1024},
        timeout=180.0,
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# task selection — TRAINING pool only; prefer unsolved / under-practiced (FR-001/002, III)
# ---------------------------------------------------------------------------
def select_task(conn: psycopg.Connection) -> BenchTask | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT b.id, b.problem_id, b.content, b.ground_truth, b.domain "
            "FROM benchmark_tasks b "
            "WHERE b.pool = 'training' "                       # NEVER evaluation (III)
            "  AND NOT EXISTS (SELECT 1 FROM tasks t "
            "                  WHERE t.benchmark_id = b.problem_id AND t.status = 'succeeded') "
            "ORDER BY (SELECT count(*) FROM tasks t2 WHERE t2.benchmark_id = b.problem_id) ASC, "
            "         random() LIMIT 1"
        )
        row = cur.fetchone()
    if not row:
        return None
    return BenchTask(str(row[0]), row[1], row[2], row[3], row[4] or "math")


def _new_task_row(conn: psycopg.Connection, bt: BenchTask, pred: Prediction) -> str:
    """Create the attempt row, writing predicted_confidence BEFORE solving (FR-004)."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO tasks (content, domain, source, benchmark_id, benchmark_pool, status, "
            " is_eval, predicted_confidence) "
            "VALUES (%s, %s, 'benchmark', %s, 'training', 'in_progress', false, %s) RETURNING id",
            (bt.content, bt.domain, bt.problem_id, pred.confidence),
        )
        task_id = cur.fetchone()[0]
    conn.commit()
    return str(task_id)


def _extract_answer(text: str) -> str:
    m = _ANSWER_RE.search(text or "")
    return m.group(1).strip() if m else (text or "").strip().splitlines()[-1:][0] if text else ""


def _solve_prompt(content: str) -> str:
    return (
        "Solve this math problem. Show brief reasoning, then end with a single line "
        "`ANSWER: <expression>` containing only the final answer as a sympy-parseable "
        f"expression.\n\nProblem:\n{content}\n"
    )


def _predict_prompt(content: str) -> str:
    return (
        "You will be asked to solve the problem below. First, WITHOUT solving it, estimate "
        "your probability of solving it correctly as a single line `CONFIDENCE: <0..1>`.\n\n"
        f"Problem:\n{content}\n"
    )


# ---------------------------------------------------------------------------
# one iteration
# ---------------------------------------------------------------------------
def run_iteration(conn: psycopg.Connection) -> dict | None:
    s = get_settings()
    bt = select_task(conn)
    if bt is None:
        return None

    # 1. predict-before-solve (FR-004)
    pred_raw = proxy_call("pending", "small", _predict_prompt(bt.content), role="predictor")
    pred = parse_prediction(pred_raw.get("text", ""))
    task_id = _new_task_row(conn, bt, pred)

    # 2. retrieve (FR-007) → decide solve path
    retr = retrieval.retrieve(conn, bt.content)
    salience.bump_retrieval_count(conn, retr.episode_ids)
    use_retrieval = retr.top_skill is not None
    solve_path = "retrieval" if use_retrieval else "scratch"

    # 3. solve with the small model; 4. escalate if stuck (US3 wiring)
    escalated = False
    cold = retr.top_skill is None
    if pred.confidence < s.ESCALATE_CONFIDENCE or cold:
        front = proxy_call(task_id, "frontier", _solve_prompt(bt.content), role="solver")
        if front.get("refused"):
            # budget exhausted → escalation suppressed, solve locally (FR-012, SC-008)
            solve = proxy_call(task_id, "small", _solve_prompt(bt.content), role="solver")
        else:
            solve = front
            escalated = True
    else:
        solve = proxy_call(task_id, "small", _solve_prompt(bt.content), role="solver")

    candidate = _extract_answer(solve.get("text", ""))

    # 5. verify (sympy, in the --network none sandbox) (FR-013, II/VIII).
    # Reduce both sides to the canonical final answer first (GSM8K '#### N', MATH '\boxed{}').
    verdict = verify_in_sandbox(canonical_answer(candidate), canonical_answer(bt.ground_truth))

    # 6. prediction error (FR-005)
    pe = prediction_error(pred, verdict)

    # 7. persist the iteration result
    status = "succeeded" if verdict == SUCCEEDED else ("unverified" if verdict == UNVERIFIED
                                                       else "failed")
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE tasks SET status=%s, verified=%s, result=%s, prediction_error=%s, "
            " solve_path=%s, retrieval_skill_id=%s, retrieval_abstraction_id=%s, escalated=%s, "
            " llm_used=%s, cost_usd=%s, tokens_used=%s WHERE id=%s",
            (status, verdict == SUCCEEDED, candidate, pe, solve_path,
             retr.top_skill.skill_id if retr.top_skill else None,
             # 003 C reuse signal: the nearest consolidated abstraction surfaced for this solve
             # (SC-008). NULL when none was retrievable. Honest proxy = retrieved-and-available.
             retr.abstractions[0].abstraction_id if retr.abstractions else None,
             escalated, solve.get("model"), solve.get("cost_usd", 0.0),
             solve.get("tokens", 0), task_id),
        )
    conn.commit()

    # 8. crystallize a SURPRISING win (US2). A verified success the small model did NOT
    # already own — it either needed the teacher (escalated) or the outcome was high-surprise
    # (PE >= threshold). Never on a task it confidently predicted AND solved locally (IV/SC-006).
    # Determined BEFORE the episode write (003 A) so value() sees all three signals at once.
    crystallized = False
    if verdict == SUCCEEDED and solve_path == "scratch" and (escalated or pe >= s.CRYSTALLIZE_PE):
        from fenrir.skills import admit, crystallize

        cand = crystallize.make_candidate(bt.content, candidate, solve.get("text", ""))
        crystallized = admit.admit(conn, cand, originating=(candidate, bt.ground_truth), pe=pe)

    # 9. additive episode (FR-016) with the live significance bookmark (003 A). importance
    # holds value(verdict, escalated, crystallized) — the reward-magnitude factor, no longer
    # the inert 1.0. salience = PE × value × use is computed inside write_episode (one definition).
    ep = episodes.Episode(
        task_id=task_id,
        content=f"[{verdict}] {bt.content[:200]} -> {candidate}",
        domain=bt.domain, prediction_error=pe,
        importance=salience.value(verdict, escalated=escalated, crystallized=crystallized),
    )
    episode_id = episodes.write_episode(conn, ep)

    return {
        "task_id": task_id, "verdict": verdict, "prediction_error": pe,
        "solve_path": solve_path, "escalated": escalated, "episode_id": episode_id,
        "crystallized": crystallized,
    }


def run(n: int) -> list[dict]:
    s = get_settings()
    conn = connect()
    out: list[dict] = []
    try:
        for i in range(n):
            try:
                res = run_iteration(conn)
            except Exception as exc:  # one bad task must not kill the cohort
                conn.rollback()
                print(f"  ! iteration {i} errored, skipping: {type(exc).__name__}: {exc}")
                continue
            if res is None:
                break
            out.append(res)
            # 10. consolidation on cadence (US4)
            if (i + 1) % s.CONSOLIDATION_EVERY_N_ITERS == 0:
                from fenrir.consolidation import sleep
                sleep.run(conn)
    finally:
        conn.close()
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fenrir.core")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--once", action="store_true", help="run a single iteration")
    g.add_argument("--run", type=int, metavar="N", help="run N iterations")
    args = ap.parse_args(argv)
    n = 1 if args.once else args.run
    results = run(n)
    print(f"✓ ran {len(results)} iteration(s)")
    for r in results:
        print(f"  {r['task_id'][:8]} {r['verdict']:10} PE={r['prediction_error']:.2f} "
              f"{r['solve_path']:9} esc={r['escalated']} cryst={r['crystallized']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Skill admission — independent verification pass + versioning (002, T026).

Constitution VIII (independent of the proposer), VII (versioned before modify), II.
A candidate is admitted to the library ONLY after its code+self_test run in the
`--network none` sandbox AND it reproduces the verified solution to the originating
task. Failing candidates are rejected. Versioning: small PE → new version; large PE
→ new skill + a `contradicts` edge in graph_updates. Never silent overwrite (FR-023/024).
"""
from __future__ import annotations

import psycopg

from fenrir.memory.embed import embed, to_pgvector
from fenrir.sandbox.runner import run
from fenrir.verify.sympy_oracle import SUCCEEDED, canonical_answer, verdict

_LARGE_PE = 0.75  # large-PE boundary: new skill + contradicts (vs new version)


def _selftest_program(code: str, self_test: str) -> str:
    """Trusted harness; the skill code is executed in isolation (--network none)."""
    return (
        "import json, sys\n"
        "ns = {}\n"
        "ok = True\nerr = ''\n"
        "try:\n"
        f"    exec({code!r}, ns)\n"
        f"    exec({self_test!r}, ns)\n"
        "    ns['self_test']()\n"
        "    ans = str(ns['solve']())\n"
        "except Exception as e:\n"
        "    ok = False; err = repr(e); ans = ''\n"
        "print(json.dumps({'ok': ok, 'answer': ans, 'err': err}))\n"
    )


def _run_candidate(code: str, self_test: str) -> tuple[bool, str]:
    res = run(_selftest_program(code, self_test))
    if res.timed_out or res.payload is None:
        return (False, "")
    return (bool(res.payload.get("ok")), str(res.payload.get("answer", "")))


def admit(conn: psycopg.Connection, candidate, *, originating: tuple[str, str], pe: float) -> bool:
    """Run the independent pass; on success insert/version the skill. Returns True if admitted."""
    ok, produced = _run_candidate(candidate.code, candidate.self_test)
    if not ok:
        return False
    # reproduce the verified solution to the originating task (independent re-check, VIII).
    # Canonicalize both sides first — ground_truth may be a full solution (#### / \boxed).
    _, ground_truth = originating
    if verdict(canonical_answer(produced), canonical_answer(ground_truth)) != SUCCEEDED:
        return False

    # embed the originating problem so retrieval can surface this skill on similar tasks.
    # NULL fallback if the embedder is down — never block admission.
    try:
        vec: str | None = to_pgvector(embed(candidate.problem or candidate.name))
    except Exception:
        vec = None

    with conn.cursor() as cur:
        cur.execute("SELECT id, version FROM skills WHERE name = %s", (candidate.name,))
        existing = cur.fetchone()
        if existing is None:
            cur.execute(
                "INSERT INTO skills (name, content, embedding, skill_kind, self_test, state, "
                " version, strength, created_by) "
                "VALUES (%s, %s, %s::vector, 'code', %s, 'stable', 1, 0.5, 'crystallization') "
                "RETURNING id",
                (candidate.name, candidate.code, vec, candidate.self_test),
            )
            conn.commit()
            return True

        skill_id, version = existing
        # version-before-modify (VII): snapshot the prior version first
        cur.execute(
            "INSERT INTO skill_versions (skill_id, version, content, state, strength, "
            " created_by, change_reason) "
            "SELECT id, version, content, state, strength, created_by, %s FROM skills WHERE id=%s",
            ("reconsolidation" if pe < _LARGE_PE else "contradiction", skill_id),
        )
        if pe < _LARGE_PE:
            # small PE → new version of the same skill
            cur.execute(
                "UPDATE skills SET content=%s, self_test=%s, version=version+1 WHERE id=%s",
                (candidate.code, candidate.self_test, skill_id),
            )
        else:
            # large PE → new skill + CONTRADICTS edge (never overwrite)
            cur.execute(
                "INSERT INTO skills (name, content, skill_kind, self_test, state, version, "
                " strength, created_by) VALUES (%s, %s, 'code', %s, 'stable', 1, 0.5, "
                " 'crystallization') RETURNING id",
                (f"{candidate.name}_v{version + 1}", candidate.code, candidate.self_test),
            )
            new_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO graph_updates "
                "(trigger, from_node, relation_type, to_node, confidence) "
                "VALUES ('meta_reflection', %s, 'contradicts', %s, 0.8) "
                "ON CONFLICT (from_node, relation_type, to_node) DO NOTHING",
                (new_id, skill_id),
            )
        conn.commit()
    return True

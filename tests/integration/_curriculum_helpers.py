"""Shared seeding helpers for the 004 curriculum integration suites.

Embeddings are constructed analytically (not via Ollama) so cosine to the skill loadout is
exact and deterministic: a skill sits at the unit vector e0 = [1,0,0,…]; a task at target
cosine c sits at [c, sqrt(1-c²), 0,…], giving cos(skill, task) = c precisely. This lets the
tests pin which adjacency band each seeded task falls in without a live embedding model.
"""
from __future__ import annotations

import math

import psycopg

DIM = 768
SKILL_VEC = [1.0] + [0.0] * (DIM - 1)


def vec_at_cosine(c: float) -> list[float]:
    """Unit vector whose cosine with SKILL_VEC is exactly ``c``."""
    v = [0.0] * DIM
    v[0] = c
    v[1] = math.sqrt(max(0.0, 1.0 - c * c))
    return v


def pgv(vec: list[float]) -> str:
    return "[" + ",".join(repr(x) for x in vec) + "]"


def seed_skill(conn: psycopg.Connection, name: str = "skill-0", *,
               vec: list[float] | None = None, state: str = "stable") -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO skills (name, content, embedding, skill_kind, state) "
            "VALUES (%s, %s, %s::vector, 'text', %s)",
            (name, f"content for {name}", pgv(vec or SKILL_VEC), state),
        )
    conn.commit()


def seed_bench_task(conn: psycopg.Connection, problem_id: str, cosine: float | None, *,
                    pool: str = "training", content: str | None = None,
                    ground_truth: str = "0") -> None:
    """Seed a benchmark task. ``cosine`` is its similarity to SKILL_VEC; None → NULL embedding."""
    emb = pgv(vec_at_cosine(cosine)) if cosine is not None else None
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO benchmark_tasks (benchmark, problem_id, pool, difficulty, domain, "
            " content, ground_truth, embedding) "
            "VALUES ('gsm8k', %s, %s, 'easy', 'math', %s, %s, %s::vector)",
            (problem_id, pool, content or f"problem {problem_id}", ground_truth, emb),
        )
    conn.commit()


def mark_solved(conn: psycopg.Connection, problem_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO tasks (content, domain, source, benchmark_id, benchmark_pool, status, "
            " is_eval) VALUES ('x','math','benchmark', %s,'training','succeeded', false)",
            (problem_id,),
        )
    conn.commit()

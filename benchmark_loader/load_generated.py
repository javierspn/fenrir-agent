"""Load generator JSONL into benchmark_tasks (006, D13). In-repo / <host> side.

Ground truth is RE-DERIVED by executing each problem's solution_code in the existing
``--network none`` sandbox (Constitution X) and confirmed via the sympy oracle (II) — the
generator's claimed answer is never trusted. Loads are idempotent (stable problem_id +
ON CONFLICT). Family → pool is whole-family (III).

Usage:  python -m benchmark_loader.load_generated --in problems.jsonl
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import psycopg

from benchmark_loader.families import pool_for
from fenrir.memory.embed import embed, to_pgvector
from fenrir.sandbox.runner import run
from fenrir.settings import get_settings
from fenrir.verify.sympy_oracle import SUCCEEDED, canonical_answer, verdict


@dataclass
class LoadResult:
    read: int = 0
    loaded: int = 0
    rejected: int = 0
    duplicates: int = 0


def _normalize(q: str) -> str:
    return re.sub(r"\s+", " ", q.lower()).strip()


def problem_id(question: str) -> str:
    """Stable, content-addressed id → idempotent reloads (R3)."""
    return "qwen-gen-" + hashlib.sha256(_normalize(question).encode("utf-8")).hexdigest()[:16]


def _harness(code: str) -> str:
    """Trusted harness; the model's solution_code runs in isolation (--network none, X)."""
    return (
        "import json\n"
        "ns = {}\nok = True\nerr = ''\nans = ''\n"
        "try:\n"
        f"    exec({code!r}, ns)\n"
        "    ans = str(ns.get('answer', ''))\n"
        "except Exception as e:\n"
        "    ok = False; err = repr(e)\n"
        "print(json.dumps({'ok': ok, 'answer': ans, 'err': err}))\n"
    )


def derive_ground_truth(code: str, claimed: str) -> str | None:
    """Run solution_code in the sandbox → derive the answer → confirm it matches `claimed`
    via the sympy oracle. Returns the sandbox-derived ground truth, or None to reject (II/X)."""
    res = run(_harness(code))
    if res.timed_out or res.payload is None or not res.payload.get("ok"):
        return None
    produced = str(res.payload.get("answer", ""))
    if not produced:
        return None
    # self-consistency: the generator's claimed answer must match what its own code computes (II)
    if verdict(canonical_answer(produced), canonical_answer(claimed)) != SUCCEEDED:
        return None
    return produced


def load_generated(conn: psycopg.Connection, path: Path) -> LoadResult:
    r = LoadResult()
    with conn.cursor() as cur:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            r.read += 1
            try:
                obj = json.loads(line)
            except Exception:
                r.rejected += 1
                continue
            q = obj.get("question")
            code = obj.get("solution_code")   # required for re-verification (R8)
            claimed = obj.get("answer")
            fam = obj.get("family")
            if not all(isinstance(x, str) and x for x in (q, code, claimed, fam)):
                r.rejected += 1
                continue
            try:
                pool = pool_for(fam)
            except ValueError:
                r.rejected += 1
                continue
            gt = derive_ground_truth(code, claimed)   # sandbox-derived authoritative truth (II/X)
            if gt is None:
                r.rejected += 1
                continue
            try:
                vec: str | None = to_pgvector(embed(q))
            except Exception:
                vec = None   # NULL-tolerant; backfillable (FR-006)
            cur.execute(
                "INSERT INTO benchmark_tasks "
                "(benchmark, problem_id, pool, domain, content, ground_truth, "
                " contamination_safe, family, embedding) "
                "VALUES ('qwen-gen', %s, %s, 'math', %s, %s, TRUE, %s, %s::vector) "
                "ON CONFLICT (problem_id) DO NOTHING",
                (problem_id(q), pool, q, gt, fam, vec),
            )
            if cur.rowcount == 0:
                r.duplicates += 1
            else:
                r.loaded += 1
        conn.commit()
    return r


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="benchmark_loader.load_generated")
    ap.add_argument("--in", dest="inp", type=Path, required=True)
    args = ap.parse_args(argv)
    conn = psycopg.connect(get_settings().db_dsn)
    try:
        res = load_generated(conn, args.inp)
    finally:
        conn.close()
    print(f"read={res.read} loaded={res.loaded} rejected={res.rejected} "
          f"duplicates={res.duplicates}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

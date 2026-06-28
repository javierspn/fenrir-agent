"""Download math benchmarks and partition into disjoint, deterministic pools
(FR-016, SC-005; research R7).

Partition is a pure function of the stable problem id (deterministic hash), so
re-runs reproduce the same split — idempotent and disjoint by construction. Raw
problems load contamination_safe=FALSE (likely in base-model pretraining); the
contamination-safe frozen set is the deferred eval-bench sub-step (bootstrap 5b).
"""
from __future__ import annotations

import hashlib

import psycopg

# (dataset, hf_path, config, split, revision). `revision` is PINNED for reproducible,
# contamination-stable loads (and required by bandit B615). Bump deliberately via renovate.
# Project Euler optional/out-of-band.
#
# MATH: hendrycks/competition_math was pulled from the Hub (P4.6). Replacement
# EleutherAI/hendrycks_math ships one config per subject (no "all" config), so the
# benchmark spans 7 entries that all land under benchmark="math". Fields: problem,
# level, type, solution (no separate answer — ground_truth falls back to solution;
# the eval phase extracts the \boxed{} value).
_MATH_SUBJECTS = (
    "algebra", "counting_and_probability", "geometry", "intermediate_algebra",
    "number_theory", "prealgebra", "precalculus",
)
DEFAULT_DATASETS = (
    {"benchmark": "gsm8k", "hf_path": "openai/gsm8k", "config": "main",
     "split": "train", "revision": "main"},
    *(
        {"benchmark": "math", "hf_path": "EleutherAI/hendrycks_math", "config": subj,
         "split": "train", "revision": "main"}
        for subj in _MATH_SUBJECTS
    ),
)
_TRAINING_SHARE = 70  # percent


def assign_pool(problem_id: str) -> str:
    """Deterministic 70/30 split keyed on the stable problem id (pure)."""
    digest = hashlib.sha256(problem_id.encode("utf-8")).hexdigest()
    bucket = int(digest, 16) % 100
    return "training" if bucket < _TRAINING_SHARE else "evaluation"


def _insert(conn: psycopg.Connection, rows: list[dict]) -> None:
    with conn.cursor() as cur:
        for r in rows:
            cur.execute(
                "INSERT INTO benchmark_tasks "
                "(benchmark, problem_id, pool, difficulty, domain, content, ground_truth, "
                " contamination_safe) "
                "VALUES (%s, %s, %s, %s, 'mathematics', %s, %s, FALSE) "
                "ON CONFLICT (problem_id) DO NOTHING",
                (
                    r["benchmark"], r["problem_id"], assign_pool(r["problem_id"]),
                    r.get("difficulty"), r["content"], r["ground_truth"],
                ),
            )
    conn.commit()


def load_and_partition(conn: psycopg.Connection, datasets_spec=DEFAULT_DATASETS) -> dict:
    """Download + partition + insert. Returns per-pool counts. Requires network +
    the `datasets` library (heavy; runs in the one-shot benchmark-loader container)."""
    from datasets import load_dataset

    for spec in datasets_spec:
        try:
            # revision IS pinned via spec["revision"]; bandit B615 only accepts a string
            # literal and can't resolve the dict value — justified suppression.
            ds = load_dataset(  # nosec B615
                spec["hf_path"], spec.get("config"), split=spec["split"], revision=spec["revision"]
            )
        except Exception as exc:  # one bad/renamed/gated source must not abort bootstrap
            print(f"WARN: skipping benchmark {spec['benchmark']} ({spec['hf_path']}): {exc}")
            continue
        # Include config in the id only when it adds discriminating info (math's 7
        # subjects all share benchmark="math"); gsm8k's "main" keeps the legacy
        # "{benchmark}-{split}-{i}" form so already-loaded rows stay idempotent.
        cfg = spec.get("config")
        prefix = (
            f"{spec['benchmark']}-{cfg}" if cfg and cfg not in ("main", "default")
            else spec["benchmark"]
        )
        rows = []
        for i, ex in enumerate(ds):
            pid = f"{prefix}-{spec['split']}-{i}"
            rows.append(
                {
                    "benchmark": spec["benchmark"],
                    "problem_id": pid,
                    "difficulty": str(ex.get("level", "")) or None,
                    "content": ex.get("question") or ex.get("problem") or "",
                    "ground_truth": ex.get("answer") or ex.get("solution") or "",
                }
            )
        _insert(conn, rows)

    with conn.cursor() as cur:
        cur.execute("SELECT pool, count(*) FROM benchmark_tasks GROUP BY pool")
        return dict(cur.fetchall())


def main() -> int:
    from fenrir import db

    conn = db.connect()
    try:
        pools = load_and_partition(conn)
        print(f"benchmarks loaded: {pools}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

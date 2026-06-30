"""006 loader — JSONL → sandbox-verified → benchmark_tasks (real pgvector via migrated_conn;
migration 0009). The sandbox + embedder are stubbed so we test the load/verify/idempotency logic
without Docker/Ollama; the verifier (sympy oracle) runs for real."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmark_loader import load_generated as lg

pytestmark = pytest.mark.usefixtures("migrated_conn")


class _Res:
    def __init__(self, answer, ok=True, timed_out=False):
        self.timed_out = timed_out
        self.payload = (None if (timed_out or answer is None)
                        else {"ok": ok, "answer": answer, "err": ""})


@pytest.fixture()
def stub_sandbox(monkeypatch):
    """sandbox.run → echoes a fixed derived answer; embed → dummy 768-vec."""
    monkeypatch.setattr(lg, "run", lambda program, **k: _Res("12"))
    monkeypatch.setattr(lg, "embed", lambda text: [0.0] * 768)
    monkeypatch.setattr(lg, "to_pgvector", lambda vec: "[" + ",".join("0" for _ in vec) + "]")


def _jsonl(tmp_path, records) -> Path:
    p = tmp_path / "problems.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    return p


def _rec(q, fam="two-step-rate", answer="12", code="answer = 3*4"):
    return {"question": q, "answer": answer, "solution_code": code, "family": fam,
            "n_steps": 2, "source": "qwen-gen"}


def _count(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()[0]


def test_load_clean_row(migrated_conn, stub_sandbox, tmp_path):
    res = lg.load_generated(migrated_conn, _jsonl(tmp_path, [_rec("Three boxes of 4 each?")]))
    assert res.loaded == 1 and res.rejected == 0
    row = _count(migrated_conn,
                 "SELECT count(*) FROM benchmark_tasks WHERE benchmark='qwen-gen' "
                 "AND contamination_safe=TRUE AND family='two-step-rate' AND ground_truth='12'")
    assert row == 1   # SC-001/SC-002 (ground_truth = sandbox-derived '12')


def test_reload_is_idempotent(migrated_conn, stub_sandbox, tmp_path):
    f = _jsonl(tmp_path, [_rec("Three boxes of 4 each?")])
    lg.load_generated(migrated_conn, f)
    res2 = lg.load_generated(migrated_conn, f)
    assert res2.loaded == 0 and res2.duplicates == 1   # SC-004
    assert _count(
        migrated_conn,
        "SELECT count(*) FROM benchmark_tasks WHERE benchmark='qwen-gen'") == 1


def test_claimed_vs_derived_mismatch_rejected(migrated_conn, stub_sandbox, tmp_path):
    # sandbox derives '12' (stub) but the record claims '99' → self-inconsistent → reject (II)
    f = _jsonl(tmp_path, [_rec("Bad?", answer="99")])
    res = lg.load_generated(migrated_conn, f)
    assert res.rejected == 1 and res.loaded == 0
    assert _count(
        migrated_conn,
        "SELECT count(*) FROM benchmark_tasks WHERE benchmark='qwen-gen'") == 0


def test_transfer_family_pool(migrated_conn, stub_sandbox, tmp_path):
    lg.load_generated(migrated_conn, _jsonl(tmp_path, [_rec("Movers meet?", fam="distance-meet")]))
    assert _count(migrated_conn,
                  "SELECT count(*) FROM benchmark_tasks WHERE family='distance-meet' "
                  "AND pool='transfer'") == 1   # SC-005, III
    assert _count(migrated_conn,
                  "SELECT count(*) FROM benchmark_tasks WHERE family='distance-meet' "
                  "AND pool='training'") == 0


def test_missing_solution_code_rejected(migrated_conn, stub_sandbox, tmp_path):
    bad = {"question": "No code?", "answer": "12", "family": "two-step-rate", "n_steps": 2}
    res = lg.load_generated(migrated_conn, _jsonl(tmp_path, [bad]))
    assert res.rejected == 1 and res.loaded == 0   # R8 — no solution_code → can't verify → skip

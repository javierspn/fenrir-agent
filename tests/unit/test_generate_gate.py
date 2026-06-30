"""006 generator — host gate + families + stable id (pure unit, no model, no DB)."""
from __future__ import annotations

from benchmark_loader import families
from benchmark_loader.generate import _strip_fences, validate
from benchmark_loader.load_generated import problem_id


def _obj(question, code, n_steps=2):
    return {"question": question, "solution_code": code, "n_steps": n_steps,
            "_family": "two-step-rate"}


# --- validate() accept + reject classes (FR-003, SC-003, U3) ---

def test_validate_accepts_clean_and_keeps_solution_code():
    rec = validate(_obj("Three boxes hold 4 each. How many?", "answer = 3*4"))
    assert rec is not None
    assert rec["answer"] == "12" and rec["source"] == "qwen-gen"
    assert rec["solution_code"] == "answer = 3*4"   # R8 — loader needs it
    assert rec["family"] == "two-step-rate"


def test_validate_rejects_irrational_answer():
    assert validate(_obj("Diagonal of a 2 unit square?", "answer = sqrt(2)")) is None  # not clean


def test_validate_accepts_rational():
    rec = validate(_obj("Split 1 pizza among 3.", "answer = Rational(1,3)"))
    assert rec is not None and rec["answer"] == "1/3"


def test_validate_allows_sympy_import():
    # models naturally write `import sympy as sp`; gate must allow it (matches the sandbox)
    rec = validate(_obj("3 boxes of 4 each?", "import sympy as sp\nanswer = sp.Integer(3*4)"))
    assert rec is not None and rec["answer"] == "12"


def test_validate_rejects_forbidden_token():
    assert validate(_obj("Files in 2 dirs?", "import os\nanswer = 2")) is None


def test_validate_rejects_hidden_constant():
    # question has 7, code never uses it
    assert validate(_obj("After 7 days, 3 plus 4?", "answer = 3+4")) is None


def test_validate_rejects_leaked_answer():
    # answer 12 appears in the question text
    assert validate(_obj("3 times 4 (it is 12 right?)", "answer = 3*4")) is None


def test_validate_rejects_crash():
    assert validate(_obj("2 over 0?", "answer = 1/0")) is None


def test_strip_fences_tolerant():
    assert _strip_fences('```json\n{"a":1}\n```') == '{"a":1}'   # U3


# --- families (FR-005, SC-005) ---

def test_every_family_has_one_pool():
    assert set(families.FAMILY_POOL) == set(families.FAMILY_NAMES)


def test_transfer_family_never_trains():
    pools = families.FAMILY_POOL
    assert "transfer" in pools.values()
    for fam, pool in pools.items():
        if pool == "transfer":
            assert families.pool_for(fam) == "transfer"   # whole-family, never training


def test_pool_for_unknown_raises():
    import pytest
    with pytest.raises(ValueError):
        families.pool_for("not-a-family")


# --- stable, idempotent problem_id (FR-004, R3) ---

def test_problem_id_stable_and_normalized():
    a = problem_id("  Three  boxes hold 4 each. ")
    b = problem_id("three boxes hold 4 each.")
    assert a == b and a.startswith("qwen-gen-")

"""US1 (T017): the verifier is the sole adjudicator and is independent of the proposer.
SC-002, FR-013/014, Constitution VIII.
"""
from __future__ import annotations

from fenrir.verify import sympy_oracle


def test_sympy_is_sole_oracle():
    # symbolic equivalence, not textual match
    assert sympy_oracle.verdict("2*x + 2*x", "4*x") == sympy_oracle.SUCCEEDED
    assert sympy_oracle.verdict("1/2", "0.5") == sympy_oracle.SUCCEEDED
    # textually similar but wrong
    assert sympy_oracle.verdict("4*x + 1", "4*x") == sympy_oracle.FAILED
    # un-parseable → unverified (never silently a success)
    assert sympy_oracle.verdict("", "4") == sympy_oracle.UNVERIFIED
    assert sympy_oracle.verdict("@@@", "4") == sympy_oracle.UNVERIFIED


def test_canonical_answer_extracts_benchmark_formats():
    ca = sympy_oracle.canonical_answer
    assert ca("...\n#### 200") == "200"                       # gsm8k
    assert ca("...#### 11,000") == "11000"                    # gsm8k thousands sep
    assert ca("the answer is $\\boxed{5000}$.") == "5000"     # math boxed
    assert ca("$\\boxed{\\frac{1}{2}}$") == "(1)/(2)"          # math frac
    assert ca("\\boxed{18}") == "18"


def test_verdict_never_crashes_on_raw_solution_text():
    """parse_expr can raise TokenError/etc. on a full multi-line solution — must be caught
    and returned as unverified, never propagate (this crashed a live cohort)."""
    raw = "He treats 20*.2=4 extra\nSo 44*5=220\n#### 11000"
    assert sympy_oracle.verdict("11000", raw) == sympy_oracle.UNVERIFIED  # raw won't parse
    # but after canonical extraction it verifies
    assert sympy_oracle.verdict(
        sympy_oracle.canonical_answer("11000"), sympy_oracle.canonical_answer(raw)
    ) == sympy_oracle.SUCCEEDED


def test_verdict_on_extracted_benchmark_answers():
    ca = sympy_oracle.canonical_answer
    # the live-cohort cases: model answer vs full-solution ground_truth, post-extraction
    assert sympy_oracle.verdict(ca("200"), ca("...#### 200")) == sympy_oracle.SUCCEEDED
    assert sympy_oracle.verdict(ca("5000"), ca("$\\boxed{5000}$")) == sympy_oracle.SUCCEEDED
    assert sympy_oracle.verdict(ca("1/2"), ca("$\\boxed{\\frac{1}{2}}$")) == sympy_oracle.SUCCEEDED
    assert sympy_oracle.verdict(ca("19"), ca("#### 200")) == sympy_oracle.FAILED


def test_verdict_does_not_consult_a_model():
    """The verifier function imports only sympy — no LLM/proxy import path. A confident
    but wrong answer is still FAILED (judge independent of the proposer's confidence)."""
    import inspect

    src = inspect.getsource(sympy_oracle.verdict)
    assert "proxy" not in src and "anthropic" not in src and "ollama" not in src.lower()
    assert sympy_oracle.verdict("999", "4") == sympy_oracle.FAILED

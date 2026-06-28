"""sympy ground-truth oracle (002, T012). Constitution II/VIII, I.

The SOLE adjudicator of correctness — symbolic equivalence only, never textual
match or LLM-judge. Verdict ∈ {succeeded, failed, unverified}. ``verdict()`` is a
pure function (used by unit tests and run *inside* the sandbox via ``VERIFY_PROGRAM``
so the verdict is produced by a process independent of the solver — separation of
powers). Contract: contracts/verifier.contract.md
"""
from __future__ import annotations

import re

SUCCEEDED = "succeeded"
FAILED = "failed"
UNVERIFIED = "unverified"


def _last_boxed(s: str) -> str | None:
    """Extract the content of the last \\boxed{...} with brace matching."""
    idx = s.rfind("\\boxed")
    if idx < 0:
        return None
    i = s.find("{", idx)
    if i < 0:
        return None
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1:j]
    return None


def canonical_answer(s: str) -> str:
    """Reduce a benchmark ground-truth (full solution) or a model answer to its final answer.

    GSM8K stores the solution ending in ``#### <answer>``; MATH wraps the answer in
    ``\\boxed{...}``. Then strip light LaTeX so sympy can parse the common numeric/fraction
    cases (FR-013). Genuinely non-sympy answers (e.g. ``\\text{A}``) stay as-is and will be
    reported ``unverified`` downstream — honest (the edge case: no checkable ground truth)."""
    s = str(s)
    if "####" in s:
        s = s.split("####")[-1]
    boxed = _last_boxed(s)
    if boxed is not None:
        s = boxed
    # light LaTeX normalisation
    s = re.sub(r"\\text\s*\{([^}]*)\}", r"\1", s)
    s = re.sub(r"\\d?frac\s*\{([^}]*)\}\s*\{([^}]*)\}", r"(\1)/(\2)", s)
    for tok in ("\\!", "\\,", "\\;", "\\left", "\\right", "\\$", "$", "\\%", "%"):
        s = s.replace(tok, "")
    s = s.strip().strip(".").strip()
    # thousands separators only when the result is otherwise a plain number
    if re.fullmatch(r"-?[\d,]+(\.\d+)?", s):
        s = s.replace(",", "")
    return s


def verdict(candidate: str, ground_truth: str) -> str:
    """Symbolic-equivalence verdict. ``unverified`` when sympy cannot parse/decide;
    such results are NEVER counted as success or used to crystallize (FR-015)."""
    import sympy
    from sympy.parsing.sympy_parser import parse_expr

    if candidate is None or str(candidate).strip() == "":
        return UNVERIFIED
    try:
        c = parse_expr(str(candidate), evaluate=True)
        t = parse_expr(str(ground_truth), evaluate=True)
    except Exception:  # parse can raise SympifyError/SyntaxError/TokenError/etc. — all → unverified
        return UNVERIFIED
    try:
        diff = sympy.simplify(c - t)
        if diff == 0:
            return SUCCEEDED
        # relational / set fallbacks
        if sympy.simplify(sympy.nsimplify(c) - sympy.nsimplify(t)) == 0:
            return SUCCEEDED
        return FAILED
    except Exception:
        return UNVERIFIED


# The sandbox image has only sympy (not the fenrir package), so the in-container program inlines
# the verdict logic. The candidate is DATA on stdin, not code. This is the source the runner ships:
SANDBOX_VERIFY_SOURCE = '''
import sys, json
import sympy
from sympy.parsing.sympy_parser import parse_expr
def verdict(candidate, ground_truth):
    if candidate is None or str(candidate).strip() == "":
        return "unverified"
    try:
        c = parse_expr(str(candidate), evaluate=True)
        t = parse_expr(str(ground_truth), evaluate=True)
    except Exception:
        return "unverified"
    try:
        if sympy.simplify(c - t) == 0:
            return "succeeded"
        return "failed"
    except Exception:
        return "unverified"
d = json.load(sys.stdin)
print(json.dumps({"verdict": verdict(d.get("candidate",""), d.get("ground_truth",""))}))
'''


def verify_in_sandbox(candidate: str, ground_truth: str) -> str:
    """Run the verdict inside the `--network none` sandbox (independent process, VIII)."""
    from fenrir.sandbox.runner import run

    res = run(SANDBOX_VERIFY_SOURCE, {"candidate": candidate, "ground_truth": ground_truth})
    if res.timed_out or res.payload is None:
        return UNVERIFIED
    return res.payload.get("verdict", UNVERIFIED)

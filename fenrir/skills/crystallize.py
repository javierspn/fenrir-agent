"""Skill crystallization — produce a code+self_test candidate (002, T025).

Constitution: skills are stored as executable code plus a self_test, never free text
(FR-022). The candidate is distilled by the crystallizer role through the proxy. Admission
(an independent verification pass) happens in admit.py.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from fenrir.core import proxy_call  # the single proxy egress (X)

_CODE_RE = re.compile(r"```(?:python)?\n(.*?)```", re.DOTALL)


@dataclass
class SkillCandidate:
    name: str
    code: str        # executable python (a solve function)
    self_test: str   # asserts the code reproduces the verified answer
    problem: str = ""  # the originating problem text — embedded so retrieval can find the skill


def _prompt(problem: str, answer: str, reasoning: str) -> str:
    return (
        "Turn this solved math problem into a reusable Python skill.\n"
        "Return TWO fenced ```python blocks:\n"
        "  1) a function `solve()` that returns the answer as a sympy-parseable string;\n"
        "  2) a `self_test()` that asserts solve() reproduces the known answer.\n\n"
        f"Problem:\n{problem}\n\nKnown answer: {answer}\n\nReasoning:\n{reasoning}\n"
    )


def _slug(problem: str) -> str:
    words = re.findall(r"[a-z0-9]+", problem.lower())[:4]
    return "skill_" + "_".join(words or ["math"])


def make_candidate(problem: str, answer: str, reasoning: str) -> SkillCandidate:
    """Ask the crystallizer (small model via proxy) for code + self_test."""
    out = proxy_call("crystallize", "small", _prompt(problem, answer, reasoning),
                     role="crystallizer")
    blocks = _CODE_RE.findall(out.get("text", ""))
    code = blocks[0].strip() if blocks else f"def solve():\n    return {answer!r}\n"
    self_test = (blocks[1].strip() if len(blocks) > 1
                 else f"def self_test():\n    assert str(solve()).strip() == {answer!r}\n")
    return SkillCandidate(name=_slug(problem), code=code, self_test=self_test, problem=problem)

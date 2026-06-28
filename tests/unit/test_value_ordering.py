"""003 increment A — value() ordering (significance.contract Invariant 3, SC-002).

The reward-magnitude bookmark must order outcomes skill-yielding ≥ teacher-taught ≥
from-scratch, all strictly above failed ≥ unverified, and must never be a flat constant.
"""
from __future__ import annotations

from fenrir.memory.salience import salience, value
from fenrir.verify.sympy_oracle import FAILED, SUCCEEDED, UNVERIFIED


def test_value_strict_ordering():
    scratch = value(SUCCEEDED, escalated=False, crystallized=False)
    teacher = value(SUCCEEDED, escalated=True, crystallized=False)
    skill = value(SUCCEEDED, escalated=True, crystallized=True)
    skill_scratch = value(SUCCEEDED, escalated=False, crystallized=True)

    # skill-yielding ≥ teacher-taught ≥ from-scratch (SC-002)
    assert skill >= teacher >= scratch
    assert skill_scratch >= scratch
    # crystallized and escalated each lift value above the bare success
    assert teacher > scratch
    assert skill > teacher


def test_success_beats_failed_beats_unverified():
    scratch = value(SUCCEEDED, escalated=False, crystallized=False)
    failed = value(FAILED, escalated=False, crystallized=False)
    unverified = value(UNVERIFIED, escalated=False, crystallized=False)
    assert scratch > failed >= unverified > 0.0


def test_value_is_not_constant():
    """The standing bug was importance=1.0 for everything. Assert outcomes diverge."""
    scores = {
        value(SUCCEEDED, escalated=False, crystallized=False),
        value(SUCCEEDED, escalated=True, crystallized=False),
        value(SUCCEEDED, escalated=True, crystallized=True),
        value(FAILED, escalated=False, crystallized=False),
    }
    assert len(scores) == 4  # all distinct — value is live


def test_zero_factor_floors_salience():
    """Product form: a zero in any factor drops salience to the floor."""
    assert salience(0.0, 5.0, 9) == 0.0          # zero surprise
    assert salience(0.5, 0.0, 9) == 0.0          # zero value
    assert salience(0.5, 5.0, -1) == 0.0         # (retrieval_count + 1) == 0

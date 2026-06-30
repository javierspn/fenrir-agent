"""T014 [US2]: external-quota arithmetic (selection.contract C4, FR-004, SC-005).

The per-cohort plan guarantees >= ceil(fraction·n) external slots for every n — by
construction, not in expectation — so the ≥30% guard holds on 100% of cohorts incl. small n.
"""
from __future__ import annotations

import math

import pytest

from fenrir.curriculum import external_slot_plan


@pytest.mark.parametrize("n", [1, 2, 3, 5, 7, 10, 33, 100, 200])
@pytest.mark.parametrize("frac", [0.30, 0.5, 0.10])
def test_at_least_ceil_external_slots(n, frac):
    plan = external_slot_plan(n, frac)
    assert len(plan) == n
    k = sum(plan)
    assert k == min(n, math.ceil(frac * n))      # exactly ceil, no over/under
    assert k / n >= frac - 1e-9                   # never below the floor fraction


def test_zero_and_empty():
    assert external_slot_plan(0, 0.3) == []
    assert external_slot_plan(4, 0.0) == [False, False, False, False]


def test_slots_are_spread_not_clustered():
    # n=10, frac=0.30 → 3 external slots, evenly spread (not all at the front)
    plan = external_slot_plan(10, 0.30)
    idx = [i for i, x in enumerate(plan) if x]
    assert len(idx) == 3
    assert max(idx) - min(idx) >= 5               # genuinely spread across the cohort

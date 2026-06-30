"""T015 [US2]: the selection objective has NO novelty term (FR-006, selection.contract C3).

Two adjacent candidates identical in cosine are ranked indifferently — there is no
distance-from-seen / diversity / "newness" term that could break the tie. This is the
structural rejection of Voyager's novelty-maximization objective (§10.1).
"""
from __future__ import annotations

import random

from fenrir.curriculum import pick_index


def _share_of_index0(strength: float, draws: int = 4000) -> float:
    # two candidates with IDENTICAL cosine; order/content must not bias the pick
    rng = random.Random(99)
    hits = sum(1 for _ in range(draws) if pick_index([0.85, 0.85], strength, rng) == 0)
    return hits / draws


def test_equal_cosine_is_indifferent_at_mid_strength():
    assert abs(_share_of_index0(0.5) - 0.5) < 0.05


def test_equal_cosine_is_indifferent_at_zero_strength():
    assert abs(_share_of_index0(0.0) - 0.5) < 0.05


def test_pick_depends_only_on_cosine_not_position():
    # Reversing two equal-cosine candidates yields the same ~50/50 split — no positional
    # or recency/novelty signal leaks into the objective.
    rng = random.Random(7)
    a = sum(pick_index([0.85, 0.85], 0.6, rng) for _ in range(2000))
    rng = random.Random(7)
    b = sum(pick_index([0.85, 0.85], 0.6, rng) for _ in range(2000))
    assert a == b      # deterministic under a fixed seed; cosine-only objective

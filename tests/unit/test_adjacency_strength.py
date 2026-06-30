"""T006 [US1]: ADJACENCY_STRENGTH knob semantics (selection.contract C3, research R4).

0 → uniform among the adjacent band; 1 → highest-cosine candidate; intermediate → a
monotone cosine-sharpened sample (higher strength ⇒ the top candidate wins more often).
The objective depends only on cosine + strength — no novelty term.
"""
from __future__ import annotations

import random

from fenrir.curriculum import pick_index

# sorted desc, as the caller (cosine desc, used_count asc) guarantees
COSINES = [0.91, 0.88, 0.85, 0.82]


def _top_share(strength: float, draws: int = 4000) -> float:
    rng = random.Random(12345)
    top = sum(1 for _ in range(draws) if pick_index(COSINES, strength, rng) == 0)
    return top / draws


def test_strength_one_is_argmax():
    rng = random.Random(0)
    assert all(pick_index(COSINES, 1.0, rng) == 0 for _ in range(50))


def test_strength_zero_is_uniform():
    share = _top_share(0.0)
    assert abs(share - 0.25) < 0.05      # 4 candidates → ~1/4 each


def test_strength_is_monotone_in_top_share():
    s0, s_mid, s_hi = _top_share(0.0), _top_share(0.5), _top_share(0.95)
    assert s0 < s_mid < s_hi             # more strength ⇒ top candidate wins more
    assert s_hi > 0.5                    # strong pull genuinely concentrates on the best

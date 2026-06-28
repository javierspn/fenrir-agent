"""003 increment C — replay sampling + clustering primitives (consolidation.contract 3/5/8).

Pure-function coverage for the over-merge guard, greedy clustering, and the seeded
weighted-with-replacement draw (reproducible, weight-monotonic, terminates under budget).
"""
from __future__ import annotations

import math
import random

import pytest

from fenrir.consolidation.sleep import _cluster, _cosine


def _ang(theta_deg: float) -> list[float]:
    """A 768-dim unit vector living in the first two dims at angle theta — cosine between two
    such vectors is cos(Δtheta), so geometry is exact and easy to reason about."""
    t = math.radians(theta_deg)
    return [math.cos(t), math.sin(t)] + [0.0] * 766


def _ep(idx, theta, eff=1.0):
    return {"id": idx, "content": "c", "domain": "math", "vec": _ang(theta), "eff": eff}


def test_cosine_basic():
    assert _cosine(_ang(0), _ang(0)) == pytest.approx(1.0)
    assert _cosine(_ang(0), _ang(90)) == pytest.approx(0.0, abs=1e-9)
    assert _cosine(_ang(0), _ang(60)) == pytest.approx(0.5)   # cos 60° = 0.5


def test_cluster_groups_near_duplicates():
    eps = [_ep(i, theta) for i, theta in enumerate([0, 1, 2, 1.5])]
    clusters = _cluster(eps, sim_floor=0.85, max_spread=0.25)
    assert len(clusters) == 1 and len(clusters[0]) == 4


def test_cluster_separates_distinct_methods():
    eps = [_ep(0, 0), _ep(1, 0.5), _ep(2, 89), _ep(3, 89.5)]
    clusters = _cluster(eps, sim_floor=0.85, max_spread=0.25)
    assert len(clusters) == 2


def test_over_merge_guard_splits_incoherent():
    # all within sim_floor of the seed (0.866 ≥ 0.85) but B·C = cos60 = 0.5 → spread 0.5 > 0.25
    eps = [_ep(0, 0), _ep(1, 30), _ep(2, -30)]
    clusters = _cluster(eps, sim_floor=0.85, max_spread=0.25)
    assert all(len(cl) == 1 for cl in clusters)   # split back to singletons, not collapsed


def test_weighted_draw_reproducible_and_monotonic():
    weights = [10.0, 1.0]
    a = random.Random(1).choices([0, 1], weights=weights, k=200)
    b = random.Random(1).choices([0, 1], weights=weights, k=200)
    assert a == b                                  # reproducible under fixed seed
    assert a.count(0) > a.count(1)                 # higher weight drawn more (competition)
    assert len(a) == 200                           # terminates at budget

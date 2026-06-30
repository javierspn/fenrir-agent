"""T005 [US1]: adjacency-band classification (selection.contract C2, research R2).

A candidate's max-skill cosine is classified into infeasible / adjacent / trivial; the
feasibility gate keeps only the *adjacent* band. Boundaries land in the documented band.
"""
from __future__ import annotations

from fenrir.curriculum import classify

FLOOR = 0.80
CEIL = 0.92


def test_below_floor_is_infeasible():
    assert classify(0.0, FLOOR, CEIL) == "infeasible"
    assert classify(0.79999, FLOOR, CEIL) == "infeasible"


def test_in_band_is_adjacent():
    assert classify(0.80, FLOOR, CEIL) == "adjacent"      # floor is inclusive
    assert classify(0.86, FLOOR, CEIL) == "adjacent"
    assert classify(0.91999, FLOOR, CEIL) == "adjacent"


def test_at_or_above_ceil_is_trivial():
    assert classify(0.92, FLOOR, CEIL) == "trivial"       # ceil is exclusive → trivial
    assert classify(1.0, FLOOR, CEIL) == "trivial"


def test_only_adjacent_passes_the_gate():
    bands = [classify(c, FLOOR, CEIL) for c in (0.5, 0.80, 0.88, 0.95)]
    assert bands == ["infeasible", "adjacent", "adjacent", "trivial"]

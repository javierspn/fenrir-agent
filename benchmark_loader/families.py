"""Solution-method families for the contamination-safe generator (006, D13).

Each family is ONE solution method — solving instance 1 should make instances 2..N cheaper
(the within-family reuse test). The family→pool map is whole-family (Constitution III): a family
is never split across pools, and >=1 family is reserved wholly to the held-out transfer pool.
"""
from __future__ import annotations

# (name, method-description) — the description seeds the generator prompt.
FAMILIES: list[tuple[str, str]] = [
    ("two-step-rate", "rate × time then a second arithmetic step"),
    ("system-2eq", "two linear equations in two unknowns"),
    ("percent-of-percent", "successive percentage changes"),
    ("ratio-split", "split a total in a given ratio"),
    ("work-combined", "combined work rates (A and B together)"),
    ("age-problem", "ages now vs. in N years, one relation"),
    ("unit-conversion", "multi-step unit conversion then arithmetic"),
    ("avg-backfill", "find the missing value given a target average"),
    ("interest-simple", "simple interest then a follow-up step"),
    ("distance-meet", "two movers closing a gap, find meet time"),
]

FAMILY_NAMES: list[str] = [n for n, _ in FAMILIES]

# Whole-family pool assignment (III). distance-meet is held wholly OUT of training (transfer);
# age-problem is the within-distribution held-out (evaluation); the rest train.
FAMILY_POOL: dict[str, str] = {
    "two-step-rate": "training",
    "system-2eq": "training",
    "percent-of-percent": "training",
    "ratio-split": "training",
    "work-combined": "training",
    "unit-conversion": "training",
    "avg-backfill": "training",
    "interest-simple": "training",
    "age-problem": "evaluation",   # held-out, within-distribution
    "distance-meet": "transfer",   # held-out, never trained on (III)
}

assert set(FAMILY_POOL) == set(FAMILY_NAMES), "every family needs exactly one pool"
assert "transfer" in FAMILY_POOL.values(), "reserve >=1 family to transfer (III)"


def pool_for(family: str) -> str:
    """Whole-family pool for a family name. Raises on an unknown family."""
    try:
        return FAMILY_POOL[family]
    except KeyError as exc:
        raise ValueError(f"unknown family: {family!r}") from exc

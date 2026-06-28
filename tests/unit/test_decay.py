"""003 increment B — read-time decay math (decay.contract Invariant 2, SC-003).

effective_salience() must equal the stored salience at age 0, halve every
DECAY_HALFLIFE_DAYS, decrease monotonically with age, and fall back to created_at when
last_reactivated_at is NULL — all without mutating the stored value.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from fenrir.memory.salience import effective_salience
from fenrir.settings import get_settings

NOW = datetime(2026, 6, 28, 12, 0, 0, tzinfo=timezone.utc)


def test_age_zero_equals_stored():
    assert effective_salience(2.0, NOW, NOW, now=NOW) == pytest.approx(2.0)


def test_halves_at_one_half_life():
    hl = get_settings().DECAY_HALFLIFE_DAYS
    created = NOW - timedelta(days=hl)
    assert effective_salience(2.0, None, created, now=NOW) == pytest.approx(1.0, rel=1e-9)


def test_quarter_at_two_half_lives():
    hl = get_settings().DECAY_HALFLIFE_DAYS
    created = NOW - timedelta(days=2 * hl)
    assert effective_salience(2.0, None, created, now=NOW) == pytest.approx(0.5, rel=1e-9)


def test_monotonic_decreasing_in_age():
    created_old = NOW - timedelta(days=30)
    created_new = NOW - timedelta(days=1)
    older = effective_salience(1.0, None, created_old, now=NOW)
    newer = effective_salience(1.0, None, created_new, now=NOW)
    assert older < newer < 1.0


def test_null_reactivation_falls_back_to_created():
    created = NOW - timedelta(days=3)
    with_null = effective_salience(1.0, None, created, now=NOW)
    with_created_as_react = effective_salience(1.0, created, created, now=NOW)
    assert with_null == pytest.approx(with_created_as_react)


def test_reactivation_resets_clock():
    created = NOW - timedelta(days=30)          # very old
    reactivated = NOW - timedelta(hours=1)      # just touched
    faded = effective_salience(1.0, None, created, now=NOW)
    fresh = effective_salience(1.0, reactivated, created, now=NOW)
    assert fresh > faded
    assert fresh == pytest.approx(1.0, rel=1e-2)   # ~back to stored

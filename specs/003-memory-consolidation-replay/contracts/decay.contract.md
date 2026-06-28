# Contract — Passive forgetting via decay (increment B)

**Module**: `fenrir/memory/salience.py` (read-time decay helper) + `fenrir/memory/episodes.py`
+ `fenrir/memory/retrieval.py` (reactivation) + migration `0004`.

## Interface

```python
def effective_salience(salience: float, last_reactivated_at, created_at, *, now) -> float:
    """salience * exp(-ln2 * age_days / DECAY_HALFLIFE_DAYS),
       age_days = (now - COALESCE(last_reactivated_at, created_at)).days_fractional.
       Pure function; never mutates stored salience."""
```

SQL-side equivalent (used in consolidation candidate ranking / dashboard) MUST match the
Python form exactly:
```sql
salience * exp(-ln(2) * extract(epoch from (now() - coalesce(last_reactivated_at, created_at)))
               / (86400 * :half_life_days))
```

## Invariants

1. **Down-weight only** (FR-007, SC-004). Decay never UPDATEs `salience`, never deletes, never
   hides a row. Stored bookmark is immutable; decay exists only as a read-time multiplier.
2. **Monotonic** (SC-003). For two rows with equal stored `salience`, the one with the older
   `COALESCE(last_reactivated_at, created_at)` has strictly lower `effective_salience`.
3. **Anchor exemption** (FR-008). Anchored ground truth lives in `long_term_memory`
   (`is_anchor=true`, `decay_rate=0`) and is unaffected. STM carries no anchors.
4. **Reversible** (FR-009). `retrieval.py` surfacing an episode AND a won replay both set
   `last_reactivated_at = now()`, resetting age to 0.
5. **Tunable + observable** (FR-010/011). `DECAY_HALFLIFE_DAYS` in settings; dashboard panel
   plots `effective_salience` vs age.
6. **Migration** (FR-012). `0004_consolidation_replay.sql` adds only
   `short_term_memory.last_reactivated_at timestamptz` (nullable, no backfill). Presented for
   human confirmation before apply (XII).

## Tests (unit + integration)

- equal-salience pair, advance `now`, only one reactivated → idle `effective_salience` lower.
- anchor row: arbitrary age → unchanged.
- after decay, `SELECT` still returns the row in full (no delete/hide).
- reactivation resets age (effective bounces back to ~stored salience).
- Python `effective_salience` and the SQL expression agree within float tolerance.

# Contract — Significance bookmark (increment A)

**Module**: `fenrir/memory/salience.py` (single source of truth) + `fenrir/memory/episodes.py`
+ one call-site change in `fenrir/core.py`.

## Interface

```python
def value(verdict: str, *, escalated: bool, crystallized: bool) -> float:
    """Reward-magnitude bookmark, computed at write time. Constants from settings."""

def salience(prediction_error: float, value: float, retrieval_count: int) -> float:
    """THE single significance definition. = prediction_error * value * (retrieval_count + 1)."""
```

## Invariants

1. **One definition.** `recompute()` and `bump_retrieval_count()` MUST call `salience()` —
   no inline arithmetic. Given identical `(prediction_error, value, retrieval_count)`, every
   call site returns the identical score (SC-001).
2. **Live value.** `value()` is never the constant 1.0 for a write. `core.py` MUST pass
   `importance=value(verdict, escalated=…, crystallized=…)` into the `Episode` (today it
   passes nothing).
3. **Strict ordering** (SC-002). For equal `(prediction_error, retrieval_count)`:
   `value(SUCCEEDED, crystallized=True) ≥ value(SUCCEEDED, escalated=True) ≥
    value(SUCCEEDED)` and all three `> value(FAILED) ≥ value(UNVERIFIED)`.
4. **Factor inspectability** (FR-004). The three inputs remain separately readable from the
   episode row (`prediction_error`, `importance`, `retrieval_count`) — significance is
   reconstructable, not opaque.
5. **No schema change** (FR-005). Uses existing STM columns only.

## Tests (unit)

- `value()` ordering table: scratch < teacher < skill; success > failed > unverified.
- `salience()` is referenced (not re-implemented) by `recompute`/`bump_retrieval_count`
  (assert equality of outputs across the three entry points for random inputs).
- Zero in any factor floors significance (product form).

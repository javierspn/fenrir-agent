# Research — 003 Memory Consolidation Replay (Phase 0)

Three decisions were deferred from the spec (documented defaults, not blocking). Each is
resolved here against the **live code and schema**, not generic literature. Format:
Decision / Rationale / Alternatives considered.

---

## R1 — The single significance definition + the value signal (increment A)

**Decision.** One function is the sole definition of significance:

```
salience(prediction_error, value, retrieval_count)
    = prediction_error × value × (retrieval_count + 1)
```

where `value` (the "reward magnitude" bookmark) is computed **at write time** from outcomes
the loop already holds:

```
value(verdict, escalated, crystallized)
    = base(verdict) × (W_ESCALATED if escalated else 1) × (W_CRYSTALLIZED if crystallized else 1)

base(SUCCEEDED)   = 1.0
base(FAILED)      = W_FAIL      (default 0.2)
base(UNVERIFIED)  = W_UNVERIFIED(default 0.1)

W_ESCALATED    default 1.5     # teacher-taught win is expensive → more valuable
W_CRYSTALLIZED default 2.0     # yielded a reusable skill → most valuable
```

All weights live in `settings.py`. The existing `salience()` in `memory/salience.py` keeps
its signature; the inline duplicate formulas in `recompute()` / `bump_retrieval_count()` are
deleted and made to **call** `salience()` so there is exactly one definition (fixes the
1.0-vs-0.5 default drift). `core.py` passes `importance=value(...)` into the `Episode`
(today it passes nothing → inert 1.0).

**Rationale.** Multiplicative keeps the three factors orthogonal and individually
inspectable (FR-004): PE = surprise, value = worth, `(count+1)` = use. The ordering
skill-yielding ≥ teacher-taught ≥ from-scratch (SC-002) falls out of `2.0 ≥ 1.5 ≥ 1.0`.
Low base for failed/unverified means failures still persist (VI) but rarely win
consolidation — consistent with the existing gate that already rejects high-residual
clusters.

**Alternatives considered.**
- *Additive blend* (`α·PE + β·value + γ·use`) — rejected: a zero in any factor should floor
  significance (the brain's selective gate, R6 from 002); additive lets a high single factor
  mask a dead one, and the factors stop being separable.
- *Keep importance=1.0, lean on PE only* — rejected: that's the current bug; value is exactly
  the lottery-vs-everyday signal the redesign is about.
- *Learned weights* — rejected for the pilot: no labels, premature; constants are tunable and
  measurable first.

**Crystallized timing note.** Whether an attempt crystallized a skill is known slightly
*after* the episode is written in the current loop order. Resolution: compute `value` at the
point the loop already knows all three (the episode write is moved to after the crystallize
step, or `value` is finalized with a single `recompute` call once crystallization is known —
chosen at task time; both keep one definition). No double formula either way.

---

## R2 — Decay functional form + where it is applied (increment B)

**Decision.** **Exponential decay computed at READ time**, never written back:

```
effective_salience = salience × exp(-LN2 · age_days / DECAY_HALFLIFE_DAYS)
age_days = (now - COALESCE(last_reactivated_at, created_at)) in days
DECAY_HALFLIFE_DAYS  default 7.0     # settings.py, tunable
```

- The stored `salience` (the bookmark) is **immutable** — decay is a read-time multiplier
  used wherever significance drives a choice (consolidation cluster weighting, dashboard).
  This preserves the additive guarantee perfectly (VI): nothing is mutated or deleted.
- **Reactivation** (FR-009): `retrieval.py` and a won replay set
  `last_reactivated_at = now()`, resetting the clock. Reversible forgetting.
- **Anchor exemption** (FR-008): anchors are `long_term_memory` rows with
  `is_anchor = true`; their decay is governed by `long_term_memory.decay_rate`, set to `0`
  for anchors. Episodes (`short_term_memory`) carry no anchored ground truth, so the
  exemption is structurally satisfied — STM decays, the anchored facts in LTM do not.
- New column: `short_term_memory.last_reactivated_at timestamptz NULL` (migration 0004).
  NULL → fall back to `created_at`, so no backfill is needed.

**Rationale.** Exponential is the canonical forgetting curve (Ebbinghaus) and needs a single,
interpretable parameter (half-life in days — "an untouched everyday episode loses half its
weight in a week"). Read-time computation avoids a sweep job, is always correct regardless of
when consolidation last ran, and keeps the bookmark immutable (cleaner than mutating stored
salience on a timer, which would fight the additive principle and need locking).

**Alternatives considered.**
- *Linear decay* — rejected: no natural half-life, can cross zero/negative, needs clamping.
- *Mutate stored salience on a timer* — rejected: write amplification, lock contention,
  and it destroys the immutable-bookmark property (a faded row could no longer prove its
  original significance).
- *Add is_anchor to STM* — rejected as unnecessary: anchors already live in LTM with a
  `decay_rate` column; duplicating the flag onto STM would be schema sprawl (XI).

---

## R3 — Clustering threshold, replay budget, strength accrual (increment C)

**Decision.** Consolidation pass becomes:

1. **Candidate set** — raw episodes (`consolidation_status='raw'`) whose `effective_salience`
   is above a floor, training/held-out pool only.
2. **Cluster** — greedy agglomeration by embedding cosine ≥ `CLUSTER_SIM_FLOOR`
   (default **0.85**, tighter than retrieval's 0.80 — merging demands more similarity than
   recall). Uses the existing pgvector embeddings; O(n²) cosine at the current
   hundreds-scale backlog (a pgvector ANN path is noted for >~5k episodes).
3. **Competitive replay** — spend `REPLAY_BUDGET` draws (default **64**), sampling clusters
   **with replacement**, each cluster's weight = sum of its members' `effective_salience`.
   Stdlib `random` seeded per run (reproducible; ties broken by cluster id).
4. **Merge-to-one + strength accrual** — first draw of a cluster creates **one**
   `long_term_memory` abstraction (`source_memories` = all member ids); each subsequent draw
   reinforces it: `strength += STRENGTH_PER_REPLAY` (default **0.1**), `reinforcement_count
   += 1`, `last_reinforced_at = now()`. Members' `last_reactivated_at` refreshed (feeds B).
5. **Per-cluster predictability gate** (FR-017) — before the first merge of a cluster, run
   the held-out regression check on that cluster (reuse `predictability_improves`, applied to
   the whole member set). Fail → skip the cluster, leave members raw.
6. **Over-merge guard** (FR-018) — a cluster whose internal coherence is too low (max
   pairwise cosine distance above `COHERENCE_MAX_SPREAD`, default **0.25**) is split back to
   singletons before gating, so distinct methods are never collapsed into one mushy row.
7. **Additive + idempotent** (FR-020) — sources marked `consolidated`; already-consolidated
   episodes are excluded from the candidate set, so re-running produces no duplicate
   abstractions. Drift-flag (FR-019) runs unchanged after each merge.

Settings added: `CLUSTER_SIM_FLOOR=0.85`, `REPLAY_BUDGET=64`, `STRENGTH_PER_REPLAY=0.1`,
`COHERENCE_MAX_SPREAD=0.25`, `EFFECTIVE_SALIENCE_FLOOR` (small, e.g. 0.05).

**Rationale.** Weighted-with-replacement sampling is the faithful analogue of the replay
competition (winners replay repeatedly, strengthening cortical transfer); a fixed budget
bounds the pass deterministically. Merge-to-one with `source_memories` is exactly what the
existing LTM schema was built for (the column already exists, unused at scale). Per-cluster
gating + coherence guard directly answer the over-merge risk flagged in the spec.

**Alternatives considered.**
- *Deterministic top-K scan (status quo)* — rejected: no repetition, no competition, no
  generalization; it is the very behavior being replaced.
- *k-means / HDBSCAN* — rejected for the pilot: needs a tuned k or extra deps; greedy
  cosine-threshold is transparent, dependency-free, and adequate at current scale.
- *Strength = cluster size* — rejected: conflates "how many similar episodes" with "how hard
  it won the competition"; per-replay accrual measures the latter, which is the signal SC-005
  asks for.

---

## Cross-cutting

- **No new model calls** → no budget impact (IX). Embeddings already stored; clustering reads
  them.
- **Reproducibility** — every stochastic step (replay sampling) is seeded; the seed is logged
  on the `consolidation_runs` row so a pass can be replayed for audit.
- **Measurement** (SC-007/008) — three dashboard panels read existing columns:
  strength-vs-`reinforcement_count`, `effective_salience`-vs-age, and reuse = count of tasks
  whose solve drew on a consolidated abstraction over time. A flat reuse curve is a valid
  recorded negative result.

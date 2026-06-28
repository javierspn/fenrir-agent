# Feature Specification: Memory Consolidation Replay (hippocampal two-stage model)

**Feature Branch**: `003-memory-consolidation-replay`

**Created**: 2026-06-27

**Status**: Draft

**Input**: User description: "Redesign Fenrir's memory/consolidation subsystem to follow the hippocampal two-stage consolidation model (sharp-wave-ripple bookmarking + sleep replay). Three sequenced increments: (A) a single significance bookmark written at experience time, (B) passive forgetting via decay, (C) consolidation as competitive replay over clusters that merges many episodes into one abstraction. Scope is strictly the memory and consolidation subsystem plus a schema migration; the loop, verification, budget, sandbox, and skill crystallization are out of scope except as signal sources."

## Overview

The cognitive loop (002) records every attempt as an additive episode, tags it with a
"salience" score, and periodically runs a regulated "sleep" pass that promotes
high-salience episodes into long-term abstractions. That subsystem works but diverges
from the biological model it was inspired by, in three ways that this feature corrects.

The neuroscience reference (hippocampal sharp-wave ripples) describes a **two-stage**
mechanism: at experience time, a significant event is *bookmarked* by a local change;
later, during sleep, those bookmarks are *replayed in competition* — stronger ones win,
replay repeatedly, and transfer to cortex, while the unimportant fade. Crucially, replay
collapses *many* similar experiences into *one* generalized structure (a map), and the
significance that drives the competition is decided **once, at encoding**.

Today Fenrir: (1) computes significance in several places with inconsistent defaults and
leaves the "value" signal effectively unused; (2) has no notion of forgetting — nothing
ever fades; (3) consolidates by scanning the top-N salient episodes and copying each one
into its own abstraction — it accumulates but never generalizes. The third gap is the
suspected root cause of an observed project problem: consolidated knowledge is rarely
**reused**, so learning does not visibly compound.

**The deliverable is the measurement, not a guaranteed improvement.** Consistent with the
project thesis, this feature is instrumented to show — or honestly falsify — whether a
faithful two-stage model makes consolidated knowledge concentrate, decay, and get reused.
A flat result is a valid, recorded negative result.

This feature is delivered as three sequenced increments (A → B → C) behind one feature
branch, each independently valuable and testable.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A: One significance bookmark, written at encoding (Priority: P1)

The operator runs the loop. Each attempt is recorded with a single significance score that
is computed **once**, at the moment the episode is written, from three distinct and
individually meaningful signals: **surprise** (prediction error), **value** (was the answer
verified-correct, was it learned from the expensive teacher, did it yield a reusable skill),
and **use** (how often the episode is later re-accessed). There is exactly one definition of
significance in the system; the value signal is no longer an inert constant.

**Why this priority**: This is the foundation. Decay (B) and competitive replay (C) both
weight on significance, so significance must first be a single, trustworthy, meaningful
number. It also fixes a standing correctness bug (the value factor is currently a flat
constant, so significance reduces to surprise × use). Smallest change, unblocks the rest.

**Independent Test**: Write three episodes — a from-scratch verified success, a
teacher-taught (escalated) verified success, and a verified success that crystallized a
skill — with identical surprise and use. Assert their significance scores are strictly
ordered (skill-yielding ≥ teacher-taught ≥ from-scratch), proving the value signal is live
and distinct from surprise. Assert significance is computed by a single shared definition
(the same inputs produce the same score regardless of call site).

**Acceptance Scenarios**:

1. **Given** an episode is written at encoding time, **When** its significance is computed,
   **Then** it derives from surprise × value × use using one shared definition, and the
   stored score equals that definition's output.
2. **Given** two verified successes identical except that one was escalated to the teacher,
   **When** both are written, **Then** the escalated one has strictly higher value (and thus
   significance) than the non-escalated one.
3. **Given** a verified success that crystallized a skill, **When** it is written, **Then**
   its value reflects the skill outcome and exceeds an otherwise-identical success that did not.
4. **Given** an episode is later surfaced by retrieval, **When** its use count increases,
   **Then** its significance is recomputed by the same single definition — never a second,
   divergent formula.

---

### User Story 2 - B: Passive forgetting via decay (Priority: P2)

Over time, the significance of an episode that is neither re-accessed nor replayed **fades**,
so everyday attempts gradually sink while rare, high-value events stay prominent — the
"everyday memory fades, a lottery win lasts" curve. Forgetting is purely a down-weighting:
no episode is ever deleted or hidden from query, and **anchored ground-truth facts never
decay** (anchors live in long-term memory with `decay_rate=0`; raw episodes carry no anchor
flag and always decay). The decay rate is an operator-tunable setting
(`DECAY_HALFLIFE_DAYS`, distinct from the long-term-memory `decay_rate` column), and the
fade is observable on the dashboard.

**Why this priority**: Decay is what makes the replay competition (C) meaningful — without
fade, every old episode competes forever and the system cannot prioritize what was recently
and significantly learned. It is sequenced after A because it weights on the bookmark, and
before C because C's competition assumes a decaying field.

**Independent Test**: Write two episodes of equal initial significance; re-access one
repeatedly and leave the other idle while simulating the passage of time; assert the idle
one's effective significance drops below the re-accessed one, that both rows remain fully
queryable, and that a long-term abstraction flagged as an anchor (`is_anchor`, `decay_rate=0`)
does not decay at all.

**Acceptance Scenarios**:

1. **Given** two episodes with equal initial significance, **When** time passes and only one
   is re-accessed or replayed, **Then** the idle one's effective significance is strictly
   lower than the active one.
2. **Given** any decayed episode, **When** it is queried, **Then** its row is still present
   and readable in full — decay never deletes, hides, or hard-edits content.
3. **Given** a long-term abstraction flagged as an anchor (non-decaying ground truth,
   `is_anchor`/`decay_rate=0`), **When** arbitrary time passes with no access, **Then** its
   effective significance is unchanged. (Raw episodes carry no anchor flag and always decay.)
4. **Given** an operator sets the decay rate, **When** consolidation runs, **Then** the rate
   in effect is the configured value, and the resulting fade is visible on the dashboard.
5. **Given** a faded episode is re-accessed or wins a replay, **When** that happens, **Then**
   its effective significance is refreshed (forgetting is reversible by renewed relevance).

---

### User Story 3 - C: Consolidation as competitive replay over clusters (Priority: P3)

The regulated "sleep" pass stops copying each salient episode into its own abstraction and
instead **replays in competition**: similar episodes are grouped, a fixed replay budget is
spent drawing groups in proportion to their significance (with repetition, so high-value
groups are replayed many times), and each group is merged into a **single** abstraction whose
strength grows with how often it was replayed. The existing safety gate (an abstraction is
kept only if it does not regress on held-out problems) runs **per group**, with an added
check that guards against collapsing genuinely different methods into one. The drift-flag
safeguard is unchanged.

**Why this priority**: This is the highest-value change — it is what turns accumulation into
**generalization**, and is the suspected fix for knowledge not being reused. It is sequenced
last because it depends on a trustworthy bookmark (A) and a decaying field (B), and it carries
the largest blast radius (it replaces the core of the consolidation pass) so it should land on
a proven foundation.

**Independent Test**: Seed a cluster of K near-duplicate successful episodes plus several
unrelated ones; run one consolidation pass with a known replay budget; assert the K-cluster
produced exactly one abstraction linked to all K sources (not K abstractions), that its
strength reflects multiple replay hits rather than a constant, that a higher-significance
cluster received more replay draws than a lower one, and that an attempt to merge two
distinct methods is blocked by the per-group regression check.

**Acceptance Scenarios**:

1. **Given** a group of similar successful episodes, **When** a consolidation pass runs,
   **Then** they are merged into exactly one abstraction whose source list contains every
   member of the group.
2. **Given** two groups of unequal significance, **When** the replay budget is spent, **Then**
   the higher-significance group is drawn (replayed) more often than the lower one.
3. **Given** a group replayed multiple times, **When** its abstraction is written, **Then**
   the abstraction's strength increases with replay count rather than being a fixed value.
4. **Given** a candidate merge that would regress on the held-out problem slice, **When** the
   per-group gate evaluates it, **Then** the merge is rejected and the source episodes remain
   unconsolidated.
5. **Given** any consolidation pass, **When** it completes, **Then** all source episodes are
   marked consolidated and none are deleted (additive guarantee preserved).
6. **Given** the evaluation pool, **When** any consolidation or held-out check runs, **Then**
   it draws only from the training/held-out slice and never reads the evaluation pool.

---

### Edge Cases

- **Empty or singleton clusters**: an episode with no similar peers either forms a
  one-member group (still gated) or is left unconsolidated — never forced into a spurious merge.
- **All episodes decayed below a floor**: a consolidation pass with nothing above the
  significance floor does no merges and records an empty-but-successful run (not an error).
- **Decay vs. anchor conflict**: an old anchored abstraction (LTM `is_anchor`/`decay_rate=0`)
  must not decay — the anchor rule wins. (Raw episodes are never anchors, so the conflict
  arises only at the LTM layer.)
- **Replay budget larger than available significance mass**: drawing with repetition must
  terminate cleanly and not loop forever when few clusters exist.
- **Re-running consolidation**: already-consolidated episodes are not re-merged into duplicate
  abstractions on a subsequent pass (idempotent with respect to consolidated sources).
- **Over-merge pressure**: a large, internally-diverse cluster must be split or gated rather
  than collapsed into one mushy abstraction that regresses on held-out problems.
- **Significance ties**: deterministic, documented tie-breaking so runs are reproducible.

## Requirements *(mandatory)*

### Functional Requirements

**A — single bookmark at encoding**

- **FR-001**: The system MUST compute an episode's significance from exactly three distinct
  signals — surprise (prediction error), value (reward-magnitude), and use (re-access
  frequency) — combined by a **single shared definition** used at every call site.
- **FR-002**: The value signal MUST be derived at write time from outcomes the loop already
  knows: verified-correctness, whether the attempt was escalated to the teacher, and whether
  it yielded a crystallized skill. It MUST NOT be a constant.
- **FR-003**: Significance MUST be written once at episode-encoding time and recomputed by the
  **same** definition whenever a contributing signal changes (e.g., use count increments).
- **FR-004**: The three signals MUST remain individually inspectable (the system can report
  each factor's contribution), so significance is explainable, not opaque.
- **FR-005**: Increment A MUST require no schema migration (it reuses existing episode fields).

**B — passive forgetting via decay**

- **FR-006**: The effective significance of an episode MUST decay as a function of elapsed
  time since its last bookmarking/reactivation, unless it is re-accessed or replayed.
- **FR-007**: Decay MUST only down-weight. Episodes MUST never be deleted, hidden from query,
  or have their recorded content hard-edited by decay (preserves additive guarantee).
- **FR-008**: Anchored ground truth MUST be exempt from decay entirely. Anchors live in
  long-term memory (`is_anchor=true`, `decay_rate=0`); raw episodes (`short_term_memory`)
  carry no anchor flag and always decay, so the exemption is satisfied structurally at the
  LTM layer.
- **FR-009**: Re-access or a won replay MUST refresh an episode's reactivation time, so
  forgetting is reversible by renewed relevance.
- **FR-010**: The decay rate MUST be a single operator-tunable setting surfaced in
  configuration, with a documented default.
- **FR-011**: The decay effect (e.g., effective-significance distribution over age) MUST be
  observable on the dashboard.
- **FR-012**: Any schema change required by decay MUST be delivered as a reviewed migration
  and flagged for human approval before application (human-in-the-loop on self-modifying
  schema).

**C — competitive replay over clusters**

- **FR-013**: Consolidation MUST group similar raw (unconsolidated) episodes by semantic
  similarity before promoting them.
- **FR-014**: Consolidation MUST spend a fixed, operator-tunable **replay budget** by drawing
  groups in proportion to group significance, **with repetition**, so higher-significance
  groups are replayed more often.
- **FR-015**: Each group MUST be merged into **exactly one** long-term abstraction whose
  source list references every episode in the group.
- **FR-016**: An abstraction's strength MUST accrue with the number of times its group was
  replayed, rather than being a fixed constant.
- **FR-017**: The predictability/regression gate MUST run **per group** before a merge; a
  group that would regress on the held-out training slice MUST NOT be merged.
- **FR-018**: The system MUST guard against over-merging: a group whose members are not
  coherent enough (would regress) MUST be rejected or split rather than collapsed.
- **FR-019**: The drift-flag safeguard against abstractions warping away from anchored truth
  MUST remain in force, unchanged.
- **FR-020**: Every consolidation pass MUST remain additive (sources marked consolidated,
  never deleted) and MUST be idempotent with respect to already-consolidated sources.

**Cross-cutting (all increments)**

- **FR-021**: No increment may read or mutate the evaluation pool; all held-out checks draw
  only from the training/held-out slice.
- **FR-022**: The ungameable verification path (symbolic oracle) MUST remain untouched; this
  feature changes only how memories are scored, faded, and consolidated.
- **FR-023**: The scope of changed code MUST be confined to the memory and consolidation
  subsystem plus the one decay migration; the loop, budget cap, sandbox, and crystallization
  logic are not modified except to supply the value signal to the bookmark.

### Key Entities *(include if feature involves data)*

- **Episode (short-term memory)**: one recorded attempt. Carries surprise, value, use, the
  single significance score, an embedding for grouping, a reactivation timestamp (added by B),
  and a consolidation status. Never deleted. (Episodes carry **no** anchor flag — anchoring is
  an LTM-only property; raw episodes always decay.)
- **Abstraction (long-term memory)**: a generalization produced by consolidation. Carries a
  strength that grows with replay, and a source list of the episodes it was merged from.
- **Significance**: the single derived score (surprise × value × use), with per-factor
  contributions inspectable.
- **Replay event**: one draw against the replay budget; selects a group with probability
  proportional to its significance and contributes one strength increment to that group's
  abstraction.
- **Cluster/group**: a set of semantically similar raw episodes considered together for one
  merge.
- **Anchor**: a non-decaying ground-truth memory, exempt from forgetting.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: There is exactly **one** definition of significance in the system; identical
  inputs yield identical scores regardless of where significance is computed (no divergent
  formulas remain).
- **SC-002**: For attempts with equal surprise and use, value strictly orders them
  skill-yielding ≥ teacher-taught ≥ from-scratch — demonstrating the value signal is live.
- **SC-003**: Given equal initial significance, an idle episode's effective significance is
  measurably lower than a re-accessed one after a defined elapsed interval, while an anchor's
  is unchanged (0% decay).
- **SC-004**: 100% of episodes remain queryable after decay and after consolidation — zero
  deletions, confirming the additive guarantee.
- **SC-005**: After consolidation of a seeded K-member similar cluster, the number of
  abstractions produced for that cluster is exactly 1 (not K), and its strength is strictly
  greater than a single-replay baseline — demonstrating merge + replay-weighted strength.
- **SC-006**: Across a consolidation pass, higher-significance groups receive measurably more
  replay draws than lower-significance groups (monotonic relationship), within sampling noise.
- **SC-007**: The dashboard shows three new curves — (a) abstraction strength vs. replay
  count, (b) effective-significance vs. episode age (the decay curve), and (c) retrieval/reuse
  rate of consolidated abstractions over time — and a flat curve on any of them is accepted
  and recorded as a valid negative result.
- **SC-008**: The reuse curve (c) is the headline compounding signal: the feature is
  considered to have *demonstrated* compounding only if consolidated abstractions are retrieved
  and applied to later tasks at a rate measurably above zero; otherwise the negative result is
  reported honestly.
- **SC-009**: No change touches the evaluation pool or the verification oracle, confirmed by
  test.

## Assumptions

- The existing episode store already holds prediction error, an embedding per episode, an
  anchor flag, a consolidation status, and a long-term abstraction table with a strength field
  and a source-list — so A and C need no new tables and only B adds a column (reactivation
  time).
- "Value" is adequately captured by signals the loop already produces (verified-correct,
  escalated, crystallized-a-skill); richer external reward is out of scope for this feature.
- Semantic grouping can reuse the embeddings and vector index already present; no new
  embedding model is introduced.
- The held-out regression gate may remain the pilot's simplified form (drawn from the existing
  consolidation contract); deepening it into a full re-solve A/B is explicitly a later feature.
- Decay and replay-budget defaults will be chosen conservatively and tuned against live data;
  initial values are starting points, not claims of optimality.
- Increments land in order A → B → C, each mergeable on its own; B and C assume A is in place.

## Dependencies

- Builds directly on the 002 cognitive-core subsystem (episodes, salience, consolidation,
  long-term memory, anchors, the held-out slice, the dashboard).
- The decay migration (B) depends on human approval per the human-in-the-loop schema rule.
- Dashboard curves depend on the read-only reporting role already used by the learning
  dashboard.

# Feature Specification: Feasibility-Gated Curriculum (skill-adjacent task bias)

**Feature Branch**: `004-feasibility-gated-curriculum`

**Created**: 2026-06-29

**Status**: Draft

**Input**: User description: "Feasibility-gated curriculum (P2.9 / D6). Bias task selection toward skill-adjacent tasks to lift skill-coverage off ~0.8% so reuse can bite and the cold-escalation curve can separate downward. The curriculum queries current skill loadout/state before proposing a task so it never proposes the impossible. Hard guards: keep the forced 30%-external-benchmark mix, keep train/eval pool separation (is_eval read-only), and REJECT Voyager-style novelty-maximization (reward-hacking vector). Falsifiable target: Panel-🧩 coverage rises, Panel-🎯 skill-covered escalation separates below cold, retrieval-reuse rate climbs, escalation rate falls over ~8-13 cohorts. Math pilot only."

## Overview

The cognitive loop (002) and the consolidation/replay subsystem (003) are live and
instrumented. The 003 verdict is now readable, and it is honest: the system **recalls but
does not yet compound**. The diagnosis is one number — **skill coverage ≈ 0.8%**: a stored
skill matches the *next* task only about 1 in 125 times. Because a relevant skill is almost
never present, retrieval-reuse sits near zero and the "skill-covered" escalation curve cannot
separate from the cold curve. Volume alone will not fix this — random sampling over ~10k tasks
makes a skill-to-task collision rare by construction.

This feature attacks coverage directly. Instead of drawing the next training task uniformly at
random, the curriculum **queries the current skill loadout first** and **biases selection toward
tasks that are adjacent to skills the system already has** — tasks whose structure overlaps an
existing skill closely enough that reuse is *possible*, but not so closely that nothing is
learned. The same query makes the curriculum **feasibility-aware**: it never proposes a task the
current loadout makes impossible. Raising coverage is the lever that lets every downstream
compounding signal (reuse rate, skill-covered escalation, overall escalation) finally move.

**The deliverable is the measurement, not a guaranteed improvement.** Consistent with the
project thesis (D7) and exactly as 003 was framed, this feature is instrumented to *prove or
honestly falsify* that biasing the curriculum toward skill-adjacent tasks lifts coverage and,
through it, produces observable compounding. A flat or negative result over the cohort series is
a valid, recorded outcome — not a failure to hide.

This feature deliberately adopts only the **feasibility-gated** half of D6's curriculum guidance
and **rejects the Voyager novelty-maximization objective**. Maximizing raw exploration/diversity
is a reward-hacking vector (§10.1): an objective that rewards "new" invites the system to chase
novelty for its own sake rather than competence. Diversity in Fenrir comes from the *forced 30%
external-benchmark mix*, never from a novelty reward.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Feasibility-gated, skill-adjacent task selection (Priority: P1)

The operator runs a training cohort. For each non-external task, the curriculum first reads the
current skill library, then selects a task whose required structure is **adjacent** to an
existing skill — close enough that a stored skill *could* be retrieved and reused, far enough
that the attempt still exercises learning. The curriculum never emits a task that the current
loadout makes infeasible. Over a cohort series, the share of tasks for which a relevant skill
exists (**coverage**) climbs off its ~0.8% floor.

**Why this priority**: This is the entire lever. Coverage is the binding constraint identified by
the 003 verdict; every other compounding signal is downstream of it. Without this change the
reuse rate, the skill-covered escalation curve, and the falling-escalation thesis cannot be
tested at all. Smallest change that unblocks the headline measurement.

**Independent Test**: Seed a known set of skills. Run task selection for one cohort with the
gate ON and once with uniform-random selection (gate OFF) over the same pool. Assert that the
gate-ON cohort has a strictly higher fraction of skill-covered tasks (coverage) and that **no
selected task is infeasible** given the seeded loadout, while the gate-OFF cohort reproduces the
~baseline coverage.

**Acceptance Scenarios**:

1. **Given** a non-empty skill library, **When** the curriculum selects the next training task,
   **Then** it consults the current loadout and prefers a task adjacent to an existing skill,
   recording why the task was chosen (which skill it is adjacent to).
2. **Given** a task whose prerequisites the current loadout cannot satisfy, **When** the
   curriculum evaluates it, **Then** that task is not proposed (feasibility gate).
3. **Given** the gate is enabled across a cohort, **When** the cohort completes, **Then** the
   measured coverage for that cohort exceeds the uniform-random baseline for the same pool.
4. **Given** an empty skill library (cold start), **When** the curriculum runs, **Then** it
   still produces a full cohort of valid tasks by falling back to the external/benchmark pool —
   it never stalls for lack of an adjacent skill.

---

### User Story 2 - Anti-reward-hacking guards preserved (Priority: P1)

The same guards that make Fenrir's learning signal trustworthy survive the curriculum change.
Every cohort still draws **at least 30% from external benchmarks** regardless of what is
skill-adjacent; the held-out **evaluation pool is never selected into training** (`is_eval`
tasks remain read-only); and selection is driven by **feasibility/skill-adjacency, never by a
novelty-maximization objective**. The curriculum remains a **separate instance** from the
learner and the judge (Constitution VIII).

**Why this priority**: Co-equal P1 with US1. Biasing the curriculum toward what the system can
already do is exactly the move that, unguarded, collapses into overfitting and reward hacking —
the system could inflate "coverage" by feeding itself trivially-covered near-duplicates. The
guards are what keep the lift in US1 a *real* learning result instead of a memorized one. The
feature is not safe to ship without them, so they ship together.

**Independent Test**: Run a cohort and assert: (a) ≥30% of selected tasks come from the external
benchmark pool; (b) zero selected training tasks carry `is_eval=TRUE`; (c) the selection
objective contains no novelty/diversity reward term — adjacency and feasibility fully determine
preference. Attempt to select an eval-pool task into training and assert it is rejected.

**Acceptance Scenarios**:

1. **Given** any cohort the curriculum builds, **When** the cohort is assembled, **Then** at
   least 30% of its tasks are drawn from external benchmarks, independent of skill adjacency.
2. **Given** the evaluation/transfer pool, **When** the curriculum selects training tasks,
   **Then** no `is_eval` task is ever chosen, written to, or consolidated from.
3. **Given** two candidate tasks of equal feasibility, **When** the curriculum ranks them,
   **Then** the ranking never rewards a task simply for being more novel/diverse; only
   adjacency to existing skills and feasibility decide preference.
4. **Given** the running system, **When** the curriculum proposes tasks, **Then** it does so as
   a separate instance that does not see the learner's reasoning or self-evaluation.

---

### User Story 3 - The compounding verdict is readable on the dashboard (Priority: P2)

After a cohort series with the gate enabled, the operator can read a yes/no compounding verdict
from the existing "Are we actually learning?" board without ad-hoc SQL. The **🧩 coverage**
panel shows coverage rising off ~0.8%; the **🎯 skill-covered vs cold escalation** panel shows
the skill-covered curve separating *below* the cold curve; the retrieval-reuse rate climbs; and
overall escalation rate trends down across the series.

**Why this priority**: The mechanism (US1) and its guards (US2) are the product; this story makes
the result *legible* so the curriculum bet can be judged honestly. It is P2 because the panels
already exist from prior work — this story confirms they read correctly under the new selection
policy and adds whatever per-cohort series view is missing, rather than building the dashboard
from scratch.

**Independent Test**: Run a short multi-cohort series with the gate on; confirm each of the four
signals (coverage, skill-covered-vs-cold escalation gap, reuse rate, overall escalation rate) is
queryable per cohort and renders as a trend on the board, including the case where a signal stays
flat (a valid negative result must be just as readable as a positive one).

**Acceptance Scenarios**:

1. **Given** a completed cohort series, **When** the operator opens the board, **Then** coverage,
   reuse rate, skill-covered vs cold escalation, and overall escalation rate are each visible as
   a per-cohort trend.
2. **Given** a series where the signals do not move, **When** the board is read, **Then** the
   flat result is shown plainly as a recorded negative, not hidden or smoothed away.

---

### Edge Cases

- **Cold start / empty library**: no skills exist, so nothing is skill-adjacent — the curriculum
  must fall back to the external/benchmark pool and still emit a full, valid cohort (US1 #4).
- **Adjacency set exhausted**: every skill-adjacent task already ran this cohort — the remaining
  slots fall back to the external/benchmark draw rather than re-feeding near-duplicates.
- **Coverage-inflation hack**: an over-aggressive adjacency knob feeds the system trivially
  near-identical tasks, raising *training* coverage while teaching nothing — caught because the
  verdict is measured on the held-out eval pool (III) and cross-checked against reuse rate, not
  by training accuracy.
- **Over-narrowing**: adjacency bias concentrates the cohort into one tiny sub-domain — bounded
  by the forced 30% external mix (US2 #1) which guarantees breadth every cohort.
- **Feasibility misjudged**: the gate wrongly marks a solvable task infeasible and starves the
  cohort — selection must degrade to the external pool to fill the cohort rather than emit fewer
  tasks than requested.
- **Budget exhaustion mid-cohort (IX)**: the daily cap is reached — curriculum behavior on
  exhaustion follows the existing hard-cap rule (drop to local models / postpone), unchanged.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The curriculum MUST query the current skill loadout/state before selecting each
  non-external training task, and MUST bias selection toward tasks that are *adjacent* to an
  existing skill (reuse possible) rather than drawing uniformly at random.
- **FR-002**: The curriculum MUST NOT propose a task the current loadout makes infeasible
  (feasibility gate).
- **FR-003**: The system MUST record, per selected task, why it was chosen — at minimum which
  existing skill it was judged adjacent to (or that it was an external/fallback draw) — so the
  selection policy is auditable.
- **FR-004**: Every cohort MUST draw at least 30% of its tasks from external benchmarks,
  independent of skill adjacency, preserving the diversity guard.
- **FR-005**: The curriculum MUST NOT select, write to, or consolidate from any `is_eval` task;
  the evaluation/transfer pool remains strictly read-only (Constitution III).
- **FR-006**: The selection objective MUST be limited to feasibility and skill-adjacency; it MUST
  NOT include any novelty- or diversity-maximization reward term (rejects Voyager's objective;
  §10.1).
- **FR-007**: The curriculum MUST operate as a separate instance from the learner and the judge,
  without access to the learner's reasoning or self-evaluation (Constitution VIII).
- **FR-008**: On an empty or insufficient skill library, the curriculum MUST fall back to the
  external/benchmark pool and still emit a complete, valid cohort — it MUST never stall.
- **FR-009**: The system MUST expose, per cohort, the four verdict signals — skill coverage,
  retrieval-reuse rate, skill-covered vs cold escalation, and overall escalation rate — as
  queryable series feeding the existing "Are we actually learning?" dashboard.
- **FR-010**: The skill-adjacency strength MUST be an operator-tunable setting so the bias can be
  dialed between "pure feasibility filter" and "strong adjacency pull" without code changes.
- **FR-011**: A flat or negative result over the cohort series MUST be recorded and readable as a
  valid outcome; the feature MUST NOT alter, hide, or smooth a non-improving series.
- **FR-012**: The change MUST be additive and respect the daily budget hard cap (Constitution
  IX); on budget exhaustion the existing curriculum-degradation rule applies unchanged.

### Key Entities

- **Curriculum selection**: the policy that, given the current skill loadout and the available
  task pools, chooses the next training task; produces a per-task selection record (chosen task,
  source pool, adjacent-skill reference or fallback reason).
- **Skill loadout / coverage**: the set of currently crystallized skills and the derived measure
  of what fraction of candidate tasks a skill could serve (coverage); the headline metric this
  feature moves.
- **Task pools**: the disjoint training and held-out evaluation/transfer pools, plus the external
  benchmark source that supplies the forced 30% diversity mix; `is_eval` marks read-only members.
- **Cohort verdict signals**: the per-cohort series — coverage, reuse rate, skill-covered vs cold
  escalation gap, overall escalation rate — that constitute the falsifiable compounding readout.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Over a series of ~8–13 cohorts with the gate enabled, **skill coverage rises
  materially off the ~0.8% baseline and is sustained** above it (first target: reaching low
  single-digit-percent coverage, an order of magnitude over baseline), demonstrating the lever
  works.
- **SC-002**: The **skill-covered escalation rate separates below the cold (skill-absent)
  escalation rate** by a measurable margin on the 🎯 panel — covered tasks escalate less often
  than cold ones.
- **SC-003**: The **retrieval-reuse rate climbs above its near-zero baseline** and tracks the
  coverage rise (reuse moves *with* coverage, the cross-check that the lift is real and not
  memorized).
- **SC-004**: The **overall escalation rate trends downward** across the cohort series — the
  D7/D8 compounding signal, distinct from flat-escalation = recall-only.
- **SC-005**: **Every** cohort contains **≥30% external-benchmark tasks** and **0 eval-pool
  tasks** — the guards hold on 100% of cohorts, with no exceptions.
- **SC-006**: For any candidate task the curriculum proposes, **0 are infeasible** under the
  loadout at proposal time (the gate never emits an impossible task).
- **SC-007**: A flat series (no movement in SC-001…SC-004) is **fully readable on the dashboard
  as a recorded negative result**, with no signal hidden or altered — the honest-falsification
  requirement.

## Assumptions

- **"Skill-adjacent" is defined by retrievability**: a task is adjacent to a skill when that
  skill would plausibly be *retrieved* for it (structural/semantic proximity above a tunable
  threshold), not by hand-authored task taxonomies. This reuses the existing retrieval substrate
  rather than introducing a new classifier.
- **The 30% external mix is the diversity mechanism**, inherited from prior work; this feature
  preserves it verbatim and does not introduce a competing novelty objective (D6 rejection).
- **Coverage targets are first-milestone, not final**: SC-001's "low single-digit percent" is the
  threshold that proves the lever moves; it is not a claim about the eventual ceiling. The real
  test is *direction and the reuse cross-check*, per the thesis.
- **The dashboard panels already exist** (🧩 coverage, 🎯 skill-covered vs cold escalation, the
  reuse-rate panel) from prior GitOps work; US3 verifies they read correctly under the new policy
  and adds only any missing per-cohort series view, not a new board.
- **Math pilot only** (Constitution I): scope is the math task pools and their verifier; no new
  domain is introduced.
- **Existing nightly cohort harness is the runner**: the ~8–13 cohort series accumulates through
  the existing `fenrir-cohort` nightly mechanism plus manual batches; this feature changes *which*
  tasks that harness selects, not how cohorts are launched.
- **Feasibility/adjacency judgments may be imperfect**; the cohort-fill fallback to the external
  pool (FR-008) guarantees a complete cohort even when those judgments misfire.

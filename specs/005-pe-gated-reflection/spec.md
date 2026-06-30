# Feature Specification: PE-gated meta-reflection

**Feature Branch**: `005-pe-gated-reflection`

**Created**: 2026-06-30

**Status**: Draft

**Input**: User description: "P1.2 — PE-gated meta-reflection. Add a meta-reflection step to the cognitive loop, gated and weighted by prediction-error magnitude, replacing uniform per-task reflection effort with effort that concentrates where the system was surprised (D3 / §3). Tiers: low PE → skip; mid → cheap; high → full LLM reflection feeding skill edit-or-create. Respect constitution IX/VIII/III/VI/VII/IV. Measurable in SQL/Grafana."

## Why this feature (context)

Today the loop spends the **same effort on every task** after verification: it writes an additive
episode for all, and crystallizes a skill on any escalated-or-surprising scratch win. There is **no
distinct reflection step** that extracts *why* a result happened and turns it into a better skill.
The neuroscience basis (D3: prediction error is the master signal; D6/SOAR: chunk only on impasse)
says learning effort should **concentrate where the system was surprised** — uniform reflection
wastes the core efficiency trick. This feature introduces meta-reflection as an explicit step whose
cost is **gated by prediction-error (PE) magnitude**, so the cheap majority stay cheap and the rare
high-surprise events get deep treatment immediately (front-running batch consolidation).

This is **P1 lever 1.2** (BACKLOG.md), the next core-mechanism after the curriculum (004).

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Reflection effort tracks surprise, not task volume (Priority: P1)

As the operator, I want the system to **skip or cheapen reflection on low-surprise tasks and reserve
deep reflection for high-PE events**, so that learning cost concentrates where the model was actually
wrong/surprised and does not scale with the volume of easy, already-known problems.

**Why this priority**: This is the lever itself — the PE gate. Without it, reflection is either absent
(today) or would run uniformly (the flaw D3 identifies). It is the smallest slice that delivers the
efficiency property and is independently measurable.

**Independent Test**: Run a cohort containing a mix of low-PE (confident, correct, local) and high-PE
(surprising/escalated) tasks; confirm reflection is invoked at the three tiers in proportion to PE —
near-zero on the low-PE tasks, full on the high-PE tasks — and that per-task average cost does not
rise as low-surprise volume grows.

**Acceptance Scenarios**:

1. **Given** a task solved locally with high confidence and a correct verdict (PE below the LOW
   threshold), **When** the iteration completes, **Then** reflection is **skipped** (tier = `none`),
   no reflection LLM call is made, and only the additive episode is written (today's behavior).
2. **Given** a task with PE in the MID band, **When** the iteration completes, **Then** a **cheap**
   reflection runs with **no extra LLM call** (a structured signal only) and is recorded.
3. **Given** a task with PE at/above the HIGH threshold (a surprise/impasse), **When** the iteration
   completes, **Then** a **full** reflection runs (one LLM pass) and its tier is recorded.
4. **Given** the same cohort run twice with the LOW threshold set to 0 vs 1, **When** compared,
   **Then** reflection-invocation rate changes accordingly — proving the gate, not a fixed schedule,
   drives invocation.

---

### User Story 2 — High-PE reflection improves the skill library (Priority: P1)

As the operator, I want a **full reflection to extract the reusable lesson and feed skill
edit-or-create** — a small surprise edits the matched skill as a new version, a large surprise spawns
a new skill — so that the highest-surprise events strengthen the library immediately rather than
waiting for the nightly consolidation pass.

**Why this priority**: Reflection that only labels tasks has no compounding value; the payoff is that
surprise turns into a better/owned skill (D6 impasse chunking, P2.1 reconsolidation seed). Ships with
US1 as the meaningful unit.

**Independent Test**: Feed a high-PE task whose problem is adjacent to an existing skill; confirm the
existing skill gains a **new version** (not an in-place mutation) when PE is moderate, and a **new
skill** is created when PE is large; confirm neither happens for low/mid-PE tasks.

**Acceptance Scenarios**:

1. **Given** a high-PE verified win adjacent to an existing skill and a *moderate* reflection-PE,
   **When** full reflection runs, **Then** the existing skill is updated as a **new version** (prior
   version retained, VII) and the change is attributable to this task.
2. **Given** a high-PE verified win with *large* reflection-PE (or no adjacent skill), **When** full
   reflection runs, **Then** a **new skill** is created (self-tested, per existing crystallization
   rules) and linked to the originating task.
3. **Given** a high-PE event but the daily budget is exhausted, **When** full reflection is due,
   **Then** it is **suppressed gracefully** (downgraded to cheap reflection, recorded as suppressed),
   exactly as escalation degrades — no crash, no budget breach (IX).
4. **Given** an `is_eval = TRUE` task, **When** the iteration completes at any PE, **Then** reflection
   **never writes or mutates a skill** and never consolidates (III, read-only held-out).

---

### User Story 3 — The gate is observable and honest (Priority: P2)

As the operator, I want **every task to record which reflection tier it received and the outcome**, so
I can confirm in SQL/Grafana that reflection concentrates on surprise and report a flat/negative
result honestly.

**Why this priority**: The project's deliverable is the measurement (D7/D8). The audit is needed to
trust the gate, but the gate (US1+US2) can ship and run without the dashboard cut.

**Independent Test**: After a cohort, query the per-task reflection tier and join to PE; confirm the
distribution is legible (tier vs PE) and that a cohort where nothing surprised renders plainly as "all
`none`/cheap".

**Acceptance Scenarios**:

1. **Given** a completed cohort, **When** the operator queries reflection tiers, **Then** each task
   has exactly one recorded tier (`none` | `cheap` | `full`) and full-reflection rows record whether a
   skill was edited, created, or suppressed.
2. **Given** a cohort with no high-PE events, **When** rendered, **Then** the reflection panel shows a
   flat all-`none`/`cheap` series — a valid recorded outcome, not an error.

---

### Edge Cases

- **PE exactly on a threshold** — boundaries are defined inclusively for the higher tier (PE ≥ HIGH →
  full; LOW ≤ PE < HIGH → cheap; PE < LOW → none), so a task lands in exactly one tier.
- **Unverified verdict (sympy could not decide)** — treated as surprising for gating PE but MUST NOT
  produce a crystallized/edited skill (no skill from an unverified outcome, II/IV).
- **Failed verdict with high PE** — full reflection may run to extract a lesson, but only writes a
  skill from a *verified success* (IV); on failure it records the lesson without certifying a skill.
- **Budget exhausted mid-cohort** — all subsequent full reflections downgrade to cheap and are marked
  suppressed; the cohort still completes (IX, parity with escalation suppression).
- **Reflection LLM refuses/errors** — the iteration MUST still complete and persist (reflection is
  best-effort enrichment, never a gate on task completion).
- **A skill edit that would regress** — reflection-driven edits inherit the same admission discipline
  as crystallization (a new version must still pass its self-test before replacing the active one).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The loop MUST compute a reflection **tier** for every task: `full` whenever the task
  **escalated** to the teacher (so the full tier exactly supersets today's crystallize trigger, no
  regression — SC-008), otherwise from prediction-error magnitude against two configurable thresholds:
  `none` (PE < LOW), `cheap` (LOW ≤ PE < HIGH), `full` (PE ≥ HIGH).
- **FR-002**: `none`-tier tasks MUST incur **no reflection LLM call** and behave as today (additive
  episode only) — reflection cost MUST NOT scale with low-surprise task volume.
- **FR-003**: `cheap`-tier tasks MUST record a lightweight structured reflection signal **without an
  extra LLM call**.
- **FR-004**: `full`-tier tasks MUST run **exactly one** reflection LLM pass that extracts a reusable
  lesson from the task.
- **FR-005**: A `full` reflection on a **verified success** MUST feed skill **edit-or-create**: a
  **matched** skill (`retrieval_skill_id` set) with PE below `REFLECT_EDIT_PE_MAX` edits it as a
  **new version** (prior retained, VII); a cold task (no matched skill) or PE at/above
  `REFLECT_EDIT_PE_MAX` **creates a new skill** under the existing self-test admission rules.
- **FR-006**: Reflection MUST **never certify a skill from an unverified or failed outcome** (II/IV);
  on such outcomes it may record a lesson only.
- **FR-007**: Reflection MUST respect the **daily budget hard cap** (IX): when exhausted, a due `full`
  reflection downgrades to `cheap` and is recorded as **suppressed**; the budget is never exceeded.
- **FR-008**: Reflection MUST honor **learner/judge/curriculum separation** (VIII) — it MUST NOT grade
  its own output as ground truth nor influence task selection.
- **FR-009**: For `is_eval = TRUE` tasks, reflection MUST be **read-only** (III): no skill write/edit,
  no consolidation, regardless of PE.
- **FR-010**: Every task MUST persist exactly one **reflection tier** plus, for `full`, the outcome
  (`edited` | `created` | `none` | `suppressed`) and a link to any affected skill — queryable in SQL.
- **FR-011**: The PE thresholds MUST be **operator-configurable** (settings) without code change, and
  their defaults documented.
- **FR-012**: Reflection MUST be **best-effort**: a reflection error/refusal MUST NOT fail or roll back
  the task iteration.
- **FR-013**: Episodes remain **additive** (VI/D1): reflection never deletes or overwrites a source
  episode.
- **FR-014**: A **flat/negative** result (no high-PE events → no full reflections) MUST be a recorded,
  legible outcome, not an error state (D7/D8 honesty).

### Key Entities *(include if feature involves data)*

- **Reflection tier**: the per-task classification (`none` | `cheap` | `full`) derived from PE; one
  per task, recorded for audit.
- **Reflection outcome** (full tier only): what the reflection did — `edited` (existing skill, new
  version), `created` (new skill), `none` (lesson recorded, no skill change), `suppressed` (budget).
- **Reflection record / lesson**: the structured lesson extracted from a task, linked to the task and
  to any skill it edited/created.
- **Skill version**: an existing entity; reflection adds a version on edit rather than mutating in
  place (VII).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Across a cohort, reflection-invocation rate **correlates with the PE distribution** —
  full-reflection share approximates the high-PE share, not a fixed fraction of tasks.
- **SC-002**: As the proportion of low-surprise tasks rises, **average reflection cost per task does
  not rise** (low-PE tasks add ~zero reflection cost).
- **SC-003**: **100%** of high-PE verified wins receive a `full` reflection (or a recorded
  `suppressed` when the budget is exhausted) — none are silently skipped.
- **SC-004**: At least one **skill edit-or-create is attributable to reflection** over a cohort that
  contains high-PE verified wins (the compounding payoff is observable).
- **SC-005**: **Zero** skill writes occur for `is_eval = TRUE` tasks (III), verifiable by query.
- **SC-006**: The **daily budget cap is never exceeded** by reflection, across any cohort size (IX).
- **SC-007**: Reflection tier is recorded for **100%** of tasks and is renderable per cohort; a cohort
  with no surprise renders as an all-`none`/`cheap` series without error (D7/D8).
- **SC-008**: Turning reflection **off** (thresholds set so nothing reaches `full`) leaves task
  throughput and verdicts unchanged vs today — the feature is additive and gated, not a rewrite.

## Assumptions

- **Prediction error is already computed and stored per task** (002/FR-005); this feature consumes it,
  it does not redefine it. "Reflection-PE" for the edit-vs-create decision reuses the same PE signal.
- **Crystallization and its self-test admission already exist** (skills as executable code + `self_test`);
  reflection's create path reuses that admission, and its edit path reuses skill versioning (VII).
- **The single budget proxy is the only model-call egress** (X) and already exposes graceful
  suppression on exhaustion (parity with escalation); reflection routes its one LLM call through it.
- **"Cheap" reflection is intentionally minimal** (a structured signal, no LLM) at this stage; richer
  awake micro-reflection variants (P2.6) and full reconsolidation semantics (P2.1) are follow-ons that
  build on this gate, not part of this slice.
- **Math pilot only** (I); no domain expansion.
- **Default thresholds** will be chosen from the observed PE distribution in current cohorts and may be
  tuned; the exact numbers are an implementation/plan concern, not a spec guarantee.

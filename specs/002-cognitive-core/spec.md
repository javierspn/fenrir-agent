# Feature Specification: Cognitive Core Loop (math pilot)

**Feature Branch**: `002-cognitive-core`

**Created**: 2026-06-26

**Status**: Draft

**Input**: User description: "002-cognitive-core — the full core cognitive loop on the mathematics pilot, instrumented to prove (or falsify) the project hypothesis."

## Overview

The 01-infra feature stood up the substrate (Postgres+pgvector, Redis, Grafana, Ollama, the 14-table schema, disjoint benchmark pools, invariant anchors). This feature builds the **cognitive loop that runs on top of it** and turns the substrate into a learning system.

The loop processes math tasks one at a time: predict → retrieve prior skills → solve with the small owned model → escalate to a frontier teacher only when stuck → verify with an ungameable oracle (sympy) → measure surprise (prediction error) → store the attempt additively → consolidate high-salience memories during a regulated "sleep" step → crystallize verified, executable, self-tested skills. Every pass emits metrics.

**The deliverable is the measurement, not the accuracy.** Success is a clean, honest, instrumented answer to: *how far does external memory + crystallized skills substitute for model scale on mathematics, with falling frontier dependence?* A flat escalation-rate curve (built recall, not compounding) is a **valid, valuable negative result**, not a failure of the feature.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Solve-verify-store one task end-to-end (Priority: P1)

The operator starts the loop against the training pool. For a single task the system records a prediction, retrieves any relevant prior skills/episodes, attempts a solution with the small local model, has the result checked by the sympy verifier, computes prediction error, and writes the attempt as an additive episode — without ever touching the evaluation pool.

**Why this priority**: This is the irreducible heartbeat. Without a verified solve-and-store on a single task, nothing downstream (salience, consolidation, crystallization, curves) has any input. It is the MVP: one trustworthy, verified, recorded attempt.

**Independent Test**: Feed one known training task, run one iteration, assert: a prediction row was written before the attempt; the answer was adjudicated solely by sympy; an episode row exists with a prediction-error value; no evaluation-pool row was read or written.

**Acceptance Scenarios**:

1. **Given** an unsolved task in the training pool, **When** the loop runs one iteration, **Then** a prediction (outcome + confidence) is recorded before solving, and an episode capturing the attempt + verifier verdict + prediction error is persisted.
2. **Given** the small model returns a correct answer, **When** sympy confirms symbolic equivalence, **Then** the task is marked succeeded and the episode records success=true.
3. **Given** the small model returns a textually-plausible but mathematically-wrong answer, **When** sympy rejects it, **Then** the task is marked failed regardless of how confident the model was.
4. **Given** the loop selects tasks, **When** any iteration runs, **Then** it draws only from the training pool and never reads or mutates an evaluation-pool task.

---

### User Story 2 - Crystallize a verified, executable, self-tested skill (Priority: P1)

When a task is solved on a high-surprise (high prediction-error) attempt, the system distills the solution into a reusable skill stored as **executable code plus a self-test**, and the skill is admitted to the library **only after an independent verification pass** confirms the code runs and solves the originating task. On the next similar task, retrieval surfaces the skill and the system applies it instead of reasoning from scratch.

**Why this priority**: Crystallization is the mechanism the entire thesis rests on (compounding, not recall). Without verified skill reuse there is no "retrieval-vs-from-scratch" curve and no OOM claim. Equal P1 with US1 because the hypothesis is unfalsifiable without it.

**Independent Test**: Run a solved high-PE task through crystallization; assert a skill row exists as code + self_test; assert it was admitted only after an independent pass; feed a second similar task and assert the skill is retrieved and applied (retrieval path taken, not cold solve).

**Acceptance Scenarios**:

1. **Given** a task solved on a high-prediction-error attempt, **When** crystallization runs, **Then** a candidate skill is produced as executable code with a self_test, and is admitted to the library only if an independent pass runs the code and reproduces the verified solution.
2. **Given** a candidate skill whose self_test fails on the independent pass, **When** crystallization completes, **Then** the skill is rejected and NOT added to the library.
3. **Given** a task the system already predicted correctly (low prediction error), **When** the iteration completes, **Then** crystallization does NOT fire.
4. **Given** an existing skill in the library, **When** a new similar task arrives, **Then** retrieval surfaces it and the attempt is recorded as a retrieval-based solve rather than a from-scratch solve.

---

### User Story 3 - Escalate to the frontier teacher only when stuck (Priority: P2)

When the small model's confidence/feasibility for a task is low (cold, novel, high-surprise), the loop escalates that task to the frontier teacher through the internal budget-governed LLM proxy. Escalation is the exception, is rate-tracked, and is expected to decline over time as the skill library grows.

**Why this priority**: Escalation makes hard tasks solvable so they can crystallize, and its **rate over time is one of the three falsifiable curves**. P2 because US1+US2 can run on the small model alone for an initial cohort, but the hypothesis test needs the escalation signal.

**Independent Test**: Force a low-confidence task; assert it routes to the teacher via the proxy; assert the escalation is counted; assert a task the system is confident on does NOT escalate.

**Acceptance Scenarios**:

1. **Given** a task where the small model's confidence/feasibility is below threshold, **When** the loop solves it, **Then** it escalates to the frontier teacher through the internal LLM proxy and records that the task was escalated.
2. **Given** a task the small model is confident on, **When** the loop solves it, **Then** it does NOT escalate.
3. **Given** the daily budget is exhausted, **When** a task would otherwise escalate, **Then** escalation is suppressed and the task is handled locally or deferred — the budget cap is never silently exceeded.
4. **Given** the proposer/solver produced an answer, **When** it is verified, **Then** the verifying component is independent of the proposing component (separation of powers).

---

### User Story 4 - Regulated consolidation ("sleep") in salience order (Priority: P2)

On a cadence (or when triggered), the system consolidates memory: it processes episodes in salience order (salience = prediction-error × importance × retrieval-frequency), and merges an abstraction into long-term memory **only if the merge improves performance on held-out cases** (predictability gate). Source episodes are marked consolidated and left to decay — never hard-deleted.

**Why this priority**: Consolidation is how short-term experience becomes durable, generalizing memory, and the predictability gate is the constitutional guard against overfitting. P2 because the loop produces value per-task before sleep runs, but durable compounding needs it.

**Independent Test**: Seed episodes with varied salience; run consolidation; assert processing order is salience-descending; assert a merge that does not improve held-out cases is rejected; assert no source episode was deleted (additive only).

**Acceptance Scenarios**:

1. **Given** a backlog of unconsolidated episodes, **When** consolidation runs, **Then** episodes are processed in descending salience order.
2. **Given** a candidate abstraction, **When** it does NOT improve held-out-case performance, **Then** it is not merged; idiosyncratic detail is left unmerged.
3. **Given** consolidation merges an abstraction, **When** it writes to long-term memory, **Then** it writes a NEW row and marks the source episodes consolidated without deleting them.
4. **Given** consolidation has run, **When** the source episodes are inspected, **Then** every original record is still re-derivable (no hard delete, no cascade).

---

### User Story 5 - Track everything on the learning dashboard (Priority: P2)

The operator opens the Grafana "Learning" dashboard and sees the system's progress over time: the three falsifiable curves (cost per task, escalation rate, retrieval-vs-from-scratch share) plus supporting panels (episode/skill counts, pool occupancy, consolidation events, prediction-error distribution). All panels read through the existing read-only datasource.

**Why this priority**: The measurement is the deliverable; the dashboard is how the operator reads it. P2 because the curves can be computed/exported before they are pretty, but the project's whole point is observable, honest progress.

**Independent Test**: With a cohort of completed iterations in the database, load the dashboard and assert each of the three curves and the supporting panels render real values from the read-only datasource (placeholder panel removed).

**Acceptance Scenarios**:

1. **Given** a cohort of completed iterations, **When** the operator opens the Learning dashboard, **Then** the three curves over time are displayed with real data.
2. **Given** the dashboard panels query the database, **When** they load, **Then** they use the read-only role only (no write capability, no admin credentials).
3. **Given** the loop has run, **When** the operator inspects the dashboard, **Then** episode count, skill count, pool occupancy, consolidation events, and prediction-error distribution are visible.

---

### Edge Cases

- **Verifier cannot decide** (sympy times out, can't parse, or the task lacks a checkable ground truth): the attempt is recorded as *unverified* and is **never** counted as a success or used to crystallize a skill (a domain/task without an ungameable verdict is not eligible for autonomous learning).
- **Model emits non-extractable / malformed output** (no parseable final answer): treated as a failed attempt, episode recorded, no crystallization.
- **Two tasks crystallize conflicting skills**: the new skill is versioned/linked as contradicting rather than silently overwriting the prior one; large prediction error → new skill, small → new version.
- **Budget exhausted mid-run**: escalation stops, local-only solving continues or tasks defer; no silent cap increase; the run remains honest about what it could not attempt.
- **Retrieval returns a skill that then fails verification on the current task**: the failure is recorded as an episode (negative evidence) and does not corrupt the retrieved skill's record.
- **Benchmark contamination**: all current benchmark rows are contamination_unsafe (likely in base-model pretraining); the system MUST surface this caveat on any reported result and MUST NOT present contaminated-pool accuracy as a clean generalization claim.
- **Sandbox attempts network access** beyond the internal LLM proxy: blocked; the attempt fails closed.
- **Empty library / cold start**: the first cohort has nothing to retrieve; the loop runs purely cold and records that baseline (it is the left end of the retrieval-share curve).

## Requirements *(mandatory)*

### Functional Requirements

**Task intake & pool separation**

- **FR-001**: System MUST select tasks for solving exclusively from the **training** pool and MUST NEVER read, solve, train on, or consolidate from the **evaluation** pool (Constitution III).
- **FR-002**: System MUST track which tasks have been attempted so iterations draw unsolved/under-practiced training tasks rather than repeating trivially.
- **FR-003**: System MUST keep at least **30%** of attempted tasks sourced from external benchmark tasks (no self-generated curriculum in this feature).

**Predict-before-solve & prediction error**

- **FR-004**: System MUST record a predicted outcome and a confidence value **before** attempting each task.
- **FR-005**: System MUST compute a prediction-error value after verification from the verification delta (predicted-vs-actual correctness) and the calibration gap (predicted confidence vs realized correctness).
- **FR-006**: System MUST gate downstream learning effort by prediction error — low surprise → minimal/no reflection; high surprise → full reflection — and MUST NOT crystallize a skill on a task it already predicted correctly (Constitution IV).

**Retrieval & solving**

- **FR-007**: System MUST, before solving, retrieve candidate prior skills/episodes relevant to the task using both lexical (full-text) and vector similarity over the existing substrate.
- **FR-008**: System MUST prefer applying a retrieved verified skill over cold reasoning when an applicable skill exists, and MUST record per attempt whether it was solved via **retrieval/skill-application** or **from scratch**.
- **FR-009**: System MUST attempt solving with the small owned (local) model by default.

**Escalation router**

- **FR-010**: System MUST escalate a task to the frontier teacher model only when the small model's confidence/feasibility is below a defined threshold (cold/novel/high-PE), and MUST record the escalation.
- **FR-011**: All model calls (local and frontier) MUST go through the internal budget-governed LLM proxy that enforces the per-task budget, concurrency limit, and timeout; task sandboxes MUST have no network access except that proxy (Constitution X).
- **FR-012**: System MUST enforce the daily LLM budget as a hard cap; on exhaustion escalation is suppressed and heavy work deferred, never silently exceeded (Constitution IX).

**Verification (binding constraint)**

- **FR-013**: System MUST adjudicate correctness for every autonomous attempt using **symbolic equivalence (sympy)** as the sole ground-truth oracle — never textual match or LLM-judge alone (Constitution II).
- **FR-014**: The component that verifies MUST be independent of the component that proposes/solves (Constitution VIII separation of powers).
- **FR-015**: A task MUST be marked "succeeded" only when the sympy verifier confirms it; unverifiable results MUST be recorded as unverified and excluded from success metrics and crystallization.

**Episodic memory (additive)**

- **FR-016**: System MUST persist every attempt as an **additive episode** capturing task, prediction, solve path (retrieval vs scratch), escalation flag, verifier verdict, and prediction error.
- **FR-017**: System MUST NEVER hard-delete source episodes; consolidation marks them consolidated and lets them decay (Constitution VI; no DELETE, no ON DELETE CASCADE).
- **FR-018**: System MUST compute a **salience** score per episode = prediction-error × importance × retrieval-frequency, and update retrieval-frequency when an episode/skill is retrieved.

**Consolidation ("sleep")**

- **FR-019**: System MUST run consolidation on a cadence floor and process episodes in **descending salience order** (Constitution V).
- **FR-020**: System MUST apply a **predictability gate** — an abstraction is merged into long-term memory only if it improves performance on held-out cases; idiosyncratic detail is not merged.
- **FR-021**: Consolidation MUST write abstractions as NEW long-term rows (additive), never overwrite or delete sources.

**Skill crystallization**

- **FR-022**: System MUST store crystallized skills as **executable code plus a self_test**, never as free text (Constitution — verifiability).
- **FR-023**: A skill MUST be admitted to the library only after an **independent verification pass** runs its code and reproduces the verified solution to the originating task; candidates failing self_test are rejected.
- **FR-024**: System MUST version a skill before any modification; small prediction error → new version, large prediction error → new skill with a contradicts-link; never silent overwrite (Constitution VII).
- **FR-025**: Schema migrations and any mass/irreversible skill rewrites MUST require human confirmation, not run autonomously (Constitution XII).

**Anchors / drift**

- **FR-026**: System MUST treat invariant anchors as non-decaying and use them as a drift smoke-test (flag abstractions that have warped away from anchored ground truth).

**Instrumentation & dashboard**

- **FR-027**: System MUST emit, over time, the three falsifiable curves: (a) cost per solved task, (b) escalation rate, (c) retrieval-vs-from-scratch share.
- **FR-028**: System MUST persist per-iteration metrics sufficient to reconstruct those curves and to detect a **flat escalation rate** (the negative-result / "recall-not-compounding" signal).
- **FR-029**: System MUST replace the placeholder Grafana "Learning" dashboard with panels for the three curves plus episode/skill counts, pool occupancy, consolidation events, and prediction-error distribution, all served through the existing **read-only** datasource role.
- **FR-030**: System MUST surface the contamination caveat alongside any reported accuracy/generalization result (benchmark rows are contamination_unsafe).

### Key Entities *(include if feature involves data)*

- **Task attempt / iteration**: one pass of the loop over a single training task — links the task, the prediction, the solve path, escalation flag, verifier verdict, prediction error, and cost. Basis for all three curves.
- **Prediction**: predicted outcome + confidence recorded before solving; paired post-hoc with the realized result to yield prediction error and the calibration gap.
- **Episode** (short-term memory, additive): the durable record of one attempt; carries salience and a consolidated marker; never hard-deleted.
- **Abstraction** (long-term memory): a generalization written by consolidation as a new row after passing the predictability gate.
- **Skill**: executable code + self_test, versioned, admitted only after an independent verification pass; the asset that makes reuse cheaper than cold reasoning.
- **Salience**: derived score (PE × importance × retrieval-frequency) that orders consolidation.
- **Escalation event**: a record that a task was routed to the frontier teacher, with cost — the raw material of the escalation-rate curve.
- **Anchor**: an invariant, non-decaying ground-truth fact used as the drift smoke-test.
- **Metric series**: the persisted per-iteration values that reconstruct the three curves and feed the dashboard.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A single training task can be taken from intake through prediction → solve → sympy verification → episode persistence in one loop iteration, with the evaluation pool provably untouched.
- **SC-002**: Across a run, **100%** of autonomous success verdicts are backed by a sympy verification (zero successes from textual/LLM-judge-only adjudication).
- **SC-003**: **100%** of library-admitted skills passed an independent verification pass (code ran and reproduced the verified solution); zero free-text-only skills in the library.
- **SC-004**: Over a cohort, the three curves are computable and displayed: cost per solved task, escalation rate, and retrieval-vs-from-scratch share — each as a time series.
- **SC-005**: The system distinguishes the two hypothesis outcomes from the data alone — a **falling** escalation rate (compounding) vs a **flat** escalation rate (recall only) — i.e. the negative result is detectable, not hidden.
- **SC-006**: Crystallization fires **only** on high-prediction-error tasks; zero crystallizations occur on tasks the system already predicted correctly.
- **SC-007**: Consolidation processes episodes in salience order and rejects every abstraction that fails the held-out predictability gate; **zero** source episodes are hard-deleted across any consolidation run.
- **SC-008**: The daily budget cap is never exceeded; when exhausted, escalation provably stops and the run continues locally or defers.
- **SC-009**: On a second exposure to a task similar to one already crystallized, the system solves via retrieval/skill-application (verified by the solve-path record) rather than cold reasoning.
- **SC-010**: The Grafana "Learning" dashboard shows all required panels with real data through the read-only role, and every reported accuracy result carries the contamination caveat.

## Assumptions

- The 01-infra substrate (Postgres+pgvector, Redis, Grafana with read-only datasource, Ollama + local models, the 14-table schema, disjoint training/evaluation pools, invariant anchors, content_fts + GIN) is live on <host> and is reused as-is; this feature adds the loop and any **additive** schema columns/tables it needs (migrations are ordered + human-confirmed).
- Domain is **mathematics only** (sympy is the oracle); single-node (<host>); a single owned small model plus one frontier teacher model.
- The frontier teacher is reachable via the existing Anthropic credential path through the internal proxy; the daily budget value is operator-configured.
- "Held-out cases" for the consolidation predictability gate are drawn from training-pool material set aside for that purpose — **not** the protected evaluation pool.
- Benchmark rows are contamination_unsafe; the clean contamination-safe frozen eval set is a later feature (P4.5) — results here are reported with that caveat, and the absence of a clean transfer claim is acceptable for this feature.
- Success is defined as a **clean instrumented measurement**, not a target accuracy; a negative result (flat escalation) satisfies the feature's purpose.

### Out of Scope (deferred — do NOT build in this feature)

- Neo4j / knowledge-graph layer (P3.1) — only once drift is observable.
- Autonomous curiosity / ZPD curriculum generation (P3.2) — tasks come from benchmark pools here.
- Parallel-convergent multi-lane selector + cross-encoder reranker (P2.5) — this feature ships simpler lexical+vector retrieval.
- Multi-node model routing (P4.4); domain expansion beyond mathematics (P4.2).
- The full frozen contamination-safe evaluation set and transfer pool (P4.5) — only the caveat is surfaced here.

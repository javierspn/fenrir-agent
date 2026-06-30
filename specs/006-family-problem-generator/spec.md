# Feature Specification: Contamination-safe family-structured problem generator + by-family reuse verdict

**Feature Branch**: `006-family-problem-generator`

**Created**: 2026-06-30

**Status**: Draft

**Input**: User description: "Bring the working overnight generator into the repo: a small open model generates problem prose + sympy solution_code, sympy executes to derive ground truth (model never trusted for the answer, II/VIII), across 10 solution-method families. Load into a contamination-safe family-structured pool. Measure reuse/escalation BY FAMILY — the clean within-family compounding verdict vs today's contaminated GSM8K/MATH aggregate. (D13, P4.7)"

## Why this feature (context)

The reuse signal that decides the whole bet (does the system *compound* or merely *recall*?) is
muddied by the **data**, not only the mechanism. The current pools (GSM8K/MATH) are (a)
**contaminated** — likely in base-model pretraining, so accuracy isn't a clean generalization claim
(the dashboards already flag `contamination_unsafe`); and (b) **not family-structured** — a random
draw means a stored skill rarely matches the next task, so reuse stays low *even with* the 004
adjacency curriculum. This feature supplies a **clean, uncontaminated, family-structured** task source
so the **within-family reuse test** can give a defensible compounding verdict: *within a family of one
solution method, does escalation drop after the first member, and is the skill crystallized from
member 1 retrieved + applied to members 2..N?* A flat within-family curve is recall, not compounding —
and an honest recorded negative.

This is **P4.7 / decision D13** — the strongest available answer to the reuse question.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — A clean, family-structured task pool exists (Priority: P1)

As the operator, I want a pool of **uncontaminated, family-labelled** problems whose ground truth is
**derived by the verifier, not asserted by the generator**, so that any learning measured on it is a
clean generalization claim, not recall of memorized data.

**Why this priority**: Without a trustworthy clean pool, every downstream measurement is muddy. This
is the substrate the whole feature rests on, and is independently valuable (a contamination-safe set
the eval protocol can use).

**Independent Test**: Generate a batch, load it, and confirm every loaded row is
`contamination_safe=TRUE`, carries a `family`, has ground truth that the verifier reproduces from the
generator's code, and that no rejected (unclean) problem reaches the pool.

**Acceptance Scenarios**:

1. **Given** the generator runs over the families, **When** a candidate is produced, **Then** ground
   truth is obtained by **executing** the generator's solution code under the verifier — the
   generator's stated answer is never taken on faith (II).
2. **Given** a candidate whose answer is a decimal/irrational, or whose code crashes, imports
   forbidden modules, hides a constant not in the prose, or leaks the answer into the question,
   **When** validated, **Then** it is **rejected** and never loaded.
3. **Given** a validated batch, **When** loaded into the pool, **Then** each row has
   `benchmark='qwen-gen'`, `contamination_safe=TRUE`, a non-null `family`, and an embedding (so the
   004 curriculum can bias toward it).
4. **Given** the same batch loaded twice, **When** reloaded, **Then** no duplicates are created
   (stable id), and re-runs are idempotent.

---

### User Story 2 — Generator and judge are independent (Priority: P1)

As the operator, I want the **generator, teacher, and judge to be three different parties**, so the
clean pool can't be gamed by a single model writing both the problem and its own answer.

**Why this priority**: This is the integrity guarantee that makes the clean pool meaningful (and is a
constitution requirement). It ships with US1.

**Independent Test**: Confirm the generator model is distinct from the escalation teacher and that the
only arbiter of correctness is the symbolic verifier; confirm a generator-claimed answer that the
verifier disproves is rejected.

**Acceptance Scenarios**:

1. **Given** a candidate, **When** validated, **Then** correctness is decided **only** by the symbolic
   verifier executing the code — never by the generating model's assertion (VIII).
2. **Given** the generator is a local open model and the escalation teacher is the frontier model,
   **When** problems are later solved by the loop, **Then** generator ≠ teacher ≠ judge holds
   end-to-end (lineage independence decorrelates pretraining).

---

### User Story 3 — The within-family reuse verdict is legible (Priority: P1)

As the operator, I want reuse-rate and escalation-rate **sliced by family and by within-family
position**, so I can read the cleanest possible compounding signal and report a flat result honestly.

**Why this priority**: The family pool is only worth building if the by-family verdict is readable —
this is the deliverable (the measurement, D7/D8). It depends on US1 (the pool) + the live loop.

**Independent Test**: Run cohorts over the family pool, then query: per family, escalation rate on the
first solved member vs later members, and whether member-1's crystallized skill is retrieved/applied
to members 2..N. Confirm the drop (or flat) renders plainly.

**Acceptance Scenarios**:

1. **Given** cohorts solved over the family pool, **When** the operator queries by family, **Then**
   escalation rate for later within-family members vs the first is queryable per family.
2. **Given** a family where compounding occurs, **When** rendered, **Then** within-family escalation
   **drops** after the first member and reuse of member-1's skill on members 2..N is observable.
3. **Given** a family with no compounding, **When** rendered, **Then** the within-family curve is
   **flat** and shown plainly as a recorded negative — not hidden or errored.

---

### Edge Cases

- **Clean-but-wrong** — the generator's code runs cleanly and is accepted, but the code silently
  *diverges from the prose* (solves a different problem). This poisons ground truth → a correct solve
  is later marked wrong → fake-low reuse. Mitigation: an **optional dual-solution cross-check**
  (two independent solution derivations; accept only if they agree) for higher-trust batches.
- **Untrusted generated code execution inside the pipeline** — when the loader/CI/always-on node
  executes model-written code, it MUST run in the network-isolated sandbox, not merely a
  restricted interpreter (the standalone overnight host may use the lighter restricted runner).
- **A family the generator can't fill** (low accept rate) — the run bounds attempts per family and
  reports the shortfall rather than looping forever; a partially-filled family is still usable.
- **Generator emits non-JSON / fenced output** — tolerated (stripped); a still-unparseable candidate
  is skipped, not fatal.
- **Family-aware pool split** — whole families are kept on one side of the train/eval/transfer split
  (never split a family across pools), so the within-family test and held-out transfer stay clean.
- **Embedding backfill unavailable** — a row may load without an embedding and be backfilled later;
  missing embedding never blocks the load.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST generate math word problems where a model produces the problem text +
  an executable solution, and the **symbolic verifier executes that solution to derive ground truth**;
  the model's asserted answer MUST NEVER be used as ground truth (II).
- **FR-002**: Generation MUST be organized into **distinct solution-method families** (one method per
  family), and emit a per-problem `family` label, so within-family reuse is measurable.
- **FR-003**: The validation gate MUST reject any candidate that: crashes on execution, uses a
  forbidden capability, yields a non-clean (decimal/irrational) answer, contains a question-number not
  present in the solution (hidden constant), or leaks the answer into the question text.
- **FR-004**: The loader MUST ingest validated problems into the benchmark pool with
  `contamination_safe=TRUE`, a non-null `family`, source marked as generator-origin, and a **stable id**
  so reloads are idempotent (no duplicates).
- **FR-005**: The pool partition MUST be **family-aware** — a family is never split across
  train/eval/transfer pools; some families MAY be reserved wholly to the held-out transfer pool (III).
- **FR-006**: Loaded problems MUST be embeddable on the same basis as existing pools so the curriculum
  can bias toward them; a missing embedding MUST NOT block the load (backfillable later).
- **FR-007**: The generating model MUST be **independent** of the escalation teacher and of the judge
  (generator ≠ teacher ≠ judge), end-to-end (VIII).
- **FR-008**: When the pipeline (loader/CI/always-on node) executes model-generated code, it MUST run
  in the **network-isolated sandbox** (X); the standalone generation host MAY use a lighter restricted
  runner.
- **FR-009**: The feature MUST expose a **by-family** measurement: reuse-rate and escalation-rate per
  family and by within-family position (first member vs later members), queryable and renderable.
- **FR-010**: A flat within-family result MUST be a **legible recorded negative**, not an error or a
  hidden state (D7/D8).
- **FR-011**: An **optional dual-solution cross-check** MUST be available to raise ground-truth trust
  (accept only when two independent solutions agree); it MAY be off by default for throughput.
- **FR-012**: **Loading MUST be idempotent** — re-running the loader on the same (or overlapping)
  JSONL MUST NOT duplicate or corrupt pool rows (stable `problem_id` + conflict-skip). Generation is
  **re-runnable** (a fresh run may regenerate problems; the loader's idempotency absorbs overlap);
  resumable generation (append + skip-already-produced) is a nice-to-have, not required.

### Key Entities *(include if feature involves data)*

- **Generated problem**: `{question, answer, family, n_steps, source}` — a clean, family-labelled
  word problem whose answer was verifier-derived.
- **Family**: one solution method; the unit of the within-family reuse test. New attribute on the
  benchmark pool.
- **Benchmark pool row (extended)**: existing benchmark task + a `family` label +
  `contamination_safe=TRUE` + generator source.
- **By-family verdict slice**: per-family reuse/escalation, split by within-family position.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A **contamination-safe, family-labelled** pool exists — 100% of generator-origin rows
  are `contamination_safe=TRUE` with a non-null `family`.
- **SC-002**: **100%** of pool ground-truth values are verifier-derived (executed), not
  generator-asserted; a generator answer the verifier disproves never enters the pool.
- **SC-003**: The validation gate rejects **every** unclean candidate class (crash, forbidden
  capability, non-clean answer, hidden constant, leaked answer) — zero such rows in the pool.
- **SC-004**: Reloading a batch produces **zero** duplicates (idempotent).
- **SC-005**: No family is split across pools; reserved transfer families have **zero** training rows
  (III).
- **SC-006**: The **by-family** reuse/escalation slice is queryable, split by within-family position;
  a family with no compounding renders as a flat series without error.
- **SC-007**: On at least one family where compounding occurs, **within-family escalation drops** from
  the first solved member to later members and member-1's skill is observably reused on members 2..N —
  OR the result is honestly recorded as flat (a valid negative).
- **SC-008**: All model-generated code executed inside the pipeline runs network-isolated (X) — zero
  in-pipeline executions outside the sandbox.

## Assumptions

- **The standalone generator already exists** (working overnight script) and is brought into the repo;
  this feature is its productionization + integration, not a from-scratch design.
- **The symbolic verifier + the `--network none` sandbox already exist** (002) and are reused for
  in-pipeline ground-truth derivation and any in-pipeline execution.
- **The benchmark pool, pools, embeddings, and curriculum already exist** (001/004/0006); this adds a
  `family` dimension + a generator source, additively.
- **Generation runs locally** on a host with a small open model (separate from the always-on node);
  output is a file later loaded into the pool. The always-on node does not need a generator model.
- **"Clean" = integer or rational** ground truth (no decimal approximations); the family list is the
  10 named solution methods (extensible later).
- **Dual-solution cross-check is optional** (off by default) — a throughput/trust tradeoff, not
  required for a first clean pool.
- **Math pilot only** (I); families are GSM8K-structure arithmetic/algebra.

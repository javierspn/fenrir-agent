# Phase 0 — Research: Feasibility-Gated Curriculum (004)

Four selection decisions had to be resolved before design. Each reuses an existing substrate;
none introduces a new dependency or a novelty objective (FR-006 / D6 rejection).

---

## R1 — How is task↔skill adjacency computed?

**Decision**: Adjacency is the **max pgvector cosine between the task's embedding and the embeddings
of the current skill loadout** (`skills WHERE state IN ('stable','testing')`) — the *same* cosine the
live retriever already uses (`fenrir/memory/retrieval.py:51`), evaluated at selection time instead of
solve time. Because `benchmark_tasks` has no `embedding` column, add one (`vector(768)`) + ivfflat
index and backfill the training pool once via `fenrir.memory.embed.embed(content)`.

**Rationale**: The spec's Assumption is explicit — *"adjacent" is defined by retrievability*, not by a
hand-authored taxonomy. Reusing `RETRIEVAL_SIM_FLOOR` (0.80) as the "a skill will be retrieved"
reference means the curriculum and the retriever agree on what "covered" means by construction —
coverage measured on the board is the same quantity the curriculum optimizes. No new classifier
(Constitution XI). The lexical lane is *not* reused for selection: it is query-shaped and noisy for
ranking a whole pool; cosine over a stored task vector is stable and index-backed.

**Alternatives considered**: (a) embed-on-the-fly per candidate every selection — rejected, O(pool)
embeds per pick even if cached; the stored column is computed once. (b) a learned adjacency classifier
— rejected as unvalidated heavy component (XI / D4). (c) reuse the full `retrieve()` path per
candidate — rejected: it also scans episodes/abstractions and is built for one query, not pool ranking.

---

## R2 — What are the adjacency bands, and what does the feasibility gate reject?

**Decision**: Classify each candidate's max-skill-cosine `c` into three bands:

| Band | Condition | Meaning | Adjacency-lane action |
|---|---|---|---|
| **infeasible** | `c < ADJACENCY_FEASIBILITY_FLOOR` | nothing in the loadout is near it — cold | **rejected by the gate** (FR-002) |
| **adjacent** | `ADJACENCY_FEASIBILITY_FLOOR ≤ c < ADJACENCY_TRIVIAL_CEIL` | reuse possible, learning still required | **preferred** (FR-001) |
| **trivially-covered** | `c ≥ ADJACENCY_TRIVIAL_CEIL` | near-duplicate of an existing skill | **rejected** (anti coverage-inflation) |

The **feasibility gate** = the adjacency lane only ever emits tasks in the *adjacent* band. Defaults:
`ADJACENCY_FEASIBILITY_FLOOR = 0.80`, `ADJACENCY_TRIVIAL_CEIL = 0.92`. The trivial ceiling is the
direct defense against the **coverage-inflation hack** (spec Edge Case): an over-eager bias feeding
near-identical tasks raises *training* coverage while teaching nothing — the ceiling refuses them, and
the held-out eval verdict + reuse cross-check (III) catch any that slip through.

**Floor reconciliation (must equal the retrieval floor).** The feasibility floor defaults to **0.80 =
`RETRIEVAL_SIM_FLOOR`** deliberately. The headline coverage metric (SC-001, the 🧩 panel) is a
*solve-time retrieval hit* — `retrieval_skill_id IS NOT NULL`, set only when a skill clears
`RETRIEVAL_SIM_FLOOR` at solve. If the adjacency floor sat *below* that (e.g. 0.55), tasks in
`[0.55, 0.80)` would be "adjacent" for selection yet would **not** retrieve a skill at solve time — so
the lower half of the band could not move the very metric it targets. Pinning the floor to the
retrieval floor makes the adjacent band `[0.80, 0.92)` exactly "a skill *will* be retrieved, but the
task is not a trivial near-duplicate" — every adjacency-lane pick is a coverage hit by construction.
The operator may lower the floor below 0.80 to deliberately feed *just-out-of-reach* tasks (a
skill-strengthening bet that grows coverage only as skills generalize), but that is an explicit
off-default choice, not the baseline that proves the lever.

**Rationale**: "Feasible but not trivial" is exactly the spec's "close enough that reuse is possible,
far enough that something is learned." Bands are simple, inspectable thresholds (no opaque scoring) and
operator-tunable. Feasibility is defined *relative to the local learner's loadout* — every benchmark
task is solvable by the frontier teacher, so "infeasible" means "the adjacency lane should not spend a
non-external slot here," not "unsolvable"; such tasks still reach the system through the external mix.

**Alternatives considered**: (a) a single floor, no ceiling — rejected, leaves the inflation hack open.
(b) hard prerequisite-DAG feasibility — rejected: no prerequisite graph exists for math benchmark rows
and building one is out of scope (XI). Cosine-band feasibility is the cheap, available proxy.

---

## R3 — At what granularity is the 30% external mix enforced, and what is "external"?

**Decision**: Enforce at **cohort granularity** inside `run(n)`. "External" = a **uniform-random draw
from the training benchmark pool** — i.e. the *current* `select_task` behaviour, preserved verbatim as
a second lane. A deterministic quota guarantees `ceil(EXTERNAL_MIN_FRACTION · n)` of the cohort's slots
take the external lane regardless of adjacency (default `EXTERNAL_MIN_FRACTION = 0.30`). The external
lane is also the **fallback** for cold-start (empty loadout → no adjacent band exists) and
adjacency-exhaustion (every adjacent task already ran this cohort) — guaranteeing a full, valid cohort
(FR-008).

**Rationale**: All training rows are sourced from external math benchmarks (`benchmark_tasks.benchmark`
∈ MATH/GSM8K/…); there is no separate "synthetic" pool to exclude, so the diversity guard is "a
guaranteed share of *unbiased* draws," which preserves breadth against the over-narrowing edge case.
Cohort granularity (not per-iteration) is the natural unit: the harness runs `run(n)` as one cohort,
and the quota is simplest to reason about and test across the n slots. Selection is seedable so a
gate-ON vs gate-OFF A/B over the same pool is reproducible (Independent Test, US1).

**Alternatives considered**: (a) per-iteration 30% coin-flip — rejected: only meets 30% in
expectation, can violate SC-005 on a short cohort. (b) a separately partitioned "diversity pool" —
rejected: no such partition exists and creating one is scope creep (XI). The deterministic slot quota
meets "≥30% on 100% of cohorts" exactly.

---

## R4 — `ADJACENCY_STRENGTH` knob semantics and the no-novelty guarantee

**Decision**: `ADJACENCY_STRENGTH ∈ [0,1]` controls *only* how hard the adjacency lane pulls toward
the most-adjacent feasible task, with no other behavioural term:
- **0** → pure **feasibility filter**: pick uniformly at random *among* the adjacent-band candidates.
- **1** → strong pull: pick the **highest-cosine** adjacent candidate (ties broken by under-practiced
  `used_count`, then seedable random).
- intermediate → rank adjacent candidates by cosine and sample with weight `cosine ^ (k·strength)`
  (a monotone sharpening of the cosine ordering; `k` a fixed shape constant).

The objective is a pure function of `(feasibility band, cosine-to-loadout, used_count tiebreak)`. There
is **no** term that rewards distance-from-seen, entropy, diversity, or "newness" — the no-novelty
assertion (FR-006) is a structural property of this function, unit-tested by feeding two candidates
identical in cosine+feasibility and asserting the ranker is indifferent regardless of how "novel"
either is.

**Rationale**: D6 adopts only the *feasibility-gated* half and rejects Voyager's novelty-maximization
as a reward-hacking vector (§10.1). Making strength a sharpening of an existing-competence signal — not
an exploration bonus — keeps the bias pointed at *what the system can build on*, never at novelty for
its own sake. One scalar in `[0,1]` lets the operator sweep "filter only ↔ strong pull" without code
changes (FR-010).

**Alternatives considered**: (a) an explicit exploration/exploitation ε term — rejected: ε-exploration
*is* a novelty pull, exactly the D6 rejection. (b) reward = α·adjacency + β·novelty — rejected for the
same reason. Diversity is delivered solely by R3's forced external mix, never by a reward term.

---

## Resolved unknowns

All Technical-Context items are concrete; no `NEEDS CLARIFICATION` remains. New tunables (defaults):
`ADJACENCY_STRENGTH=0.6`, `ADJACENCY_FEASIBILITY_FLOOR=0.80` (= `RETRIEVAL_SIM_FLOOR`),
`ADJACENCY_TRIVIAL_CEIL=0.92`, `EXTERNAL_MIN_FRACTION=0.30` — all in `fenrir/settings.py`, overridable
via `infra/.env`.

**Coverage senses (I2).** "Coverage" appears in three related senses: (a) *selection-time* — a relevant
skill could be retrieved for the task (the lever); (b) the *authoritative SC-001 metric* on the 🧩
panel — `avg(retrieval_skill_id IS NOT NULL)`, a solve-time retrieval hit; (c) the gate-ON>gate-OFF
*test signal* — adjacency-band pick fraction. (b) is the headline number; (a)/(c) are its upstream
drivers. With the floor pinned to `RETRIEVAL_SIM_FLOOR` (above), (a) and (b) coincide for every
adjacency-lane pick, so the test signal (c) is a faithful proxy for the panel metric (b).

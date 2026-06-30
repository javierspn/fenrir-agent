# Phase 0 — Research: PE-gated meta-reflection

## R1 — Threshold defaults from the live PE distribution

**Decision**: `REFLECT_PE_LOW = 0.3`, `REFLECT_PE_HIGH = 0.5`.

**Rationale**: The prediction-error distribution over the last cohorts is sharply **bimodal**
(<host> `fenrir_core`, 2026-06-30):

| PE bucket | count |
|---|---|
| 0.0–0.1 | 69 |
| 0.2–0.3 | 10 |
| 0.4–0.8 | 0 |
| 0.9–1.0 | 65 |

avg 0.463 · median 0.150 · p90 0.950. There is a near-empty valley between ~0.3 and ~0.9. So any
LOW in [0.1, 0.3] separates the confident-correct cluster, and any HIGH in [0.5, 0.9] captures the
surprise/fail cluster identically. `LOW=0.3` keeps the small 0.2–0.3 group in `cheap`; `HIGH=0.5`
captures the 0.9–1.0 cluster as `full`.

**Alternatives considered**: `HIGH=0.8` (per the original feature note) — captures the *same* high
cluster on current data (valley is empty 0.5–0.9) but opens a gap with crystallization (see R2).
Rejected in favor of 0.5. Both thresholds are `settings.py` tunables, re-tunable as the distribution
shifts.

## R2 — Align `REFLECT_PE_HIGH` with `CRYSTALLIZE_PE` (no behavior gap)

**Decision**: default `REFLECT_PE_HIGH = CRYSTALLIZE_PE` (both 0.5), **and the full tier also fires on
`escalated`** (F1). Today crystallization fires on `verdict==SUCCEEDED and solve_path=='scratch' and
(escalated OR pe>=CRYSTALLIZE_PE)`. A **PE-only** gate would drop the `escalated`-with-low-PE case (a
task that needed the teacher but had small surprise) — it would crystallize today but only get
`cheap`/`none` reflection, a silent **SC-008 regression**. So `tier()` forces `full` whenever
`escalated`, making `{escalated} ∪ {pe>=HIGH}` an **exact superset** of today's crystallize predicate.
Full reflection becomes the single home of "turn a surprising/teacher-taught verified win into a
skill", covering that trigger plus the new edit path.

**Rationale**: with `HIGH == CRYSTALLIZE_PE` and the `escalated` OR-branch folded in, off-state and
on-state agree exactly on *what becomes a skill*; only the *effort tiering* (none/cheap) is new, and it
applies only to tasks that would never have crystallized anyway (low-PE, not escalated).

**Alternatives considered**: keep crystallization independent and layer reflection on top — rejected:
two overlapping skill-creation paths invite double-writes and drift. Reflection wraps it instead.

## R3 — Edit-vs-create decision rule

**Decision**: within `full` reflection on a **verified success**, edit-vs-create is driven primarily by
**whether a skill matched**:
- a **matched adjacent skill exists** (`retrieval_skill_id` set) **and** `pe < REFLECT_EDIT_PE_MAX`
  → **edit**: write a new version of that skill (VII).
- **no matched skill** (cold) **or** `pe >= REFLECT_EDIT_PE_MAX` (near-total surprise = a new method)
  → **create**: a new self-tested skill via the existing `admit`/`crystallize` path.

**Rationale**: mirrors reconsolidation (D3/P2.1 seed): a surprise on a *known* structure refines it; a
cold or maximal surprise spawns a distinct memory. Reuses `retrieval_skill_id` already in the loop, no
extra retrieval. **Reachability (U3)**: the live full-tier PE clusters at 0.9–1.0, so a low
`REFLECT_EDIT_PE_MAX` (e.g. 0.75) would sit in the empty 0.5–0.9 valley and the edit path would
*never* fire in prod — every full task would create. Default is therefore **0.95**: matched tasks with
PE 0.9–0.95 → edit (reachable on current data), PE ≥ 0.95 → create. Tunable as the distribution
shifts; if the mid-band fills, lower it.

**Alternatives considered**: always-create (today's behavior) — rejected: never refines, library only
grows (the Voyager weakness D6 calls out). Always-edit — rejected: loses genuinely new methods.

## R4 — Cheap tier = structured signal, no LLM

**Decision**: `cheap` records a lightweight structured reflection row (tier + a templated, non-LLM
note derived from existing fields: verdict, escalated, solve_path, retrieval hit) — **zero model
calls**.

**Rationale**: SC-002 requires reflection cost not to scale with low-surprise volume; the mid band is
sparse anyway. A no-LLM signal still gives the audit a third tier and a hook for richer awake
micro-reflection later (P2.6) without paying now (XI scope discipline).

## R5 — Budget suppression parity with escalation

**Decision**: the single `full` LLM call routes through the existing budget proxy. If the proxy
refuses (budget exhausted), reflection **downgrades to `cheap`** and records `outcome='suppressed'` —
identical pattern to escalation suppression already in `core.run_iteration` (the `front.get("refused")`
branch). The iteration always completes; the cap (IX) is never exceeded.

**Rationale**: reuses a proven path; keeps one definition of "what happens when broke". Reflection is
best-effort (FR-012): any other reflection error is caught, recorded as `outcome='none'`, iteration
proceeds.

## R6 — Placement & transactionality

**Decision**: call `reflect()` in `core.run_iteration` **after** the task UPDATE+commit (step 7) and
**after/around** crystallize (step 8), **before** the episode write (step 9). Reflection's own writes
(reflection row, skill version/create, the tasks reflection columns) commit in their own statement(s);
a reflection failure rolls back only reflection, never the already-committed task result.

**Rationale**: the task verdict is durable before reflection runs (D10 — a crash mid-reflection loses
no task data). Episode write stays last so `value()` can later incorporate whether reflection acted
(future hook; not required this slice).

## R7 — is_eval read-only by construction

**Decision**: `reflect()` returns `tier` for audit on `is_eval=TRUE` rows but **short-circuits before
any skill write/edit or consolidation** — the read-only guard is the first branch after tiering.

**Rationale**: III — held-out must never leak into the library. Enforced in code, asserted in tests
(SC-005), not left to caller discipline.

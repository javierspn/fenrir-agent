# Implementation Plan: PE-gated meta-reflection

**Branch**: `005-pe-gated-reflection` | **Date**: 2026-06-30 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/005-pe-gated-reflection/spec.md`

## Summary

Add an explicit **meta-reflection step** to `fenrir/core.run_iteration`, inserted between the current
crystallize step (8) and the additive episode write (9). The step classifies every task into a
**PE tier** — `full` if `escalated` (F1, exact subsumption of today's crystallize trigger), else
`none` (PE < `REFLECT_PE_LOW`), `cheap` (LOW ≤ PE < `REFLECT_PE_HIGH`), `full` (PE ≥ `REFLECT_PE_HIGH`)
— and spends effort accordingly: `none` does nothing extra (today's path),
`cheap` records a structured signal with **no LLM call**, `full` runs **one** budgeted LLM reflection
that extracts a lesson and feeds **skill edit-or-create** (moderate reflection-PE → new skill version;
large → new skill). Full reflection **subsumes** the existing crystallization create-path and adds the
edit path. Defaults are grounded in the live **bimodal PE distribution** (clusters at PE≤0.1 and
PE≥0.9): `REFLECT_PE_LOW=0.3`, `REFLECT_PE_HIGH=0.5` (= existing `CRYSTALLIZE_PE`, so the gate has no
behavior gap vs today). Audit via additive migration `0007` (tasks reflection columns + a `reflections`
table). All constitution constraints (III/IV/VI/VII/VIII/IX) hold by construction.

## Technical Context

**Language/Version**: Python 3.12 (existing `fenrir/` package)

**Primary Dependencies**: existing only — `psycopg` (Postgres), the in-house budget proxy
(`fenrir/llm/`), `fenrir.predict.prediction_error`, `fenrir.skills.{admit,crystallize}`,
`fenrir.memory.{episodes,salience}`. No new third-party deps.

**Storage**: Postgres 16 + pgvector (`fenrir_core`). Additive migration `0007_reflection.sql`.

**Testing**: pytest — unit (`tests/unit/`) + integration (`tests/integration/`, testcontainers +
real pgvector), guarded by `FENRIR_STACK_UP`/`FENRIR_OLLAMA_UP`.

**Target Platform**: <host> (always-on node), `<fenrir>` container.

**Project Type**: single project (the `fenrir` cognitive-loop library + its data stack).

**Performance Goals**: reflection adds **≤1 LLM call per task and only on `full` tier**; `none`/`cheap`
add zero model calls. Average reflection cost per task must not rise with low-surprise volume (SC-002).

**Constraints**: daily budget hard cap (IX) — `full` downgrades to `cheap` (recorded `suppressed`) when
exhausted; reflection is best-effort (an error never fails the iteration); additive-only schema.

**Scale/Scope**: one new module (`fenrir/reflect.py`), one wiring point in `core.run_iteration`, 5
settings tunables, one additive migration, unit + integration tests. No dashboard in this feature
(SQL provided for a later cut).

## Constitution Check

*GATE: must pass before Phase 0. Re-checked after Phase 1 — still passing.*

| Principle | Status | How |
|---|---|---|
| **I — math-only pilot** | ✅ | no domain change; reflection operates on the same math tasks |
| **II — external ungameable verification** | ✅ | reflection never re-judges; it consumes the existing sympy verdict; no skill from unverified output |
| **III — eval pool never trained on** | ✅ | `is_eval=TRUE` → reflection is read-only (no skill write/edit, no consolidate), enforced before any write (FR-009) |
| **IV — PE gates learning** | ✅ | this *is* the feature — tiers derive from PE; low-PE confident-correct local solves get `none` (SC-006/008) |
| **V — consolidation regulated** | ✅ | unchanged; reflection front-runs but reuses the same self-test admission, no new merge path |
| **VI — episodes additive** | ✅ | reflection writes new rows only (reflections table, skill versions); never deletes/overwrites an episode |
| **VII — skills versioned before modification** | ✅ | edit path writes a NEW skill version (prior retained); reuses existing versioning |
| **VIII — learner/judge/curriculum separated** | ✅ | reflection neither grades its own output as truth nor influences selection |
| **IX — daily budget hard cap** | ✅ | the one `full` LLM call routes through the budget proxy; on exhaustion it suppresses (parity with escalation) — cap never exceeded |
| **X — sandbox/egress** | ✅ | reflection's only model call is via the single proxy egress; any skill self-test runs in the existing `--network none` sandbox |
| **XI — scope discipline** | ✅ | one module + one wiring point + one additive migration; cheap-reflection kept LLM-free; richer variants (P2.1/P2.6) explicitly deferred |
| **XII — human-in-loop at migrations** | ✅ | `0007` applied with human confirmation on deploy (same as `0006`) |
| **XIII — autonomous only where verifiable** | ✅ | math = Tier-1 exact verifier; unchanged |

**No violations → Complexity Tracking empty.**

## Project Structure

### Documentation (this feature)

```text
specs/005-pe-gated-reflection/
├── plan.md              # this file
├── research.md          # Phase 0 — threshold + integration decisions
├── data-model.md        # Phase 1 — reflection columns + reflections table
├── quickstart.md        # Phase 1 — how to validate the gate end-to-end
├── contracts/
│   └── reflect.md       # internal contract: fenrir.reflect.reflect() + tiers
└── tasks.md             # Phase 2 (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
fenrir/
├── core.py              # wire reflect() between crystallize (8) and episode write (9)
├── reflect.py           # NEW — tier(), reflect(): gate + cheap signal + full LLM pass + edit/create
├── predict.py           # reused — prediction_error (no change)
├── settings.py          # +5 tunables: REFLECT_ENABLED, REFLECT_PE_LOW, REFLECT_PE_HIGH, REFLECT_EDIT_PE_MAX, REFLECT_MODEL_ROLE
├── skills/
│   ├── admit.py         # reused — create path (self_test admission)
│   ├── crystallize.py   # reused — candidate construction
│   └── (edit path)      # new skill-version write reuses existing versioning
└── llm/                 # reused — budget proxy single egress + graceful suppression

infra/migrations/
└── 0007_reflection.sql  # NEW — additive: tasks.reflection_tier/outcome/skill_id + reflections table

tests/
├── unit/test_reflect.py            # tier boundaries, gate, suppression, is_eval read-only
└── integration/test_reflect_loop.py# full-tier edit/create against real pgvector + sandbox
```

**Structure Decision**: single project, mirrors 002–004. Reflection is one new module
(`fenrir/reflect.py`) wired at one point in the existing loop; everything else is reuse.

## Phase 0 — Research

See [research.md](research.md). Resolves: (1) threshold defaults from the live PE distribution;
(2) alignment of `REFLECT_PE_HIGH` with `CRYSTALLIZE_PE` to avoid a behavior gap; (3) edit-vs-create
decision rule; (4) cheap-tier = no-LLM structured signal; (5) suppression parity with escalation.

## Phase 1 — Design & Contracts

- [data-model.md](data-model.md) — `tasks.reflection_tier`, `tasks.reflection_outcome`,
  `tasks.reflection_skill_id`, and the `reflections` table (lesson + links); migration `0007`.
- [contracts/reflect.md](contracts/reflect.md) — `fenrir.reflect.tier(pe)` and
  `fenrir.reflect.reflect(conn, ctx)` signatures, return shape, and the invariants tests assert.
- [quickstart.md](quickstart.md) — end-to-end validation (gate distribution, edit/create, suppression,
  is_eval read-only) + the per-cohort tier-vs-PE SQL for the later dashboard cut.

## Complexity Tracking

> No constitution violations. No entries.

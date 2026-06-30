# Implementation Plan: Contamination-safe family-structured problem generator + by-family reuse verdict

**Branch**: `006-family-problem-generator` | **Date**: 2026-06-30 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/006-family-problem-generator/spec.md`

## Summary

Productionize the working overnight generator into `benchmark_loader/`. **`generate.py`** (ported from
the Desktop script) runs a local open model (Qwen via LM Studio/Ollama) that emits problem prose +
executable `solution_code` across **10 solution-method families**, validates each candidate, and writes
JSONL `{question, answer, family, n_steps, source='qwen-gen'}` — its restricted-builtins+SIGALRM gate
is acceptable **only** on the standalone local host. **`load_generated.py`** ingests that JSONL into
`benchmark_tasks`: it **re-derives ground truth by executing `solution_code` in the existing
`--network none` sandbox** (X) and confirming it via `sympy_oracle` (II), then inserts
`content=question, ground_truth=<verifier-derived>, benchmark='qwen-gen', contamination_safe=TRUE,
family=…`, `problem_id=sha256(normalized question)` (idempotent), pool via a **family-aware split**
(whole families to train/eval/transfer; ≥1 family reserved to transfer, III). Additive migration
**`0009`** adds `benchmark_tasks.family`. The deliverable is the **by-family verdict**: reuse +
escalation sliced by family and within-family position (first solved member vs later) — the clean
compounding test. Optional dual-solution cross-check (two independent solutions must agree) raises
ground-truth trust, off by default.

## Technical Context

**Language/Version**: Python 3.12 (`benchmark_loader/` package + `fenrir/` reuse).

**Primary Dependencies**: existing only — `sympy` + `fenrir.verify.sympy_oracle`
(`verdict`/`canonical_answer`/`SUCCEEDED`), `fenrir.sandbox.runner.run` (`--network none`),
`fenrir.memory.embed` (the 0006 embedding path), `psycopg`. Generation backends call a local model
server (LM Studio `:1234` / Ollama `:11434`) via `curl` — **on the generation host only**, not on the
always-on node.

**Storage**: Postgres 16 + pgvector (`fenrir_core`). Additive migration `0009_benchmark_family.sql`.

**Testing**: pytest — unit (gate rejections, stable id, family split) + integration (load_generated
against real pgvector via `migrated_conn`, sandbox-stubbed for ground-truth derivation).

**Target Platform**: generation on a local GPU host (or free cloud GPU, see FUNDING.md); loading +
cohorts on <host> (`<fenrir>` / `fenrir_core`).

**Project Type**: single project (`benchmark_loader/` tool + `fenrir/` reuse).

**Performance Goals**: generation is model-bound (~40–70% accept, ~2k problems in a few hours on a 14B
Q4); the load + per-row sandbox verification is the only in-repo cost — bounded per row by the sandbox
timeout. No always-on cost added.

**Constraints**: II (verifier derives truth — never the generator's asserted answer), VIII
(Qwen-gen ≠ DeepSeek-teacher ≠ sympy-judge), III (family-aware held-out split), X (in-pipeline
execution sandboxed), VI (additive schema), idempotent loads.

**Scale/Scope**: 2 new modules (`generate.py`, `load_generated.py`) + a family-split helper + one
additive migration + a by-family dashboard panel/SQL + tests. Generation model lives off-repo.

## Constitution Check

*GATE: must pass before Phase 0. Re-checked after Phase 1 — still passing.*

| Principle | Status | How |
|---|---|---|
| **I — math-only pilot** | ✅ | GSM8K-structure arithmetic/algebra families only |
| **II — external ungameable verification** | ✅ | ground truth is **verifier-derived** (sandbox-execute solution_code → sympy confirm); the generator's stated answer is never trusted |
| **III — eval pool never trained on** | ✅ | family-aware split; ≥1 family reserved wholly to the transfer pool; a family is never split across pools |
| **IV — PE gates learning** | ✅ | unchanged — these are just tasks the existing loop solves |
| **VI — additive** | ✅ | `0009` adds a nullable column + index; loads INSERT only; idempotent on `problem_id` |
| **VIII — learner/judge/curriculum separated** | ✅ | generator (local Qwen) ≠ teacher (DeepSeek) ≠ judge (sympy); generator never judges its own output |
| **X — sandbox / egress** | ✅ | in-pipeline execution of model-generated code runs `--network none`; generation host's lighter runner is off the always-on node |
| **XI — scope discipline** | ✅ | 2 modules + 1 migration + 1 panel; dual-check optional; autonomous gap-gen (P3.2) explicitly out |
| **XII — human-in-loop at migrations** | ✅ | `0009` applied with human confirmation on deploy |
| **XIII — autonomous only where verifiable** | ✅ | math = Tier-1 exact verifier; unchanged |

**No violations → Complexity Tracking empty.**

## Project Structure

### Documentation (this feature)

```text
specs/006-family-problem-generator/
├── plan.md · research.md · data-model.md · quickstart.md
├── contracts/
│   ├── generate.md          # generator CLI + JSONL record + local validation gate
│   └── load_generated.md    # JSONL → sandbox-verified → benchmark_tasks loader contract
└── tasks.md                 # /speckit-tasks
```

### Source Code (repository root)

```text
benchmark_loader/
├── generate.py          # NEW — ported generator (families, backends, local gate, JSONL out)
├── load_generated.py    # NEW — JSONL → sandbox-derive ground truth → benchmark_tasks (idempotent)
├── families.py          # NEW — the 10 FAMILIES + family-aware pool-split helper (III)
├── load.py              # reused — _insert / assign_pool patterns
└── perturb.py           # reused-adjacent (contamination-safe templates)

fenrir/
├── verify/sympy_oracle.py   # reused — verdict / canonical_answer / SUCCEEDED
├── sandbox/runner.py        # reused — run(program) --network none (X)
└── memory/embed.py          # reused — embedding (0006 path), backfillable

infra/migrations/
└── 0009_benchmark_family.sql  # NEW — additive: benchmark_tasks.family + index (pool,family)

dashboard/provisioning/dashboards/
└── learning.json            # by-family reuse/escalation panel (within-family position)

tests/
├── unit/test_generate_gate.py        # gate rejections, stable id, family split
└── integration/test_load_generated.py# JSONL → sandbox-verified load (migrated_conn)
```

**Structure Decision**: single project; generator + loader live in `benchmark_loader/` next to the
existing dataset loader, reusing the verifier + sandbox + embedder. Generation model is off-repo.

## Phase 0 — Research

See [research.md](research.md): (1) verifier-derived ground truth vs the standalone gate's
restricted-builtins (in-pipeline MUST sandbox); (2) stable `problem_id` (sha256 of normalized
question) for idempotency; (3) family-aware pool split + which family to reserve to transfer; (4)
by-family + within-family-position measurement (join on `benchmark_id`); (5) optional dual-solution
cross-check; (6) where generation runs (local/cloud, not the always-on node).

## Phase 1 — Design & Contracts

- [data-model.md](data-model.md) — `0009` (`benchmark_tasks.family` + index), the JSONL record, the
  `qwen-gen` row shape, the by-family slice.
- [contracts/generate.md](contracts/generate.md) + [contracts/load_generated.md](contracts/load_generated.md).
- [quickstart.md](quickstart.md) — smoke generate → load (sandbox-verified) → by-family verdict SQL.

## Complexity Tracking

> No constitution violations. No entries.

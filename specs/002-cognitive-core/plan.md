# Implementation Plan: Cognitive Core Loop (math pilot) — 002

**Branch**: `002-cognitive-core` | **Date**: 2026-06-27 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/002-cognitive-core/spec.md`

## Summary

Build the **cognitive loop** that runs on top of the live 01-infra substrate and turns it into
a learning system on the mathematics pilot. The loop processes one training task per iteration:
**predict → retrieve → solve (small owned model) → escalate-if-stuck (frontier teacher via the
budget-governed proxy) → verify (sympy, in a network-isolated sandbox) → compute prediction error
→ write an additive episode → (on high surprise) crystallize a verified executable skill → (on a
cadence) consolidate in salience order behind a predictability gate**. Every pass emits the
metrics that reconstruct the three falsifiable curves.

**The deliverable is the measurement, not the accuracy.** A flat escalation-rate curve is a valid
negative result. The core engineering bet is that **the 01-infra schema already carries the D1–D8
columns the loop needs**, so this feature is overwhelmingly **new application code in `fenrir/`
plus one small additive migration** — not a schema rebuild (Constitution XI / D4).

Two new long-running services join the stack: the **LLM proxy** (`fenrir:8080/llm`, semaphore +
per-task budget + timeout, wraps local Ollama and the Anthropic teacher) and an **ephemeral
network-isolated sandbox** (`--network none`) that runs sympy verification and untrusted skill
code. The frontier teacher is **`claude-opus-4-8`** (configurable down to Sonnet 4.6); the small
owned solver stays local (`qwen2.5` via Ollama); embeddings reuse `nomic-embed-text`.

## Technical Context

**Language/Version**: Python 3.12 (extends the existing thin `fenrir/` package with cognitive modules)

**Primary Dependencies** (added on top of 01-infra's `psycopg[binary]`, `httpx`, `sympy`,
`pydantic-settings`, `pyyaml`, `datasets`/`huggingface-hub`):
- **`anthropic`** (official SDK) — frontier teacher calls; model id `claude-opus-4-8`, adaptive
  thinking (`thinking={"type":"adaptive"}`), `output_config={"effort":"high"}`. No `budget_tokens`,
  no sampling params (4.8 rejects them).
- **`fastapi` + `uvicorn`** — the internal `fenrir:8080/llm` proxy (single async process).
- **`redis`** (client) — fast budget counter + concurrency, source-of-truth stays Postgres
  `budget_tracking` (D10).
- Docker Engine API (via the already-mounted `/var/run/docker.sock`) — spawn `--network none`
  ephemeral verification/skill sandboxes. `sympy` runs **inside** the sandbox image.

**Local models (via `OLLAMA_HOST`)**: solver/reasoner `qwen2.5` (small owned model), embeddings
`nomic-embed-text` (768-dim, reused). Frontier teacher `claude-opus-4-8` (Anthropic) — escalation only.

**Storage**: Reuse the live 14-table schema. **Additive only**: migration `0003_cognitive_core.sql`
adds `tasks.solve_path` + `tasks.retrieval_skill_id`, `short_term_memory.importance` +
`short_term_memory.retrieval_frequency`, and `benchmark_tasks.held_out`. No drops, no
`ON DELETE CASCADE`, no overwrite (Constitution VI/VII; migration is human-confirmed, XII/FR-025).

**Testing**: pytest + testcontainers (reuse `conftest.py` `migrated_conn`). New suites: loop
heartbeat, sympy-verifier independence, crystallization-admission, consolidation salience-order +
predictability gate, escalation/budget cap, sandbox network-isolation, pool non-leakage.

**Target Platform**: Single Linux host (<host>, RTX 4070 12 GB VRAM / 31 GB RAM). Ollama native on
host; proxy + loop + sandbox via Docker.

**Project Type**: Infrastructure + Python cognitive package (single project).

**Performance Goals**: Not throughput-bound. Targets: one full iteration completes end-to-end and
persists provably; budget cap never exceeded; sandbox fails closed on any network attempt.

**Constraints**: Math-only (sympy oracle); training pool only (eval pool never read/written);
predict-before-solve; PE gates learning; additive episodes (no hard delete); skills versioned;
daily budget hard cap (`budget_tracking.daily_budget_usd`, default 2.00); sandbox network-isolated
(reaches only the proxy, and verification needs no network at all); contamination caveat surfaced.

**Scale/Scope**: Single operator, single node. One owned small model + one frontier teacher.
14,973 benchmark rows already loaded in disjoint 70/30 pools; a held-out slice is carved **from the
training pool** for the predictability gate (NEVER the evaluation pool).

## Constitution Check

*GATE: must pass before Phase 0. Re-checked after Phase 1.*

| Principle | How this feature complies | Status |
|---|---|---|
| I. Math-only pilot | sympy is the sole oracle; only math benchmark tasks selected; no new domain | ✅ PASS |
| II. External ungameable verification | Every autonomous verdict from sympy symbolic equivalence in an isolated sandbox; never textual/LLM-judge (FR-013/015) | ✅ PASS |
| III. Eval pool never trained on | Loop selects `benchmark_tasks.pool='training'` only; held-out gate slice also from training; test asserts zero eval reads (FR-001) | ✅ PASS |
| IV. PE gates learning (NON-NEGOTIABLE) | Predict-before-solve; reflection/crystallization scale with prediction_error; crystallization forbidden on correctly-predicted tasks (FR-004/005/006, SC-006) | ✅ PASS |
| V. Regulated consolidation (NON-NEGOTIABLE) | Salience-descending processing; predictability gate (merge only if held-out improves); idiosyncratic detail not merged (FR-019/020) | ✅ PASS |
| VI. Episodes additive (D1) | Episodes written to `short_term_memory`; consolidation sets `consolidated_at`, never deletes; abstractions are NEW `long_term_memory` rows (FR-016/017/021, SC-007) | ✅ PASS |
| VII. Skills versioned before modification | `skill_versions` row written before any change; small PE → new version, large PE → new skill + `contradicts` edge in `graph_updates` (FR-024) | ✅ PASS |
| VIII. Learner/judge/curriculum separation | Verifier (sympy sandbox) is independent of the proposer/solver; the crystallization admission pass is a separate execution from the solve (FR-014, SC-002/003) | ✅ PASS |
| IX. Daily budget hard cap | Proxy enforces `budget_tracking.daily_budget_usd`; on exhaustion escalation suppressed, never silently raised (FR-012, SC-008) | ✅ PASS |
| X. Sandbox network isolation | Verification/skill sandbox runs `--network none`; model calls go through `fenrir:8080/llm` only, from the orchestrator (FR-011) | ✅ PASS |
| XI. Scope discipline (D4) | No Neo4j, no curiosity curriculum, no multi-lane reranker (P2.5/P3 deferred); reuse existing schema; one additive migration | ✅ PASS |
| XII. Human-in-the-loop on self-mod | Migration `0003` applied with human confirmation; no autonomous mass skill rewrite (FR-025) | ✅ PASS |
| XIII. Autonomous only where verification cheap/ungameable (D7) | Math + sympy qualifies as autonomous; no decision-support boundary crossed | ✅ PASS |

**Gate result: PASS — no violations. Complexity Tracking left empty.**

## Project Structure

### Documentation (this feature)

```text
specs/002-cognitive-core/
├── plan.md              # This file
├── research.md          # Phase 0 — the by-design knobs resolved (models, thresholds, cadence)
├── data-model.md        # Phase 1 — entities + the additive migration
├── quickstart.md        # Phase 1 — run one iteration end-to-end + validate
├── contracts/           # Phase 1
│   ├── llm-proxy.contract.md      # fenrir:8080/llm — request/response, budget, semaphore, timeout
│   ├── sandbox.contract.md        # network-isolated verify/skill execution contract
│   ├── verifier.contract.md       # sympy adjudication: verdict = succeeded|failed|unverified
│   ├── retrieval.contract.md      # lexical (content_fts) + vector (pgvector) selector
│   ├── loop.contract.md           # one iteration: predict→retrieve→solve→escalate→verify→PE→episode
│   ├── consolidation.contract.md  # salience order + predictability gate
│   ├── crystallization.contract.md# code+self_test, independent admission pass, versioning
│   ├── dashboard.contract.md      # Grafana "Learning" panels via grafana_ro (3 curves + supporting)
│   └── migration.contract.md      # 0003_cognitive_core.sql — additive columns, human-confirmed
└── tasks.md             # Phase 2 (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
fenrir/                          # existing thin package — now grows cognitive modules
├── settings.py                  # EXTEND: TEACHER_MODEL (default claude-opus-4-8), SMALL_MODEL
│                                #   (qwen2.5), thresholds (escalation/PE/similarity), salience
│                                #   weights, consolidation cadence, held-out fraction
├── db.py                        # reused as-is (migration applier picks up 0003)
├── core.py                      # NEW: the loop runner — one iteration, orchestrates the phases
├── memory/
│   ├── __init__.py
│   ├── retrieval.py             # NEW: lexical (ts_rank_cd over content_fts) + vector (pgvector cosine)
│   ├── episodes.py              # NEW: additive episode writer + salience (PE×importance×retr_freq)
│   └── salience.py              # NEW: salience score + retrieval_frequency bump on use
├── consolidation/
│   ├── __init__.py
│   └── sleep.py                 # NEW: salience-ordered pass + predictability gate (held-out eval)
├── skills/
│   ├── __init__.py
│   ├── crystallize.py           # NEW: high-PE solve → code+self_test candidate
│   └── admit.py                 # NEW: independent verification pass; version vs new-skill+contradicts
├── llm/
│   ├── __init__.py
│   ├── proxy.py                 # NEW: fenrir:8080/llm FastAPI app — semaphore + budget + timeout
│   ├── router.py                # NEW: local (Ollama qwen2.5) vs frontier (anthropic claude-opus-4-8)
│   └── budget.py                # NEW: redis counter + Postgres budget_tracking source-of-truth
├── verify/
│   ├── __init__.py
│   └── sympy_oracle.py          # NEW: symbolic-equivalence verdict (runs INSIDE the sandbox)
├── sandbox/
│   ├── __init__.py
│   ├── runner.py                # NEW: spawn ephemeral `--network none` container; run verify/skill
│   └── Dockerfile.sandbox       # NEW: minimal python+sympy image, no network tooling
└── predict.py                   # NEW: predicted outcome + confidence BEFORE solving; PE after

infra/
├── docker-compose.yml           # EXTEND: add `fenrir` (loop+proxy) service exposing 8080 internally;
│                                #   keep neo4j absent; mount docker.sock for sandbox spawning
└── migrations/
    └── 0003_cognitive_core.sql  # NEW: additive columns only (solve_path, retrieval_skill_id,
                                 #   importance, retrieval_frequency, held_out) — human-confirmed

dashboard/provisioning/dashboards/
└── learning.json                # REPLACE placeholder: 3 curves + episode/skill/pool/consolidation/PE

tests/integration/
├── test_loop_heartbeat.py       # US1: predict→solve→sympy→episode; eval pool untouched (SC-001)
├── test_verifier_independent.py # FR-014/SC-002: verdict only from sympy; verifier ≠ proposer
├── test_crystallize_admit.py    # US2/SC-003: code+self_test admitted only after independent pass
├── test_no_crystallize_lowpe.py # SC-006: no crystallization on correctly-predicted tasks
├── test_escalation_budget.py    # US3/SC-008: low-conf escalates; budget cap never exceeded
├── test_consolidation_gate.py   # US4/SC-007: salience order; gate rejects non-improving; no delete
├── test_sandbox_isolation.py    # FR-011: network attempt fails closed
├── test_pool_no_leak.py         # FR-001/III: loop never reads/writes evaluation pool
└── test_retrieval_solvepath.py  # SC-009: similar task → retrieval/skill-application path recorded
```

**Structure Decision**: Extend the existing single-project `fenrir/` package with the cognitive
modules that 01-infra explicitly deferred (`core.py`, `memory/`, `consolidation/`, `skills/`,
`llm/`, `verify/`, `sandbox/`). The data layer is reused verbatim; the only schema change is the
additive `0003` migration. The proxy and sandbox are the two genuinely new runtime surfaces.

## Complexity Tracking

> No constitution violations — section intentionally empty. The two new services (proxy, sandbox)
> are mandated directly by Constitution X and FR-011/013, not optional complexity.

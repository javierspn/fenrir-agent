# Phase 0 Research — Cognitive Core Loop (002)

Resolves every NEEDS-CLARIFICATION-by-design knob the spec/plan left open. Each entry: **Decision
/ Rationale / Alternatives considered**. All values are operator-configurable via `fenrir/settings.py`
unless noted; the defaults below are the starting point for the first cohort.

---

## R1 — Small owned (local) solver model

- **Decision**: `qwen2.5` via Ollama (`OLLAMA_HOST`), already pulled by 01-infra bootstrap. Embeddings
  reuse `nomic-embed-text` (768-dim). Setting: `SMALL_MODEL=qwen2.5`.
- **Rationale**: Already present on <host>, fits 12 GB VRAM, strong on math for its size. The hypothesis
  is about substituting **memory + skills** for **scale** — the solver must be small and owned so the
  escalation-rate curve has meaning. Reusing the embedder keeps retrieval consistent with what's already
  indexed in `content_fts` + pgvector.
- **Alternatives**: `llama3.1:8b` (also pulled) — kept as a fallback id; a larger Qwen 14B/32B would
  blur the "small model" claim and not fit alongside the embedder on one 12 GB card.

## R2 — Frontier teacher (escalation) model

- **Decision**: `claude-opus-4-8` (Anthropic), adaptive thinking, `effort:"high"`, via the proxy.
  Setting: `TEACHER_MODEL=claude-opus-4-8`. Budget fallback knob: `claude-sonnet-4-6`.
- **Rationale**: Escalation fires only on hard/cold/high-PE tasks (rare by design, budget-capped),
  and Constitution VIII requires the teacher/judge to be of **equal-or-greater capability** than the
  learner. The strongest math reasoner is justified at low volume. Pricing (per 1M tok): Opus 4.8
  $5/$25, Sonnet 4.6 $3/$15, Haiku 4.5 $1/$5.
- **Alternatives**: Sonnet 4.6 (cheaper, the configured fallback under budget pressure); Haiku 4.5
  **rejected as teacher** — escalation tasks are exactly the hard ones it would fail, defeating the
  point of escalation. API note: 4.8 rejects `budget_tokens` and sampling params — use adaptive
  thinking + `effort`.

## R3 — Daily LLM budget

- **Decision**: Hard cap from `budget_tracking.daily_budget_usd` (existing column, **default 2.00**).
  Operator-configured per-day; the proxy reads it and never raises it silently.
- **Rationale**: Predictable cost is a survival constraint for a solo operator (Constitution IX).
  $2/day ≈ the mature ~$10–13/mo envelope with headroom for early high-escalation cohorts. The column
  already exists and is writable day one.
- **Alternatives**: Per-task hard ceiling only (insufficient — daily aggregate is the constitutional
  unit); env var (rejected — Postgres row is the durable, restart-safe source-of-truth per D10).

## R4 — Escalation threshold (when to call the teacher)

- **Decision**: Escalate when the small model's self-reported **confidence < `ESCALATE_CONFIDENCE`
  (default 0.55)** OR the task is cold (no retrieved skill/episode above the similarity floor) OR
  predicted prediction-error is high. Setting also gates on budget: if the daily cap is exhausted,
  escalation is suppressed regardless (FR-012).
- **Rationale**: Confidence/feasibility below threshold is the spec's defined trigger (FR-010). Coupling
  to "cold" (empty retrieval) captures novelty even when the model is miscalibrated-confident. A single
  scalar keeps the router simple (the multi-lane selector is deferred P2.5).
- **Alternatives**: Pure entropy/logprob gating (Ollama exposure inconsistent across models); always-
  escalate-on-fail (burns budget; escalation must be the exception). Threshold will be tuned from the
  first cohort's calibration data in `confidence_calibration`.

## R5 — Prediction-error definition + crystallization threshold

- **Decision**: `prediction_error` ∈ [0,1] = blend of the **verification delta** (predicted correctness
  vs sympy verdict, the dominant term) and the **calibration gap** (|predicted_confidence − realized
  correctness|). Stored on `tasks.prediction_error` and `short_term_memory.prediction_error` (existing
  columns). Crystallization fires only when `prediction_error ≥ CRYSTALLIZE_PE (default 0.5)` **and**
  the task was solved/verified. Consolidation effort scales with PE.
- **Rationale**: D3 names verification delta as the cleanest signal (hard math ground truth) plus the
  near-free calibration term; both columns already exist. Constitution IV forbids crystallizing on a
  task already predicted correctly — a high-PE gate enforces SC-006 directly.
- **Alternatives**: Tool-result mismatch and user-correction signals (deferred to P4 / out of math
  scope); raw confidence as PE (ignores the actual verdict — the master signal must include ground truth).

## R6 — Salience score + weights

- **Decision**: `salience = prediction_error × importance × retrieval_frequency` (product form, per
  spec FR-018 and PROJECT_RAGNAROK §4). Additive columns `short_term_memory.importance` (default 1.0)
  and `short_term_memory.retrieval_frequency` (default 0, bumped on each retrieval) back the two
  factors the schema didn't already have; `salience` and `prediction_error` columns already exist.
  Retrieval-frequency increments when an episode/skill is surfaced (FR-018).
- **Rationale**: Product form means a zero in any factor (no surprise, never retrieved) drops salience
  to the floor — the brain's selective tagging (Science 2024). Keeping `importance` a settable scalar
  (default 1.0) leaves room to weight anchors/user tasks later without a schema change.
- **Alternatives**: Weighted sum (a high single term dominates; the spec specifies the product);
  recency term (recency is a *retrieval* cue, not a salience factor — deferred with the temporal lane).

## R7 — Consolidation cadence ("sleep")

- **Decision**: One consolidation level for the pilot, triggered on a **cadence floor**
  (`CONSOLIDATION_EVERY_N_ITERS`, default 50 iterations) or manually. Processes unconsolidated episodes
  in **descending salience order**; merges an abstraction into `long_term_memory` only if it passes the
  predictability gate. Source episodes get `consolidated_at` set, never deleted.
- **Rationale**: Constitution V + D2: cadence floor keeps cost predictable for a solo operator while
  salience ordering adopts prioritized replay. Collapsing the four PROJECT_RAGNAROK sleep levels into
  one is deliberate scope discipline (XI) — the pilot needs *a* regulated merge, not the full ultradian
  schedule. `consolidation_runs` already records each pass.
- **Alternatives**: Cron windows (`*/30`, deep at 02:00, etc.) — deferred; multi-level deep/abstract
  passes — deferred until single-level consolidation shows measured value.

## R8 — Predictability gate + held-out set construction

- **Decision**: An abstraction is merged only if, on a **held-out set of training-pool tasks**, the
  post-merge memory predicts/solves at least as well as pre-merge (no regression). The held-out slice is
  carved from the **training** pool via additive boolean `benchmark_tasks.held_out` (default false), with
  fraction `HELDOUT_FRACTION` (default 0.1) marked once at first consolidation. The **evaluation pool is
  never touched** (Constitution III; spec Assumption).
- **Rationale**: Go-CLS regulated consolidation — merge only what generalizes (FR-020). Drawing held-out
  from training keeps the protected eval pool pristine. A boolean flag is the minimal additive change and
  is deterministically reproducible.
- **Alternatives**: Hold out from the evaluation pool (**forbidden** — leakage, III); a separate table
  (heavier than a flag); dynamic per-run sampling (non-reproducible — a fixed flagged slice is auditable).

## R9 — "Similar task" retrieval threshold + selector

- **Decision**: Two-lane retrieval (the simple version, **not** the P2.5 multi-lane reranker): lexical
  `ts_rank_cd(content_fts, plainto_tsquery($q))` over both memory tables + vector cosine over pgvector
  `embedding`. A skill/episode is "applicable" when cosine similarity ≥ `RETRIEVAL_SIM_FLOOR
  (default 0.80)` OR it tops the lexical lane. Retrieved verified skill is preferred over cold solve
  (FR-008); the solve path is recorded as `retrieval` vs `scratch`.
- **Rationale**: Reuses exactly the indexes 01-infra built (`content_fts` GIN + ivfflat cosine).
  A 0.80 cosine floor is a conservative starting point for "similar enough to apply a skill" and is
  tunable from the retrieval-share curve. Recall-vs-from-scratch is one of the three measured curves.
- **Alternatives**: Single cosine funnel (misses lexical-exact matches — the spec mandates both lanes);
  cross-encoder rerank + parallel-convergent lanes (explicitly deferred, P2.5).

## R10 — Verifier sandbox + isolation mechanism

- **Decision**: sympy adjudication and all untrusted skill-code execution run in an **ephemeral Docker
  container started `--network none`** (image `Dockerfile.sandbox`: minimal python + sympy, no network
  tooling), spawned via the already-mounted `/var/run/docker.sock`, with CPU/memory/time limits.
  Verification needs **no** network; skill self-tests need none either. Model calls never happen inside
  the sandbox — they go through `fenrir:8080/llm` from the orchestrator.
- **Rationale**: Constitution X requires sandboxes reach only the proxy; sympy/skill execution needs
  *nothing*, so `--network none` is the strictest correct choice and fails closed on any egress attempt
  (FR-011). Separating verification from proposal satisfies Constitution VIII (the verdict is produced by
  an independent process). Docker ephemeral matches PROJECT_RAGNAROK §10's execution-layer design.
- **Alternatives**: In-process sympy (no isolation — untrusted crystallized code could touch the host);
  nsjail/firejail subprocess (lighter, but Docker is already in the stack and gives a clean network
  namespace + resource caps); a long-lived sandbox (ephemeral-per-task is the safer blast-radius choice).

## R11 — LLM proxy design (`fenrir:8080/llm`)

- **Decision**: Single FastAPI/uvicorn async service. One `POST /llm` endpoint: `{role, task_id,
  prompt, model_class}` → routes local (`qwen2.5` via Ollama) or frontier (`claude-opus-4-8` via the
  `anthropic` SDK). Enforces a **semaphore** (concurrency cap, default 2 local / fewer frontier),
  **per-task budget** + **daily budget** (`budget_tracking`, redis fast counter rehydrated from
  Postgres on restart), and a **per-call timeout**. On daily-cap exhaustion, frontier calls are refused
  (escalation suppressed); local best-effort continues; never silently exceeds (FR-011/012, IX).
- **Rationale**: One choke point means "nobody calls the LLM directly" (PROJECT_RAGNAROK §10). Postgres
  source-of-truth + redis counter is the D10 durability pattern (a redis wipe loses zero durable budget
  state). The multi-node router is deferred — single-node <host> only.
- **Alternatives**: Direct SDK/Ollama calls from each module (violates X — no central budget/semaphore);
  multi-node provider list with priority/ping (deferred, P4.4 — <host> is the only always-on node).

## R12 — Conflicting / contradicting skills

- **Decision**: Version before modify (Constitution VII): write a `skill_versions` row first. Small PE
  → new **version** of the same skill; large PE → **new skill** plus a `contradicts` edge recorded in
  `graph_updates` (`relation_type='contradicts'`, `trigger='meta_reflection'`). Never silent overwrite.
- **Rationale**: Reuses `skill_versions` and `graph_updates` (both exist) — no schema change for the
  contradicts link. Matches FR-024 and the L&M-2018 small-edit / large-spawn rule.
- **Alternatives**: A `contradicts_skill_id` column on `skills` (additive but redundant — the graph
  table already models typed edges); silent overwrite (forbidden, VII).

---

## Resolved settings summary (defaults → `fenrir/settings.py`)

| Setting | Default | Source / gate |
|---|---|---|
| `SMALL_MODEL` | `qwen2.5` | R1 |
| `EMBED_MODEL` | `nomic-embed-text` | R1 (reused) |
| `TEACHER_MODEL` | `claude-opus-4-8` | R2 (fallback `claude-sonnet-4-6`) |
| `DAILY_BUDGET_USD` | `budget_tracking.daily_budget_usd` (2.00) | R3 / IX |
| `ESCALATE_CONFIDENCE` | 0.55 | R4 / FR-010 |
| `CRYSTALLIZE_PE` | 0.5 | R5 / IV, SC-006 |
| salience form | `PE × importance × retrieval_frequency` | R6 / FR-018 |
| `CONSOLIDATION_EVERY_N_ITERS` | 50 | R7 / V |
| `HELDOUT_FRACTION` | 0.1 (training pool only) | R8 / III |
| `RETRIEVAL_SIM_FLOOR` | 0.80 | R9 / FR-008 |
| sandbox isolation | Docker `--network none`, ephemeral | R10 / X |
| proxy concurrency | 2 local | R11 |

**No NEEDS CLARIFICATION remains.** All knobs resolved with constitution-traceable defaults; every
value is tunable from the first cohort's measured curves without a schema change.

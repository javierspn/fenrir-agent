# Contract: Bootstrap

**Interface**: `python -m fenrir.bootstrap` (also invoked in the stack bring-up flow).
Idempotent; safe to run any number of times.

## Sequence
1. **Global guard** — `SELECT value FROM system_state WHERE key='bootstrapped'` present → log
   "already bootstrapped", exit 0 (no changes). The marker is written **only** at step 6, so a run
   interrupted before completion has no marker and correctly falls through to the per-section
   idempotent steps below. A non-empty `long_term_memory` from a partial run MUST NOT short-circuit
   here — that would strand un-loaded benchmarks (see research R6, FR-017/018).
2. **Models** — pull `qwen2.5`, `llama3.1`, `nomic-embed-text` via `OLLAMA_HOST`
   (Ollama skips present models). Failure → report model/host, do NOT mark bootstrapped.
3. **Anchors** — seed 50–100 rows from `infra/seeds/anchors_math.yaml`:
   `is_anchor=TRUE, strength=1.0, decay_rate=0, memory_type='semantic',
   domain='mathematics'`; `INSERT … ON CONFLICT (natural_key) DO NOTHING`.
   (`content_fts` is a generated column — populated automatically from `content`; bootstrap
   writes no FTS value. Bootstrap seeds no `skills` rows, so D6 columns need no action here.)
4. **Relations** — seed obvious starting relations from `infra/seeds/relations_seed.yaml` into
   Postgres `graph_updates` with `trigger='bootstrap_seed'` (NO graph DB). Endpoints are given as
   anchor **natural keys** and resolved to the matching `long_term_memory.id` from step 3;
   `INSERT … ON CONFLICT (from_node, relation_type, to_node) DO NOTHING`.
5. **Benchmarks** — run benchmark-loader: download math datasets, partition by
   deterministic hash (`hash(problem_id) % 100 < 70` → training else evaluation), disjoint.
   Populate `difficulty` from the source level field (feeds EVAL_PROTOCOL M6). Raw HF problems
   load with `contamination_safe=FALSE` (likely in base-model pretraining).
5b. **Eval bench (D8 sub-step, deferred-buildable)** — build the contamination-safe frozen eval
   set via `benchmark_loader/perturb.py` (procedural perturbation with sympy-re-derived ground
   truth) and/or post-cutoff ingest; rows marked `contamination_safe=TRUE` + `perturbation_of`.
   Deterministic/idempotent so the frozen set is byte-stable across reruns (see EVAL_PROTOCOL.md
   §7). Not required for stack bring-up; required before the first measured eval round.
6. **Marker** — upsert `system_state('bootstrapped', now())`.

## Guarantees (maps to SC-003/004/005)
- Second full run: **zero** row changes across every table.
- Interrupted run: re-run completes only the missing sections (per-section idempotency). Because the
  global guard keys on the `bootstrapped` marker (step 6), not on row presence, a crash after
  anchors but before benchmarks resumes correctly instead of short-circuiting.
- Post-run: 50–100 anchors exist, 100% `is_anchor=TRUE` at `strength=1.0`; a subsequent
  decay pass alters 0 of them.
- Post-run: 0 problems appear in both pools.

## Failure modes
- Missing required env → fail fast, name the variable, exit non-zero (SC-008).
- Ollama unreachable / dataset unavailable → report, leave system **un-bootstrapped**.

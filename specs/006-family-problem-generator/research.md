# Phase 0 — Research: family problem generator

## R1 — Two execution contexts, two trust levels

**Decision**: the standalone **generation host** uses the ported script's restricted-builtins + SIGALRM
gate (fast, local, javier's machine); the **in-repo loader** re-derives + confirms ground truth by
running `solution_code` in the existing `--network none` Docker sandbox (`fenrir.sandbox.runner.run`).

**Rationale**: X requires network-isolated execution of untrusted (model-written) code *inside the
pipeline*. The local overnight host is trusted/off the always-on node, so the lighter runner is
acceptable there — but the authoritative ground truth that enters `benchmark_tasks` MUST be the
sandbox-verified one (II/X). So the loader never trusts the JSONL `answer` field blindly; it
re-executes and confirms.

**Alternatives**: trust the generator's JSONL answer — rejected (II violation, and the generation
host's gate is weaker than the sandbox).

**Residual blast radius (X1):** the host-side gate runs model code under restricted-builtins+SIGALRM,
not `--network none`. Acceptable because it runs on a trusted local/cloud generation host *off the
always-on node*, the static guards block `import os/socket/subprocess/open`, and nothing that enters
`benchmark_tasks` is trusted until the sandbox re-derivation. Confirm the generation host has no
sensitive network reach. No spec change — documented carve-out.

## R2 — Verifier-derived ground truth

**Decision**: in `load_generated`, build a trusted harness program that `exec`s `solution_code`,
reads `answer`, prints JSON; run it via `sandbox.run`; take the sandbox's produced answer as ground
truth; additionally assert `verdict(canonical_answer(produced), canonical_answer(jsonl_answer)) ==
SUCCEEDED` — if the generator's claimed answer disagrees with what its own code computes, **reject**
(a self-inconsistent candidate). The stored `ground_truth` is the sandbox-derived value.

**Rationale**: II — sympy owns truth. Reuses `admit.py`'s exact harness+oracle pattern (002), so the
generated-problem path and the skill-admission path share one verification mechanism.

## R3 — Stable, idempotent `problem_id`

**Decision**: `problem_id = 'qwen-gen-' + sha256(normalize(question))[:16]` where `normalize` lowercases
+ collapses whitespace (matches the generator's dedup key). `benchmark_tasks.problem_id` is UNIQUE, so
the loader uses `INSERT ... ON CONFLICT (problem_id) DO NOTHING` → reloads are idempotent (FR-004/012,
SC-004).

**Rationale**: content-addressed id makes regeneration/reload safe and dedups across runs without a
sequence. Mirrors `load.py`'s deterministic-id intent.

## R4 — Family-aware pool split (III)

**Decision**: a helper in `families.py` maps each of the 10 families **wholly** to one pool:
`training` (most families), `evaluation` (held-out within-distribution), `transfer` (≥1 family kept
entirely out of training — e.g. `distance-meet` — for the cleanest held-out generalization). The map
is a static dict (deterministic, auditable); the loader assigns `pool = FAMILY_POOL[family]`.

**Rationale**: III — a family is one method; splitting it across pools would leak the method into
training and ruin the within-family/transfer test. Whole-family assignment keeps the held-out test
clean and the within-family reuse test intact (all of a training family's members are solvable in
sequence).

**Alternatives**: per-row 70/30 hash split (load.py's default) — rejected: would split families.

## R5 — By-family + within-family-position measurement

**Decision**: join solved `tasks` to `benchmark_tasks` on `tasks.benchmark_id = benchmark_tasks.problem_id`
(the existing link); group by `family`; within-family **position** = `row_number() OVER (PARTITION BY
family ORDER BY tasks.created_at)`. The verdict panel/SQL reports, per family: escalation rate for
position 1 vs positions ≥2, and reuse (skill/abstraction retrieved) for ≥2. **Compounding signal:
within a family, escalation(pos≥2) < escalation(pos 1) and reuse(pos≥2) > 0.**

**Rationale**: this is the falsifiable within-family test (D13). Position captures "did solving
member 1 make 2..N cheaper". Flat = recall (honest negative, FR-010).

*Schema note:* `tasks.benchmark_id` already stores the source `problem_id` (see `_new_task_row`), so
the join needs no new column — only `benchmark_tasks.family` (0009).

## R6 — Optional dual-solution cross-check

**Decision**: a `--cross-check` flag (default off) asks the generator for a **second independent**
`solution_code`; accept the problem only if **both** sandbox-execute to the same canonical answer.
Off by default for throughput; on for high-trust batches.

**Rationale**: mitigates clean-but-wrong (code diverges from prose) — the one ground-truth risk the
single-solution gate can't catch (FR-011). Two independent derivations agreeing is strong evidence the
code matches the stated problem. Kept optional (XI) — not needed for a first clean pool.

**Residual gap (A2):** dual-check confirms two *code* paths agree on a number; it does NOT prove
either matches the *prose*. Two solutions could both misread the prose the same way and agree. So it
catches code bugs, not prose↔code misreads. A stronger prose-grounded check (e.g. an independent
solver reading only the prose) is a future option for high-trust batches; documented, not built now.

## R8 — Generator must emit `solution_code` in the JSONL

**Decision**: the ported `generate.py` writes `solution_code` into each JSONL record (extending the
Desktop script, which dropped it after its local gate). The loader needs it to re-derive ground truth
in the sandbox (R2/II/X) — without it, the loader could only trust the claimed `answer`, violating II.

**Rationale**: one extra field makes the whole pool independently re-verifiable on the trusted side. A
record arriving without `solution_code` is skipped by the loader (can't be verified → can't be trusted).

**Alternatives**: load on the claimed answer alone — rejected (II). Re-generate solutions at load time —
rejected (non-deterministic, wasteful; the generator already produced a valid one).

## R7 — Where generation runs

**Decision**: generation runs on a **local GPU host or a free cloud GPU** (GCP/Azure credits, see
`FUNDING.md`), NOT on the always-on node — output is a JSONL file rsync'd to <host>, then loaded. The
always-on node needs no generator model.

**Rationale**: D9 (intermittent compute) + the local-first thesis — generation is a batch research job,
decoupled from the durable loop. Keeps <host> lean.

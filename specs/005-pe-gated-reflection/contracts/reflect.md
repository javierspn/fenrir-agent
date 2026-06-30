# Contract — `fenrir.reflect`

Internal module contract for the PE-gated meta-reflection step. No external/network surface; the
"contract" is the function signatures + invariants the loop and tests depend on.

## `tier(pe: float, escalated: bool, s: Settings) -> str`

Pure classifier. Returns exactly one of `"none" | "cheap" | "full"`.

- `escalated is True` → `"full"`  *(F1: any teacher-escalated task gets full reflection regardless of
  PE — this makes the full tier an exact superset of today's crystallize trigger
  `escalated OR pe>=CRYSTALLIZE_PE`, so SC-008 holds with no behavior gap)*
- else `pe < s.REFLECT_PE_LOW` → `"none"`
- else `s.REFLECT_PE_LOW <= pe < s.REFLECT_PE_HIGH` → `"cheap"`
- else `pe >= s.REFLECT_PE_HIGH` → `"full"`

Invariants (unit-tested): total + deterministic; `escalated` forces `full`; PE boundaries inclusive-up
(`LOW`→cheap, `HIGH`→full); no side effects; `REFLECT_PE_LOW <= REFLECT_PE_HIGH` enforced at settings
load. With default `REFLECT_PE_HIGH == CRYSTALLIZE_PE`, `{escalated} ∪ {pe>=HIGH}` == today's
crystallize predicate (verified-scratch wins) exactly.

## `reflect(conn, ctx: ReflectCtx) -> ReflectResult`

Called once per iteration in `core.run_iteration`, after the task UPDATE+commit, around crystallize,
before the episode write. Best-effort: **never raises into the loop** (catches internally, returns a
result with `outcome="none"` on error).

**`ReflectCtx`** (inputs, all already available in the loop):
`task_id, prediction_error, verdict, solve_path, escalated, is_eval, retrieval_skill_id,
problem_text, candidate_answer, solve_text, ground_truth`.

**`ReflectResult`** (return):
`tier: str`, `outcome: str | None` (`edited|created|none|suppressed`), `skill_id: uuid | None`,
`llm_called: bool`.

### Behavior contract

| condition | LLM call | writes | outcome |
|---|---|---|---|
| `tier=="none"` | no | `tasks.reflection_tier='none'` | `None` |
| `tier=="cheap"` | no | tasks col + `reflections` row (templated note) | `None` |
| `tier=="full"` & `is_eval` | no | tasks col + `reflections` row (tier only) | `none` (read-only, III) |
| `tier=="full"`, verified win, **matched skill** (`retrieval_skill_id` set) & `pe < REFLECT_EDIT_PE_MAX` | yes | new **skill version** + reflections + tasks col | `edited` |
| `tier=="full"`, verified win, **cold** (no matched skill) **or** `pe >= REFLECT_EDIT_PE_MAX` | yes | new **skill** (self-tested admit) + reflections + tasks col | `created` |
| `tier=="full"`, unverified/failed | yes | `reflections` row (lesson) + tasks col | `none` |
| `tier=="full"`, budget refused | no (proxy refused) | `reflections` row marked + tasks col | `suppressed` |

### Hard invariants (asserted by tests / analyze gate)

1. **IX** — at most one model call, via the budget proxy; proxy refusal → `suppressed`, never a breach.
2. **III** — `is_eval=True` ⇒ no skill write/edit, no consolidation (verified by querying skills after).
3. **II/IV** — `outcome ∈ {edited,created}` only when `verdict==SUCCEEDED`.
4. **VII** — `edited` writes a NEW skill version; the prior version still resolvable.
5. **VI** — only INSERTs / new-version rows; zero DELETE/UPDATE against episodes.
6. **FR-002/SC-002** — `none` ⇒ `llm_called==False` and no `reflections` row.
7. **FR-012** — any internal exception ⇒ caught, `outcome="none"`, loop continues.
8. **off-switch (SC-008)** — `REFLECT_ENABLED=False` (or thresholds unreachable) ⇒ behavior identical
   to today (crystallization still fires via the wrapped path; no new skill paths invoked beyond it).

## Settings (new, `fenrir/settings.py`)

| name | default | meaning |
|---|---|---|
| `REFLECT_ENABLED` | `True` | master switch (off = today's behavior) |
| `REFLECT_PE_LOW` | `0.3` | none/cheap boundary |
| `REFLECT_PE_HIGH` | `0.5` | cheap/full boundary; **= `CRYSTALLIZE_PE`** (R2) |
| `REFLECT_EDIT_PE_MAX` | `0.95` | within full: a **matched** skill with PE below ⇒ edit (new version); cold, or PE at/above (near-total surprise = a new method) ⇒ create. Default 0.95 (not 0.75) so the edit path is **reachable** on the live bimodal PE distribution where full-tier PE clusters at 0.9–1.0 (U3) |
| `REFLECT_MODEL_ROLE` | `"reflector"` | proxy role label for the one full-tier call (budget/metering) |

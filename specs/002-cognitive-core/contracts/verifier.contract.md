# Contract — sympy Verifier (ground-truth oracle)

**Module**: `fenrir/verify/sympy_oracle.py` (executes **inside** the sandbox)
**Constitution**: II (external ungameable verification), VIII (independent of proposer), I (math/sympy).

## Why it exists
The single source of truth for "did the system solve it". No textual match, no LLM-judge — symbolic
equivalence only. A task is "succeeded" only if this says so.

## Interface
```python
verify(candidate: str, ground_truth: str) -> Verdict
# Verdict ∈ { "succeeded", "failed", "unverified" }
```
- Parse both with sympy (`sympify` / domain-appropriate parsing).
- `succeeded` ← `simplify(candidate_expr - truth_expr) == 0` (or set/relational equivalence as the task
  type requires).
- `failed` ← parses on both sides but not equivalent.
- `unverified` ← sympy times out, cannot parse, or the task lacks a checkable ground truth.

## Verdict semantics (binding)
| Verdict | tasks.status | tasks.verified | counts as success? | eligible to crystallize? |
|---|---|---|---|---|
| succeeded | succeeded | true | yes | yes (if high PE) |
| failed | failed | false | no | no |
| unverified | unverified | false | **no** | **no** |

- A textually-plausible but mathematically-wrong answer → `failed`, regardless of model confidence
  (Acceptance US1.3, FR-013).
- `unverified` is **never** counted as success and **never** crystallized (Edge case; FR-015, SC-002).

## Guarantees / tests
- 100% of success verdicts trace to a sympy call — zero successes from textual/LLM-judge adjudication
  (SC-002). `test_verifier_independent.py`.
- Runs in the `--network none` sandbox, produced by a process independent of the solver (VIII).

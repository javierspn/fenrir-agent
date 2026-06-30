# Contract — `benchmark_loader/generate.py` (local generation host only)

Ported from the working overnight script. Runs on the generation host (LM Studio/Ollama + a local
open model), NOT on the always-on node. Produces JSONL; does NOT touch Postgres.

## CLI
```
python -m benchmark_loader.generate \
  --backend {lmstudio|ollama} --model <id> --per-family N \
  --out problems.jsonl [--min-steps 2] [--max-steps 5] [--cross-check]
```

## Behavior
- Round-robins the 10 families (`benchmark_loader/families.FAMILIES`) so cohorts interleave.
- For each candidate: prompt the local model → parse JSON (`_strip_fences` tolerant) → run the local
  validation gate → on accept, write one JSONL line `{question, answer, family, n_steps,
  source='qwen-gen'}`; dedup by normalized question.
- Bounds attempts per family (`--max-attempts-mult`); reports per-family tally + accept rate.
- `--cross-check` (default off, R6): request a SECOND independent `solution_code`; accept only if both
  derive the same canonical answer.

## Local validation gate (host-side, fast)
Rejects: missing keys; non-str question/code; forbidden tokens (`import os/sys`, `open(`, `exec(`,
`eval(`, `__`, `subprocess`, `socket`, `input(`); a question-number absent from the code (hidden
constant); execution crash/timeout (SIGALRM); answer not a clean integer/rational; answer leaked into
the question text. (Restricted-builtins + SIGALRM is acceptable HERE — trusted local host, off the
always-on node. The authoritative re-check happens in the loader's sandbox.)

## Invariants
1. Output is JSONL, one accepted problem per line, `source='qwen-gen'`.
2. The model's `answer` is recorded but is NOT authoritative — the loader re-derives it (II).
3. No DB writes, no network beyond the local model server.

---

# Contract — `benchmark_loader/families.py`

```python
FAMILIES: list[tuple[str, str]]          # (name, method-description) × 10
FAMILY_POOL: dict[str, str]              # family -> 'training'|'evaluation'|'transfer' (whole-family, III)
def pool_for(family: str) -> str         # FAMILY_POOL[family]; raises on unknown family
```
Invariant: every family in `FAMILIES` has exactly one pool in `FAMILY_POOL`; ≥1 family maps to
`transfer` (held-out, III); no family is split.

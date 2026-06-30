# Contract — `benchmark_loader/load_generated.py` (in-repo / <host>)

Ingests a generator JSONL into `benchmark_tasks`, deriving authoritative ground truth in the
`--network none` sandbox (II/X). Idempotent.

## CLI
```
python -m benchmark_loader.load_generated --in problems.jsonl [--require-cross-check]
```

## `load_generated(conn, path) -> LoadResult`

For each JSONL record:
1. Parse + shape-check (`question`, `solution_code`?/`answer`, `family`). *(Note: the JSONL carries
   `answer`; if the source also kept `solution_code`, re-derive from it; else the loader trusts only
   what it can re-verify — a record with no re-derivable solution is rejected. The generator SHOULD
   emit `solution_code` for re-verification; if only `answer` is present, the cross-check/verify path
   cannot run and the row is skipped.)*
2. **Derive ground truth in the sandbox** (R2): build the trusted harness (exec solution_code → print
   `answer` as JSON), `fenrir.sandbox.runner.run(program)`; on `timed_out`/no payload → reject.
3. **Confirm** `verdict(canonical_answer(produced), canonical_answer(claimed)) == SUCCEEDED`; on
   mismatch → reject (self-inconsistent, II).
4. Compute `problem_id = 'qwen-gen-' + sha256(normalize(question))[:16]`.
5. `pool = families.pool_for(family)` (III, whole-family).
6. `embedding = embed(question)` (0006 path); NULL-tolerant on failure (backfillable).
7. `INSERT INTO benchmark_tasks (benchmark, problem_id, pool, domain, content, ground_truth,
   contamination_safe, family, embedding) VALUES ('qwen-gen', …, TRUE, …) ON CONFLICT (problem_id)
   DO NOTHING`.

Returns `LoadResult{read, loaded, rejected, duplicates}`.

## Hard invariants (asserted by tests / analyze)
1. **II** — `ground_truth` is the sandbox-derived answer; a record whose claimed answer the sandbox
   disproves is rejected, never loaded.
2. **X** — model-generated code executes ONLY via `sandbox.run` (`--network none`), never `exec` in-process.
3. **III** — `pool` comes from `families.pool_for`; transfer-family rows never get `pool='training'`.
4. **VI / SC-004** — `ON CONFLICT DO NOTHING` on `problem_id` → reloading the same JSONL adds zero rows.
5. **SC-001** — every loaded row: `benchmark='qwen-gen'`, `contamination_safe=TRUE`, non-null `family`.
6. A sandbox failure / mismatch increments `rejected`, never aborts the whole load (best-effort batch).

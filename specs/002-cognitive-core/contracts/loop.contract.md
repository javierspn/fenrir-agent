# Contract — Loop Runner (one iteration)

**Module**: `fenrir/core.py` (orchestrator), `fenrir/predict.py`
**Constitution**: III, IV, II, VI. User Story 1 (P1) — the irreducible heartbeat.

## One iteration (single training task)

```
select_task()            # benchmark_tasks/tasks WHERE pool='training', unsolved/under-practiced
  → predict()            # FR-004: write predicted_confidence + predicted outcome BEFORE solving
  → retrieve()           # FR-007: lexical + vector; decide solve_path (retrieval vs scratch)
  → solve()              # FR-009: small model via proxy (model_class=small)
      → escalate?()      # FR-010: if confidence < ESCALATE_CONFIDENCE or cold or budget allows
                         #   → proxy model_class=frontier (claude-opus-4-8); set escalated=true
  → verify()             # FR-013: sympy in --network none sandbox → succeeded|failed|unverified
  → prediction_error()   # FR-005: verification delta + calibration gap → tasks/episode.prediction_error
  → write_episode()      # FR-016: additive short_term_memory row; salience computed
  → if PE ≥ CRYSTALLIZE_PE and succeeded: crystallize()   # US2; never on correctly-predicted (IV)
  → every N iters: consolidate()                          # US4
  → emit_metrics()       # tasks row carries cost/escalated/solve_path for the 3 curves
```

## Hard rules (asserted by tests)
- **Pool isolation**: `select_task()` reads only `pool='training'`; never reads or writes
  `pool='evaluation'` (FR-001, III). `test_pool_no_leak.py`.
- **Predict-before-solve**: `predicted_confidence` row written **before** the solve call; iteration
  fails loudly if solve runs first (FR-004). `test_loop_heartbeat.py`.
- **sympy-only success**: `status='succeeded'` only when the verifier says `succeeded` (FR-015).
- **Additive episode**: every attempt — success, failure, or unverified — writes exactly one
  `short_term_memory` episode; none are deleted (FR-016/017, VI).
- **PE gates crystallization**: no crystallization when the task was already predicted correctly
  (low PE) — SC-006. `test_no_crystallize_lowpe.py`.
- **≥30% benchmark-sourced** tasks across attempted set (FR-003) — no self-generated curriculum here.

## Independent test (US1)
Feed one known training task, run one iteration, assert: a `predicted_confidence` was written before
the attempt; the verdict came solely from sympy; a `short_term_memory` episode exists with a
`prediction_error`; no evaluation-pool row was read or written (SC-001).

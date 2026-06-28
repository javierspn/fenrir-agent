# Quickstart — Cognitive Core Loop (002)

Run one iteration end-to-end and validate the spec's success criteria. Assumes the **01-infra stack is
live on <host>** (Postgres+pgvector / Redis / Grafana / Ollama+models, bootstrapped, 14,973 benchmark
rows in disjoint 70/30 pools). This guide is a validation/run guide — implementation lives in
`tasks.md` and the modules under `fenrir/`.

## Prerequisites
- 01-infra stack healthy (`docker compose ps` all healthy; `system_state` has `bootstrapped`).
- Ollama reachable via `OLLAMA_HOST`; `qwen2.5` + `nomic-embed-text` present.
- A real `ANTHROPIC_API_KEY` on <host> (the 01-infra placeholder must be replaced before escalation —
  see BACKLOG open follow-up). Teacher model `claude-opus-4-8`.
- `budget_tracking` row for today exists with `daily_budget_usd` (default 2.00).

## 0. Apply the additive migration (human-confirmed — Constitution XII)
```bash
# review the SQL first, then:
python -m fenrir.db migrate          # applies 0003_cognitive_core.sql (idempotent)
# verify
psql "$DATABASE_URL" -c "\d tasks"   # solve_path, retrieval_skill_id present
psql "$DATABASE_URL" -c "\d short_term_memory"  # importance, retrieval_frequency present
psql "$DATABASE_URL" -c "select version,name from schema_migrations where version='0003';"
```

## 1. Build the sandbox image + start the proxy
```bash
docker build -f fenrir/sandbox/Dockerfile.sandbox -t fenrir-sandbox fenrir/sandbox/
# proxy comes up with the fenrir compose service (exposes :8080 on the internal network)
docker compose up -d fenrir
curl -s localhost:8080/healthz                      # proxy alive
```

## 2. Run ONE iteration (US1 — the heartbeat)
```bash
python -m fenrir.core --once
```
**Assert (SC-001):**
```sql
-- a prediction was written BEFORE the attempt
select predicted_confidence, prediction_error, solve_path, verified, escalated
  from tasks order by created_at desc limit 1;
-- an additive episode exists with a prediction error
select id, salience, prediction_error, importance, retrieval_frequency
  from short_term_memory order by created_at desc limit 1;
-- the evaluation pool was untouched
select count(*) from tasks t join benchmark_tasks b on b.problem_id = t.benchmark_id
  where b.pool = 'evaluation';            -- expect 0
```

## 3. Force a sympy verdict path (US1 — verifier independence, SC-002)
- Feed a known-answer task; confirm `status='succeeded'` only when sympy confirms.
- Feed a textually-plausible-but-wrong answer; confirm `status='failed'` regardless of confidence.
```bash
pytest tests/integration/test_loop_heartbeat.py tests/integration/test_verifier_independent.py
```

## 4. Crystallize + retrieve (US2, SC-003/006/009)
```bash
python -m fenrir.core --run 200          # a cohort large enough to hit high-PE solves
pytest tests/integration/test_crystallize_admit.py \
       tests/integration/test_no_crystallize_lowpe.py \
       tests/integration/test_retrieval_solvepath.py
```
**Assert:** library skills are `skill_kind='code'` with a `self_test`, `state='stable'` only after the
independent pass (SC-003); zero crystallizations on correctly-predicted tasks (SC-006); a second similar
task records `solve_path='retrieval'` (SC-009).

## 5. Escalation + budget cap (US3, SC-008)
```bash
pytest tests/integration/test_escalation_budget.py
```
**Assert:** a low-confidence task routes to `claude-opus-4-8` via the proxy and sets `escalated=true`;
with the daily cap exhausted, escalation is refused and `sum(cost_usd) ≤ daily_budget_usd`.

## 6. Consolidation (US4, SC-007)
```bash
python -m fenrir.consolidation.sleep --run
pytest tests/integration/test_consolidation_gate.py
```
**Assert:** episodes processed salience-descending; non-improving abstraction rejected by the
predictability gate (held-out **training** slice); zero source episodes hard-deleted.

## 7. Sandbox isolation (FR-011) + pool non-leak (FR-001)
```bash
pytest tests/integration/test_sandbox_isolation.py tests/integration/test_pool_no_leak.py
```

## 8. Dashboard (US5, SC-010)
Open Grafana → "Learning" dashboard. Confirm the **three curves** (cost/solved-task, escalation rate,
retrieval-vs-from-scratch share) render real values via the `grafana_ro` role, plus episode/skill
counts, pool occupancy, consolidation events, and the PE histogram — and that every accuracy panel
shows the **contamination caveat**.

## Full suite
```bash
pytest tests/integration -q
```
Expected: the new 9 suites green alongside the existing 01-infra suite. A **flat escalation curve** in
the dashboard is a valid, recorded **negative result** — not a test failure.

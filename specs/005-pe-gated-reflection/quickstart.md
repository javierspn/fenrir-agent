# Quickstart — validate PE-gated meta-reflection

Prereqs: stack up (`infra/docker-compose.yml`), migration `0007` applied
(`python -m fenrir.db migrate`, human-confirmed XII), Ollama reachable.

## 1. Tier boundaries (unit, no stack)

```bash
pytest tests/unit/test_reflect.py -q
```
Expect: `tier()` returns `none`/`cheap`/`full` at the `REFLECT_PE_LOW=0.3` / `REFLECT_PE_HIGH=0.5`
boundaries (inclusive-up); `none` ⇒ no LLM, no `reflections` row; settings reject `LOW > HIGH`.

## 2. Gate distribution over a cohort (integration)

```bash
FENRIR_STACK_UP=1 FENRIR_OLLAMA_UP=1 python -m fenrir.core --run 50
psql "$DB" -c "
SELECT reflection_tier, count(*),
       round(avg(prediction_error)::numeric,2) AS avg_pe
FROM tasks WHERE created_at::date = CURRENT_DATE AND is_eval=false
GROUP BY 1 ORDER BY 1;"
```
Expect (SC-001): `full` rows have high avg_pe, `none` rows low — tiers track PE, not a fixed fraction.

## 3. Edit-or-create payoff (SC-004)

```bash
psql "$DB" -c "
SELECT reflection_outcome, count(*) FROM tasks
WHERE reflection_tier='full' AND created_at::date=CURRENT_DATE
GROUP BY 1;"
```
Expect ≥1 `edited` or `created` over a cohort with high-PE verified wins; each `edited` row's
`reflection_skill_id` has a **new skill version** (prior retained, VII).

## 4. Budget suppression (SC-006, IX)

Set a tiny cap, run a cohort with high-PE tasks:
```bash
DAILY_BUDGET_USD=0.001 python -m fenrir.core --run 20
psql "$DB" -c "SELECT count(*) FROM tasks WHERE reflection_outcome='suppressed' AND created_at::date=CURRENT_DATE;"
```
Expect ≥1 `suppressed`; total spend ≤ cap (no breach).

## 5. is_eval read-only (SC-005, III)

Run an eval batch, then assert no skill mutation attributable to eval tasks:
```bash
psql "$DB" -c "
SELECT count(*) FROM tasks t JOIN reflections r ON r.task_id=t.id
WHERE t.is_eval=true AND r.outcome IN ('edited','created');"
```
Expect `0`.

## 6. Off-switch parity (SC-008)

```bash
REFLECT_ENABLED=false python -m fenrir.core --run 50
```
Expect verdict/throughput identical to pre-feature; crystallization still fires (wrapped path); no new
skill paths beyond it.

## Per-cohort measurement SQL (for the later dashboard cut, SC-001/007)

```sql
-- reflection tier mix per cohort (daily bucket = one nightly cohort)
SELECT date_trunc('day', created_at)::date AS cohort,
       count(*)                                            AS tasks,
       count(*) FILTER (WHERE reflection_tier='none')      AS none,
       count(*) FILTER (WHERE reflection_tier='cheap')     AS cheap,
       count(*) FILTER (WHERE reflection_tier='full')      AS full,
       count(*) FILTER (WHERE reflection_outcome='edited') AS edited,
       count(*) FILTER (WHERE reflection_outcome='created')AS created,
       count(*) FILTER (WHERE reflection_outcome='suppressed') AS suppressed,
       round(avg(prediction_error) FILTER (WHERE reflection_tier='full')::numeric,2) AS full_avg_pe
FROM tasks WHERE is_eval=false
GROUP BY 1 ORDER BY 1;
```
A cohort with no surprise renders as all-`none`/`cheap` with zero `full` — a valid recorded negative
(SC-007), not an error.
```

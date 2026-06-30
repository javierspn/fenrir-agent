# Quickstart — validate the family generator + by-family verdict

Prereqs: migration `0009` applied (`python -m fenrir.db migrate`, human-confirm XII); the
`fenrir-sandbox` image built; a local model server for generation (LM Studio/Ollama) on the
generation host.

## 1. Generate (local host or free cloud GPU — not the always-on node)

```bash
# smoke (30s)
python -m benchmark_loader.generate --backend lmstudio --model qwen2.5-14b-instruct \
    --per-family 2 --out smoke.jsonl
head smoke.jsonl    # expect {question, answer, solution_code, family, n_steps, source:"qwen-gen"}

# full batch (a few hours on a 14B Q4)
python -m benchmark_loader.generate --per-family 200 --out problems.jsonl   # 10 families x 200
# higher trust (2x cost): add --cross-check
```
Expect: stderr accept rate >30%; every line carries `solution_code` (R8) and a `family`.

## 2. Load into the pool (sandbox-verified, on <host>)

```bash
rsync problems.jsonl <host>:<home>/ragnarok/   # generation is off-node (R7)
python -m benchmark_loader.load_generated --in problems.jsonl
```
Expect (SC-001/002): every loaded row `benchmark='qwen-gen'`, `contamination_safe=TRUE`, non-null
`family`, `ground_truth` = the **sandbox-derived** answer. A record whose claimed answer the sandbox
disproves is rejected (II). Reload the same file → 0 new rows (idempotent, SC-004):

```bash
psql "$DB" -c "SELECT family, pool, count(*) FROM benchmark_tasks WHERE benchmark='qwen-gen'
               GROUP BY 1,2 ORDER BY 1;"
```
Confirm (SC-005): the reserved transfer family has `pool='transfer'` rows and **zero** `training`.

## 3. Run by-family cohorts + read the verdict

```bash
python -m fenrir.core --run 50   # the 004 curriculum will draw from the new family pool
```

```sql
-- by-family within-position verdict (the clean compounding test, R5/SC-006/007)
WITH fam AS (
  SELECT bt.family, t.escalated, t.retrieval_skill_id, t.retrieval_abstraction_id,
         row_number() OVER (PARTITION BY bt.family ORDER BY t.created_at) AS pos
  FROM tasks t JOIN benchmark_tasks bt ON bt.problem_id = t.benchmark_id
  WHERE bt.benchmark='qwen-gen' AND t.is_eval=false AND t.status <> 'in_progress')
SELECT family,
  round(100*avg(escalated::int) FILTER (WHERE pos=1),1)  AS escal_first,
  round(100*avg(escalated::int) FILTER (WHERE pos>1),1)  AS escal_rest,
  round(100*avg((retrieval_skill_id IS NOT NULL OR retrieval_abstraction_id IS NOT NULL)::int)
        FILTER (WHERE pos>1),1)                           AS reuse_rest,
  count(*) AS solved
FROM fam GROUP BY family ORDER BY family;
```
**Compounding within a family** ⇔ `escal_rest < escal_first` AND `reuse_rest > 0`. A family where
`escal_rest ≈ escal_first` is **flat = recall, a valid recorded negative** (SC-006/FR-010) — renders
plainly on the learning.json by-family panel; not an error.

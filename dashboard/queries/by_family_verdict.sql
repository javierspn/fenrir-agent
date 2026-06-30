-- by_family_verdict.sql — canonical within-family compounding verdict (006, D13).
-- Per qwen-gen family: escalation on the first solved member vs later members, and reuse on later
-- members. Compounding within a family ⇔ escal_rest < escal_first AND reuse_rest > 0.
-- A family where escal_rest ≈ escal_first is flat = recall, a valid recorded negative (FR-010).
-- Read-only (grafana_ro). Join is tasks.benchmark_id = benchmark_tasks.problem_id.
WITH fam AS (
  SELECT bt.family, t.escalated, t.retrieval_skill_id, t.retrieval_abstraction_id,
         row_number() OVER (PARTITION BY bt.family ORDER BY t.created_at) AS pos
  FROM tasks t
  JOIN benchmark_tasks bt ON bt.problem_id = t.benchmark_id
  WHERE bt.benchmark = 'qwen-gen' AND t.is_eval = false AND t.status <> 'in_progress'
)
SELECT family,
  count(*)                                                       AS solved,
  round(100*avg(escalated::int) FILTER (WHERE pos = 1), 1)       AS escal_first,
  round(100*avg(escalated::int) FILTER (WHERE pos > 1), 1)       AS escal_rest,
  round(100*avg((retrieval_skill_id IS NOT NULL
                 OR retrieval_abstraction_id IS NOT NULL)::int)
        FILTER (WHERE pos > 1), 1)                               AS reuse_rest
FROM fam
GROUP BY family
ORDER BY family;

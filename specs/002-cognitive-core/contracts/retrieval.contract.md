# Contract — Retrieval Selector (lexical + vector)

**Module**: `fenrir/memory/retrieval.py`
**Constitution**: XI (simple, not the deferred P2.5 multi-lane reranker). FR-007/008.

## Why it exists
Before solving, surface prior skills/episodes relevant to the task, using **both** lanes the substrate
already indexes. Prefer applying a verified skill over cold reasoning, and record which path was taken.

## Lanes (both run, results merged)
- **Lexical**: `ts_rank_cd(content_fts, plainto_tsquery($q))` over `short_term_memory` and
  `long_term_memory` and `skills` content_fts (GIN indexes from 01-infra).
- **Vector**: cosine over pgvector `embedding` (768-dim, `nomic-embed-text`), ivfflat index.

## Interface
```python
retrieve(task) -> Retrieved
# Retrieved: { skills: [SkillHit], episodes: [EpisodeHit], top_skill: SkillHit | None }
# *Hit carries similarity (cosine) and lexical rank.
```
- A skill is **applicable** when `cosine ≥ RETRIEVAL_SIM_FLOOR (0.80)` OR it tops the lexical lane.
- On retrieval, bump `retrieval_frequency` on the surfaced episode(s)/skill (feeds salience, FR-018).

## Solve-path decision (FR-008, SC-009)
- If an applicable **verified** skill exists → solve via **retrieval/skill-application**:
  `tasks.solve_path='retrieval'`, `tasks.retrieval_skill_id=<id>`, execute the skill in the sandbox
  (`kind=skill_apply`).
- Else → cold solve with the small model: `tasks.solve_path='scratch'`.

## Guarantees / tests
- Both lanes execute over the existing indexes (no new index except the held-out partial index).
- On a second exposure to a task similar to a crystallized one, the solve-path record is `retrieval`
  (SC-009). `test_retrieval_solvepath.py`.
- A retrieved skill that then fails verification on the current task → recorded as a negative episode;
  the retrieved skill's record is **not** corrupted (Edge case).

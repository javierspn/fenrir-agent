# Contract — Skill Crystallization

**Module**: `fenrir/skills/crystallize.py`, `fenrir/skills/admit.py`
**Constitution**: IV (PE-gated), VII (versioned), VIII (independent admission), II (verifiable). US2 (P1).

## Trigger
Only when a task was **solved + sympy-verified** AND `prediction_error ≥ CRYSTALLIZE_PE (0.5)`.
**Never** on a task the system already predicted correctly (low PE) — Constitution IV, SC-006.

## Candidate production (`crystallize.py`)
- Distill the verified solution into a reusable **skill = executable code + a `self_test`** (never free
  text) — `skill_kind='code'`, `self_test` populated (FR-022).
- Built via the crystallizer role through the proxy.

## Admission (`admit.py`) — independent pass (VIII)
1. Run the candidate's **code + self_test in the sandbox** (`kind=skill_selftest`, `--network none`),
   in a process independent of the one that produced it.
2. Re-solve the originating task with the candidate; require it to **reproduce the verified solution**.
3. **Admit only if both pass** → `state='stable'`. Otherwise **reject** — not added to the library
   (FR-023, Acceptance US2.2, SC-003).

## Versioning (VII, FR-024)
- Before modifying any existing skill, write a `skill_versions` row.
- Small PE → new **version** of the same skill.
- Large PE / conflicting skill → **new skill** + a `contradicts` edge in `graph_updates`
  (`relation_type='contradicts'`). Never silent overwrite (Edge case).

## Guarantees / tests (`test_crystallize_admit.py`, `test_no_crystallize_lowpe.py`)
- 100% of library-admitted skills passed the independent pass; zero free-text-only skills (SC-003).
- A candidate whose self_test fails on the independent pass is rejected (US2.2).
- Crystallization fires only on high-PE tasks; zero on correctly-predicted tasks (SC-006).
- On the next similar task, retrieval surfaces the skill and the solve is recorded as `retrieval`
  (SC-009 — see `retrieval.contract.md`).

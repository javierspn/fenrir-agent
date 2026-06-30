# Cross-artifact analysis — 005 PE-gated meta-reflection

`/speckit-analyze` over spec.md + plan.md + research.md + data-model.md + contracts/reflect.md +
quickstart.md + tasks.md (2026-06-30). No CRITICAL issues. 1 HIGH + 2 MEDIUM + 2 LOW found and
**resolved before `/speckit-implement`**.

| ID | Sev | Finding | Resolution |
|----|-----|---------|------------|
| F1 | HIGH | Gate was PE-only, but today's crystallize also fires on `escalated`-low-PE → those would crystallize today but get `cheap`/`none` under reflection = silent **SC-008** regression. `escalated` was in `ReflectCtx` but unused. | `tier()` now takes `escalated` and forces `full` whenever escalated, so `{escalated}∪{pe>=HIGH}` is an exact superset of today's crystallize predicate. Updated contract (`tier` sig), research R2, plan summary, spec FR-001, task T005 (test asserts the match). |
| F2 | MED | plan.md said "4 tunables" and omitted `REFLECT_EDIT_PE_MAX`; contract/research/tasks carried 5. | plan.md → "5 tunables" + listed `REFLECT_EDIT_PE_MAX`. |
| U3 | MED | Edit band `[0.5, 0.75)` sits in the empty PE valley (full-tier PE clusters 0.9–1.0) → edit path never fires in prod; every full task creates. | `REFLECT_EDIT_PE_MAX` default `0.75 → 0.95` so matched tasks at PE 0.9–0.95 → edit (reachable). Edit-vs-create now keyed on **matched skill** first. Updated contract, research R3, spec FR-005, task T011 (PE=0.92 reachability case). |
| A4 | LOW | Spec FR-005 said "moderate/large PE" without naming the controlling setting. | FR-005 now references `REFLECT_EDIT_PE_MAX` explicitly. |
| C5 | LOW | FR-008 (separation, VIII) mapped "by construction" with no asserting task. | T015 now asserts reflection writes no verdict/selection; coverage table updated. |

**Coverage after fixes**: 14/14 FR + 8/8 SC each have ≥1 asserting task. 0 CRITICAL, 0 duplication.
Constitution check (plan.md) unchanged — all 13 hold by construction. Ready for `/speckit-implement`.

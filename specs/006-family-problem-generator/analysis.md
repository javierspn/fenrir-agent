# Cross-artifact analysis — 006 family problem generator

`/speckit-analyze` over spec + plan + research + data-model + contracts + tasks (2026-06-30).
**No CRITICAL, no constitution-MUST violations.** 7 MEDIUM + LOW found; all resolved before implement.

| ID | Sev | Finding | Resolution |
|----|-----|---------|------------|
| I1 | MED | Tests-first violated — T006/T008 "must fail first" sit after their foundational impl (T003/T001). | Reworded: generate.py is a **port** and families.py is foundational, so T006/T008 *validate* (not fail-first TDD). Loader tests (T007/T010/T011) stay fail-first. |
| C1 | MED | FR-007 AS2 (generator≠teacher *identity*) untasked — T011 only proves the verifier decides. | T012 now also asserts the configured generation model/backend ≠ `settings.frontier_model`. |
| U1 | MED | FR-012 required resumable *generation* too, untasked. | Narrowed FR-012 to **load idempotency** (stable id + conflict-skip); generation is re-runnable (loader absorbs overlap); resumable-gen = nice-to-have. |
| U2 | MED | Edge case "unfillable family" (attempt cap + shortfall) untasked. | T003 note: the port carries over the per-family attempt cap + shortfall report (already in the Desktop script). |
| A1 | MED | The 10 families never enumerated in any artifact. | data-model.md now lists all 10 (extensible in code). |
| A2 | MED | Dual-check mitigation: two solutions can both diverge from prose + agree. | research R6 residual-gap note: catches code-bug agreement, not prose↔code; prose-grounded check is a future high-trust option. |
| I2 | MED | "0006" (migration, embedding) vs "006" (this feature) — collision risk. | Clarified "migration-0006" in data-model/refs. |
| U3 | LOW | Non-JSON/fenced parse tolerance untested. | Folded into T006. |
| I3 | LOW | FR-002 under-mapped (only T001). | Coverage line adds T003. |
| D1 | LOW | By-family SQL duplicated in data-model + quickstart. | Canonical = the committed `by_family_verdict.sql` (T014); docs reference it. |
| X1 | LOW | Generation host runs model code under restricted-builtins, not `--network none`. | research R1 residual-blast-radius note: trusted off-node host, static guards, nothing trusted until sandbox re-derivation (II). Documented carve-out, no spec change. |

**Coverage after fixes:** 12/12 FR + 8/8 SC each have ≥1 task; FR-007/FR-012 partials closed (C1/U1).
Constitution: 0 MUST violations; plan correctly omits V/VII/IX (no consolidation/skill-mutation/added
always-on cost). Ready for `/speckit-implement`.

"""DEFERRED — eval-bench sub-step (bootstrap step 5b). NOT built in 01-infra.

Builds the contamination-safe FROZEN eval set via procedural perturbation
(structurally-identical variants with sympy-re-derived ground truth) and/or
post-cutoff ingest — EVAL_PROTOCOL.md §7. Spec'd now, built when the eval harness
is stood up (spec Out of Scope; BACKLOG P4.5). EVAL_PROTOCOL M4 (transfer) and the
contamination-guard panel stay inactive until this ships.

This stub exists only to reserve the module path; implementing it is out of scope
for feature 001-infra-stack.
"""
from __future__ import annotations


def build_perturbed_set(*args, **kwargs):
    raise NotImplementedError(
        "eval-bench sub-step (bootstrap 5b) — see EVAL_PROTOCOL.md §7 / BACKLOG P4.5"
    )

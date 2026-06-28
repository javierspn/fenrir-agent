# Fenrir — a cheap, compounding, self-improving loop for verifiable domains

Fenrir is a research pilot in **accumulative machine learning**: a small, locally-run model that
gets better at a verifiable domain over time by building an external memory and crystallizing
**verified, executable skills** — leaning on an expensive "teacher" model *less and less*.

**The deliverable is the measurement, not the accuracy.** The whole system is instrumented to
prove — or honestly falsify — one hypothesis: *how far do external memory + crystallized skills
substitute for model scale on mathematics, with falling dependence on a frontier teacher?* A flat
"escalation rate" curve (recall, not compounding) is a **valid negative result**, not a bug.

## The loop (one task)

```
predict (confidence, before solving)
  → retrieve prior skills/episodes (lexical + vector)
  → solve with the small owned model
  → escalate to the frontier teacher ONLY when stuck (budget-governed)
  → verify with an ungameable oracle (sympy) in a network-isolated sandbox
  → measure prediction error (surprise)
  → store the attempt as an additive episode
  → crystallize a verified, self-tested skill on a surprising win
  → consolidate ("sleep") in salience order behind a predictability gate
```

## Principles (the safety net)

- **Ungameable verification.** Every autonomous "success" is confirmed by an external oracle
  (sympy symbolic equivalence for the math pilot) — never textual match or an LLM judge. Untrusted
  code runs in a `--network none` sandbox.
- **Prediction error gates learning.** Effort, memory, and crystallization concentrate where the
  system was *surprised* — not uniformly after every task.
- **Additive memory.** Episodes are never hard-deleted; consolidation writes new abstractions and
  only keeps a generalization if it improves held-out performance (no overfitting).
- **Skills are verifiable.** A skill is executable code + a self-test, admitted to the library only
  after an independent pass runs it and reproduces the verified solution.
- **Hard budget cap.** A frontier teacher is called only when stuck, under an inviolable daily
  spending cap.

## Layout

| Path | What |
|---|---|
| `fenrir/core.py` | the loop runner (one task per iteration) |
| `fenrir/memory/` | retrieval (lexical + vector), salience, additive episodes |
| `fenrir/llm/` | the budget-governed proxy (single egress for all model calls) |
| `fenrir/verify/` | the sympy oracle |
| `fenrir/sandbox/` | the `--network none` execution sandbox |
| `fenrir/skills/` | crystallization + independent admission |
| `fenrir/consolidation/` | regulated "sleep" with a predictability gate |
| `dashboard/` | Grafana panels: the three falsifiable curves + cost/tokens |
| `specs/` | the spec-driven design (spec → plan → tasks → contracts) |

## Memory, the hippocampal way

Consolidation follows a two-stage model (significance bookmark → competitive replay):

- **Bookmark at encoding** — each attempt gets one significance score from *surprise* ×
  *value* (verified? teacher-taught? yielded a skill?) × *use*.
- **Passive forgetting** — significance decays with age unless re-accessed; anchored ground
  truth never fades. Forgetting is reversible by renewed relevance.
- **Competitive replay** — "sleep" clusters similar episodes and replays them in proportion to
  significance, merging each cluster into **one** strengthening abstraction (generalization, not
  accumulation), behind a per-cluster predictability gate.

The headline instrument is the **reuse curve**: are consolidated abstractions actually applied
to later tasks? Rising = compounding; flat = honest negative result.

## Status

Math pilot, single node, running. The loop solves real GSM8K + MATH problems, verifies them
symbolically, crystallizes teacher-taught wins into self-tested skills, and consolidates by
competitive replay. The open question under measurement: does **skill/abstraction reuse** rise
while **teacher-escalation** and **cost-per-solved** fall — together?

## Support the experiment

Fenrir runs on a single self-hosted node plus a paid frontier teacher under a hard daily cap.
Donations go directly to compute:

- **Frontier API credits** — more teacher calls = faster learning while the skill library is thin.
- **Local inference hardware** — e.g. a Mac Mini would let the small-model loop run more often,
  cheaper, and lean on the paid teacher *less* (which is the whole point).

If that's interesting, see the repo's **Sponsor** button (`.github/FUNDING.yml`).

## License & ethics

Apache-2.0 (see `LICENSE`). Please also read [`ETHICS.md`](ETHICS.md): Fenrir's autonomous loop is
intended **only for domains with a cheap, ungameable verifier** (math, code, digital logic).
Unverifiable / high-stakes domains (medicine, law, finance, strategy) are **decision-support only**
— a human owns the verifier. Don't run it autonomously where "looking correct" can diverge from
"being correct."

*This is a public mirror of a private research repo, exported on a cadence; infrastructure and
operational specifics are intentionally omitted.*

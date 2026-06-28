# Ethics & Intended Use

Fenrir is released under Apache-2.0, which places **no legal restriction** on use. This
document is therefore a statement of **intent and norms**, not an enforceable clause. We ask
that you honor it.

## What Fenrir is

A research pilot in *cheap, compounding self-improvement on **verifiable** domains*. It gets
better at a task over time by accumulating an external memory and crystallizing **verified,
executable skills**, leaning on an expensive teacher model less and less. The reference domain
is mathematics, where every autonomous "success" is confirmed by an ungameable oracle (symbolic
equivalence via `sympy`) inside a network-isolated sandbox.

## The boundary we hold (and ask you to hold)

The system is designed around one safety line:

> **Autonomy is permitted only where verification is cheap and hard to game.**

- **Verifiable domains** (math → code → digital logic — anything with a cheap, ungameable
  checker) may run autonomously, because a wrong answer is *caught*, not trusted.
- **Unverifiable / high-stakes domains** — medicine, law, finance, strategy, anything where
  correctness is contested or a human bears the consequence — must be **decision-support only**:
  a human owns the verifier and the decision. Fenrir must **never** be wired to act autonomously
  there. In those settings, reward-hacking is not a quality bug — it is a safety failure.

## Please do not

- Deploy the autonomous loop in a domain that lacks a cheap, ungameable verifier.
- Remove or weaken the verification oracle, the sandbox isolation, or the budget cap and then
  run it unattended.
- Point the self-improvement loop at objectives where "looking correct" diverges from "being
  correct" without a human in the loop.
- Use it to generate or optimize content intended to deceive, manipulate, surveil, or harm.

## Please do

- Keep the verifier ungameable and external. The whole design rests on it.
- Treat a flat learning curve as an **honest negative result** worth reporting — not something
  to massage away. The value of this project is the *measurement*.
- Extend it to new **verifiable** domains, and share what you learn.

This boundary mirrors the project's own design record (decision **D7**: *autonomous only where
verification is cheap; decision-support everywhere else*). If you build on Fenrir, carry it
forward.

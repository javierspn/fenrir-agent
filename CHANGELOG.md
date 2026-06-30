# Changelog

All notable changes to Fenrir. This file is the **canonical** changelog (private repo) and ships
verbatim to the public mirror (`fenrir-agent`) on each export, so both repos always match. The
version is single-sourced in `pyproject.toml`. This is a research pilot (0.x): each **minor** is a
feature slice; **patch** is fixes/docs between slices. Full rationale lives in `BACKLOG.md` (decision
log) + git history.

The format follows [Keep a Changelog](https://keepachangelog.com).

## [0.6.0] — 2026-06-30

### Added
- **006 — contamination-safe, family-structured problem generator + by-family reuse verdict.** A small
  open model writes problems + sympy solution code; sympy executes to derive ground truth (II/VIII —
  the model is never trusted for the answer). 10 solution-method families enable the within-family
  reuse test (does escalation drop after a family's first member; is its skill reused on 2..N).
  `benchmark_loader/{generate,load_generated,families}.py`, migration `0009` (`benchmark_tasks.family`),
  by-family verdict SQL + dashboard panel.
- **005 — PE-gated meta-reflection.** Reflection effort is tiered by prediction-error magnitude
  (none / cheap / full); high-surprise events feed skill edit-or-create. Migration `0007`.
- **Acknowledgments** section (Kaggle free GPU + open tooling).

### Changed
- **Ethics / Constitution 1.2.0 (D7).** Autonomy boundary refined into graduated verifier tiers
  (exact-formal → autonomous; coverage-bounded → autonomous + gate; approximate/model → decision-support)
  with a ladder cutoff (math/code/HDL autonomous; SPICE/FEA + high-stakes = decision-support).

### Notes
- Decision log additions: **D11** (neuroscience-gap roadmap), **D12** (CORAL/ProcMEM review),
  **D13** (the family generator).

## [0.1.0–0.5.0] — 2026-06 (pre-changelog)

- **001** infra stack · **002** cognitive core (predict→retrieve→solve→escalate→verify→episode→
  crystallize) · **003** memory-consolidation replay (bookmark/decay/competitive-replay) ·
  **004** feasibility-gated curriculum (skill-adjacent task bias). Live on the always-on node;
  measured via the Grafana "Learning" / "Are we learning?" dashboards. (History in `BACKLOG.md` + git.)

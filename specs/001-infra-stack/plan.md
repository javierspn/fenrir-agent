# Implementation Plan: Infrastructure Stack & Bootstrap (01-infra)

**Branch**: `001-infra-stack` | **Date**: 2026-06-24 | **Last updated**: 2026-06-26 (D5–D10, constitution v1.1.0) | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-infra-stack/spec.md`

## Summary

Stand up Fenrir's data layer and an idempotent bootstrap before any cognitive code:
a Docker Compose stack of **postgres (pgvector)**, **redis**, **grafana**, and a one-shot
**benchmark-loader**, plus versioned SQL migrations that create the full §13 schema with
the D1–D4 columns **and the D5/D6 substrate columns** (`content_fts` tsvector+GIN on both
memory tables for the §5 lexical lane; `skill_kind`+`self_test` on `skills` for verified-code
skills), and a Python bootstrap that seeds non-decaying math anchors, partitions
disjoint train/eval benchmark pools, and marks the system bootstrapped. Neo4j is **not**
in the stack (constitution XI / D4). The schema is **additive** — no path hard-deletes a
source episode (constitution VI / D1).

## Technical Context

**Language/Version**: Python 3.12 (bootstrap + benchmark-loader only; no cognitive code)

**Primary Dependencies**: Docker Compose; pgvector/pgvector:pg16; redis:7-alpine;
grafana/grafana:11.4.0 (pinned major — never `:latest`, reproducibility/FR-001); `psycopg[binary]`
(Postgres client), `httpx` (Ollama pulls, dataset downloads), `datasets`/`huggingface-hub`
(benchmark fetch), `pydantic-settings` (fail-fast env validation), `sympy` (eval-bench sub-step,
deferred). Migration runner: lightweight in-house ordered-SQL applier (no Alembic — keeps
migrations as plain reviewable `.sql`, constitution VII intent).

**Local models (via `OLLAMA_HOST`, research R8)**: reasoning `qwen2.5` + `llama3.1`; embedding
`nomic-embed-text` (768-dim, R3). Bootstrap pulls these; ids resolved here per spec Assumption.

**Storage**: PostgreSQL 16 + pgvector (embeddings `vector(768)`, ivfflat cosine indexes);
Redis 7 (embedding cache TTL 30d + budget counters; context cache is cognitive-phase, out of
scope here); named volumes `postgres_data`, `redis_data`, `grafana_data`.

**Testing**: pytest + testcontainers (or compose-up in CI) for schema/idempotency/anchor
integration tests; `psql`-level assertions for column/index presence.

**Target Platform**: Single Linux host (<host> primary, 32GB RAM / 12GB VRAM). Ollama runs
**natively on the host** (not in compose) for GPU access; reached via `OLLAMA_HOST`.

**Project Type**: Infrastructure + thin Python bootstrap package (single project).

**Performance Goals**: Not throughput-bound. Targets: clean `up` to all-healthy in one
attempt; bootstrap second-run is a true no-op; migrations apply in seconds.

**Constraints**: Idempotent everywhere; fail-fast on missing env; no destructive deletes
in schema/triggers; anchors never decay; train/eval pools disjoint; daily budget row
writable from day one; math-pilot scope only. **Power-loss-safe (D10)**: Postgres `fsync`/
`synchronous_commit` ON (never disabled); redis disposable (budget source-of-truth in Postgres);
`restart: unless-stopped` on all long-running services; nightly `pg_dump` to a separate location;
`postgres_data` on local fsync-honoring disk.

**Scale/Scope**: Single operator, single node. **14 tables** (see data-model.md, incl. `eval_runs`,
D8), ~50–100 anchors, ≥20 seeded relations, math benchmark datasets (GSM8K, MATH; Project Euler
optional) partitioned 70/30 (±5pp).

## Constitution Check

*GATE: must pass before Phase 0. Re-checked after Phase 1.*

| Principle | Relevance to this feature | Status |
|---|---|---|
| I. Math-only pilot | Seed only math anchors; load only math benchmarks (FR-014/016/022) | ✅ PASS |
| II. Symbolic verification | N/A here (no task execution); `ground_truth` column provisioned for later | ✅ N/A |
| III. Eval pool never trained on | Partition disjoint pools; `benchmark_tasks.pool` enforced (FR-016/SC-005) | ✅ PASS |
| IV. PE gates learning | Provide the columns it needs: `prediction_error`, `salience` (FR-006/007/008) | ✅ PASS (schema only) |
| V. Regulated consolidation | Salience-ordered index provisioned; no consolidation logic here | ✅ PASS (schema only) |
| VI. Episodes additive (D1) | No `ON DELETE CASCADE` to episodes; no delete path; guard + comment (FR-010/SC-007) | ✅ PASS |
| VII. Skills versioned | `skill_versions` table created; no mutation logic yet | ✅ PASS |
| VIII. Learner/judge separation | N/A (no LLM calls in infra) | ✅ N/A |
| IX. Daily budget hard cap | `budget_tracking` created + writable day one (FR-011) | ✅ PASS |
| X. Sandbox network isolation | N/A (no sandboxes here); compose networks scoped conservatively | ✅ N/A |
| XI. Scope discipline / no Neo4j (D4) | Zero graph-DB services; relations seeded in Postgres (FR-015/021/SC-007) | ✅ PASS |
| XII. Human-in-loop on self-mod | Migrations are reviewed plain SQL; bootstrap is read-then-write-once | ✅ PASS |
| XIII. Autonomous only where verification cheap/ungameable (D7) | No autonomous learning in infra; decision-support boundary is a later-domain concern | ✅ N/A |

**Gate result: PASS — no violations, Complexity Tracking left empty.**

## Project Structure

### Documentation (this feature)

```text
specs/001-infra-stack/
├── plan.md              # This file
├── research.md          # Phase 0 — tech decisions
├── data-model.md        # Phase 1 — schema entities + columns
├── quickstart.md        # Phase 1 — bring-up + validation guide
├── contracts/           # Phase 1 — migration + bootstrap + env contracts
│   ├── schema.contract.md
│   ├── bootstrap.contract.md
│   └── env.contract.md
└── tasks.md             # Phase 2 (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
infra/
├── docker-compose.yml          # postgres, redis, grafana, benchmark-loader (NO neo4j)
├── .env.example                # DB_PASSWORD, GRAFANA_DB_RO_PASSWORD, GRAFANA_PASSWORD,
│                               #   ANTHROPIC_API_KEY, OLLAMA_HOST, OWNER_TELEGRAM_CHAT_ID
├── migrations/
│   └── 0001_baseline_schema.sql    # all 14 tables + D1-D4 + D5/D6 columns (content_fts, skill_kind, self_test) + indexes + system_state + schema_migrations + grafana_ro read-only role; anchors+relations seeded by bootstrap from seed files
├── seeds/
│   ├── anchors_math.yaml           # 50-100 invariant math facts
│   └── relations_seed.yaml         # obvious starting relations (Postgres, no graph)
└── backup/
    └── pg_backup.sh                # D10: nightly pg_dump to a separate disk/host (cron/systemd timer)

fenrir/                         # THIN package — bootstrap only, no cognitive code
├── __init__.py
├── settings.py                 # pydantic-settings; fail-fast env validation
├── db.py                       # psycopg connection + ordered migration applier
└── bootstrap/
    ├── __init__.py
    ├── __main__.py             # `python -m fenrir.bootstrap` entrypoint (idempotent)
    ├── anchors.py              # seed anchors (is_anchor, strength=1.0, decay_rate=0)
    ├── relations.py            # seed obvious relations in Postgres
    └── models.py               # pull Ollama models via OLLAMA_HOST

benchmark_loader/               # one-shot container image
├── Dockerfile
├── load.py                     # download + index + partition train=0.7/eval=0.3 (disjoint)
├── perturb.py                  # D8: contamination-safe variants (sympy-re-derived ground truth) — EVAL_PROTOCOL.md §7
└── templates/                  # curated parametric problem templates (slots + answer_expr) for perturb.py

dashboard/
└── provisioning/
    ├── datasources/postgres.yaml   # connects as grafana_ro (read-only; GRAFANA_DB_RO_PASSWORD)
    └── dashboards/             # JSON dashboards (panels minimal for now)

tests/
├── integration/
│   ├── test_schema.py          # all tables/columns/indexes exist
│   ├── test_idempotency.py     # bootstrap 2nd run = no row changes
│   ├── test_anchors.py         # 50-100 anchors, never decay
│   ├── test_pools_disjoint.py  # no problem in both pools + 70/30 ±5pp (SC-005)
│   ├── test_no_episode_delete.py  # no cascade/path deletes episodes
│   ├── test_models_available.py   # required models respond via OLLAMA_HOST (SC-011)
│   ├── test_grafana_ro_readonly.py # grafana_ro SELECTs, writes rejected (SC-012)
│   ├── test_power_loss.py         # hard-kill mid-write → committed rows intact, no double-count (SC-010)
│   ├── test_backup_restore.py     # pg_backup artifact restores to identical counts (SC-009)
│   ├── test_restart_persist.py    # compose restart preserves data + healthy (SC-001/006)
│   ├── test_env_failfast.py       # missing var → fast named failure (SC-008)
│   ├── test_relations_seed.py     # ≥20 bootstrap_seed relations, idempotent (FR-015)
│   └── test_migrations.py         # apply/no-op/new-only (US3)
└── conftest.py                 # compose-up / testcontainers fixture
```

**Structure Decision**: Single-project infra layout per PROJECT_RAGNAROK.md §15. A
`fenrir/` package exists but is intentionally **thin** — only `settings`, `db`, and
`bootstrap`. Cognitive modules (`core.py`, `memory/`, `consolidation/`, `llm/`,
`sandbox/`) are explicitly NOT created in this feature.

## Complexity Tracking

> No constitution violations — section intentionally empty.

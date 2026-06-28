# Phase 0 Research: 01-infra

All Technical Context unknowns resolved. No remaining NEEDS CLARIFICATION.

## R1 — Migration runner: plain ordered SQL vs Alembic

- **Decision**: In-house ordered-`.sql` applier tracked in a `schema_migrations` table.
  Files `NNNN_name.sql` applied in lexical order inside one transaction each; applied
  versions recorded; re-apply is a no-op.
- **Rationale**: Constitution VII wants reviewable, append-only schema history. Plain SQL
  is the most auditable artifact; "never edit existing migration" is a social + CI rule.
  Avoids Alembic's autogenerate (which tempts in-place edits and obscures diffs).
- **Alternatives**: Alembic (heavier, Python-defined schema, autogen drift); Flyway/Sqitch
  (JVM/Perl runtime — extra dependency for a solo Python stack).

## R2 — pgvector index type: ivfflat vs hnsw

- **Decision**: `ivfflat` with `vector_cosine_ops` on the three `vector(768)` columns, as
  specified in §13. Lists tuned later when data exists.
- **Rationale**: Matches the master design; ivfflat is adequate at pilot scale and cheaper
  to build. HNSW is a later optimization once recall/latency is measured on real volume.
- **Alternatives**: HNSW (better recall/latency, higher memory + build cost — premature now,
  constitution XI); no index (full scan — fine for tiny data but we want the index present
  for SC-002 verification).
- **Note**: ivfflat needs data to train lists; on an empty table the index exists but is
  trivial. Acceptable — correctness now, tuning later.

## R2b — Lexical retrieval substrate (D5): generated tsvector + GIN

- **Decision**: Both memory tables get `content_fts tsvector GENERATED ALWAYS AS
  (to_tsvector('simple', content)) STORED` + a `gin(content_fts)` index. `'simple'` config
  (no stemming) is chosen to preserve math tokens, identifiers, and theorem names.
- **Rationale**: substrate for the §5 parallel-convergent selector's BM25-style lexical lane
  (D5). A **generated** column auto-populates from `content` — **no bootstrap seeding logic
  needed**, seeded anchors get their `content_fts` for free on insert. Ships now; the query
  lane/fusion/rerank are cognitive-phase.
- **Alternatives**: trigger-maintained tsvector column (more moving parts); ParadeDB/pg_search
  for true BM25 (extra extension — premature, constitution XI; `ts_rank_cd` is adequate at
  pilot scale).

## R12 — Power-loss durability (D10)

- **Decision**: Postgres is the only durability-critical store — keep `fsync=on` +
  `synchronous_commit=on` (defaults); committed tx + WAL replay survive a power cut. Migrations are
  one-transaction-each + idempotent (`schema_migrations`), so a cut mid-migration rolls back and
  re-applies. Redis = cache + fast counters only, `appendonly yes`/`appendfsync everysec` as
  insurance, **budget source-of-truth in Postgres `budget_tracking`** (rehydrated on restart) so a
  redis wipe loses nothing durable. All long-running services `restart: unless-stopped` (auto-boot).
  Nightly `pg_dump` to a separate disk/host for corruption/disk-failure/fat-finger (not power-loss).
- **Rationale**: FR-002a/002b. ACID already gives power-loss safety for free *if* fsync is honored;
  the work is (a) not breaking it, (b) keeping nothing durability-critical only in redis, (c)
  auto-restart, (d) a backup for the failure classes WAL doesn't cover.
- **Alternatives**: redis as a durable store (rejected — wrong tool, AOF still risks loss; Postgres
  is the ACID home); `synchronous_commit=off` for speed (rejected — trades the exact guarantee we
  need); WAL archiving / PITR (deferred — nightly `pg_dump` is enough at pilot scale, constitution XI).
- **Caveat**: the `postgres_data` volume MUST be on local disk that honors `fsync` — not a network/
  overlay mount that lies about flush, or ACID is void.

## R11 — Skills as verified executable code (D6): `skill_kind` + `self_test`

- **Decision**: `skills` gains `skill_kind TEXT DEFAULT 'code'` (`'code'`|`'text'`) and
  `self_test TEXT` (nullable). Columns only in this feature; no verification logic.
- **Rationale**: substrate for Voyager-style verified-code skills (D6) — a skill crystallizes
  later only if its `self_test` passes (§3). Bootstrap does **not** seed `skills`, so there is
  zero bootstrap impact; the columns simply exist for the cognitive phase.
- **Alternatives**: defer the columns to a later migration — rejected; they are cheap, the
  table is already in baseline, and adding now avoids a near-term migration.

## R3 — Embedding dimensionality + model

- **Decision**: `vector(768)`, embeddings from `nomic-embed-text` via Ollama.
- **Rationale**: 768 is fixed in §13 and is nomic-embed-text's native dim. Local, free,
  deterministic-cacheable (Redis embedding cache, §10.3).
- **Alternatives**: 1536 (OpenAI-style) — rejected, not local and wrong dim for the schema.

## R4 — Anchor "never decays" enforcement

- **Decision**: Two-layer guard — `is_anchor BOOLEAN` + `decay_rate = 0` on anchor rows,
  AND every future decay query MUST filter `WHERE is_anchor = FALSE`. The seed sets both.
- **Rationale**: Defense in depth. `decay_rate=0` makes the math a no-op even if a decay
  job forgets the filter; the `is_anchor` filter is the explicit contract. This feature
  only seeds; the filter obligation is documented for the consolidation feature.
- **Alternatives**: trigger preventing UPDATE of anchor strength (heavier; deferred — a
  comment + the two-layer guard is enough for infra).

## R5 — Additive episodes: preventing destructive deletes (D1)

- **Decision**: (a) No foreign key from any table to `short_term_memory` uses
  `ON DELETE CASCADE`; references that exist are `ON DELETE SET NULL` or plain. (b) No
  migration or trigger issues `DELETE FROM short_term_memory`. (c) A header comment in the
  baseline migration states the D1 invariant. (d) An integration test asserts no cascade
  path reaches episodes.
- **Rationale**: Constitution VI is a hard gate; enforce structurally, not by convention.
- **Alternatives**: a `BEFORE DELETE` trigger that raises — considered as belt-and-braces;
  deferred to avoid blocking legitimate future archival tooling. Revisit if a delete path
  ever appears.

## R6 — Idempotency strategy for bootstrap

- **Decision**: Global guard keys on the **`system_state('bootstrapped')` marker** (set only at the
  final step) → `exit 0` if present. **Not** a `long_term_memory` row count — a partial run leaves
  rows but no marker and MUST resume. Plus per-section idempotency: anchors via
  `INSERT ... ON CONFLICT (natural_key) DO NOTHING`; relations via `ON CONFLICT (from_node,
  relation_type, to_node) DO NOTHING`; benchmark partition keyed by deterministic problem id + pool;
  `system_state` upsert.
- **Rationale**: FR-012/017/018 require both a fast global no-op AND resumability after a
  partial/interrupted run. A row-count guard fails the second requirement: a crash after anchors but
  before benchmarks leaves `long_term_memory` non-empty, so a re-run would short-circuit and never
  load benchmarks. The marker is the only state set after *all* sections succeed, so it is the
  correct completion signal; per-section guards make the resume path duplication-free.
- **Alternatives**: row-count / "store non-empty" global guard — **rejected** (strands an interrupted
  first run, the exact bug above). Only per-section guards, no global marker — works but re-scans
  every section on each run; the marker gives the fast no-op too.

## R7 — Benchmark partition: disjoint + deterministic

- **Decision**: Hash each problem's stable id; assign to train if `hash % 100 < 70` else
  eval. Deterministic → re-runs reproduce the same split → idempotent and disjoint by
  construction. Record `pool` on each row.
- **Rationale**: Constitution III (no leakage) + FR-018 idempotency. A deterministic hash
  split needs no stored RNG seed and never reshuffles an existing row.
- **Alternatives**: random shuffle with stored seed (works but adds state); per-dataset
  predefined splits where they exist (use upstream split when provided, else hash).

## R8 — Ollama outside compose

- **Decision**: Ollama runs natively on the host; bootstrap reaches it at `OLLAMA_HOST`
  (default `http://host.docker.internal:11434`) and pulls `qwen2.5`, `llama3.1`,
  `nomic-embed-text`. Not a compose service.
- **Rationale**: §12 — GPU access requires native install. Pulls are idempotent (Ollama
  skips already-present models).
- **Alternatives**: Ollama-in-Docker (loses GPU passthrough simplicity on this host).

## R9 — Fail-fast configuration

- **Decision**: `pydantic-settings` BaseSettings loads the 5 required vars; missing/empty
  → raise at startup with the variable name. `.env.example` lists all five, no real values.
- **Rationale**: FR-019/020, SC-008, edge case "missing/invalid .env".
- **Alternatives**: ad-hoc `os.environ[...]` (less clear errors); dotenv-only (no validation).

## R10 — Grafana provisioning + read-only DB role

- **Decision**: The baseline migration creates a dedicated `grafana_ro` Postgres role —
  `GRANT SELECT` only, plus `ALTER DEFAULT PRIVILEGES … GRANT SELECT` so future tables stay
  readable — with its own password (`GRAFANA_DB_RO_PASSWORD`). The datasource
  (`dashboard/provisioning/datasources/postgres.yaml`) connects as `grafana_ro`, never the owning
  role. Dashboards as JSON under `dashboard/provisioning/dashboards/`. Panels minimal for now
  (existence + connection is the SC-001/FR-004 requirement; rich panels are later).
- **Rationale**: FR-004a — "read-only datasource" must be enforced by DB privileges, not just
  Grafana config. A leaked dashboard credential then cannot mutate state. Keeps dashboards
  versioned (§12) without over-investing before metrics flow.
- **Alternatives**: connect as the owning role and trust Grafana to issue only reads (rejected —
  not enforced, a write path exists); manual dashboard creation (not reproducible — rejected).

## R13 — Bootstrap/loader Python dependencies

- **Decision**: `psycopg[binary]` (Postgres client), `httpx` (Ollama pulls + dataset downloads
  over HTTP), `datasets`/`huggingface-hub` (benchmark fetch), `pydantic-settings` (fail-fast env),
  `sympy` (perturb.py re-derived ground truth, eval-bench sub-step). Tests: `pytest` +
  `testcontainers` (or compose-up in CI).
- **Rationale**: smallest set that covers HTTP, HF dataset fetch, typed env validation, and
  symbolic ground truth. All are standard, actively maintained, pure-Python-friendly.
- **Alternatives**: `requests` (sync-only — `httpx` matches the async-friendly cognitive phase);
  raw `os.environ` (no validation — R9 rejected it); Alembic for migrations (R1 rejected).

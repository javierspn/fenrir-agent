# Data Model — 003 Memory Consolidation Replay (Phase 1)

This feature is **schema-light by design**: A and C use only columns that already exist on
the live <host> schema; B adds exactly one nullable column. Below, each entity lists the
fields this feature reads/writes and the (one) field it adds.

---

## short_term_memory (Episode) — existing table

| Field | Type | Used by | Role in this feature |
|---|---|---|---|
| `id` | uuid | A/B/C | episode identity; member of `long_term_memory.source_memories` |
| `content` | text | C | merged into the abstraction text |
| `embedding` | vector | C | clustering by cosine similarity (existing pgvector) |
| `created_at` | timestamptz | B | decay age fallback when never reactivated |
| `prediction_error` | double precision | A | **surprise** factor of significance (unchanged) |
| `importance` | double precision | A | now holds the live **value** signal (was inert 1.0) |
| `retrieval_count` | integer | A | **use** factor `(count+1)` |
| `salience` | double precision | A/B/C | the single stored bookmark = PE × value × use |
| `consolidation_status` | text | C | `raw` → candidate; set `consolidated` after merge |
| `consolidated_at` | timestamptz | C | stamped on consolidation |
| **`last_reactivated_at`** | **timestamptz NULL** | **B (NEW)** | reactivation clock for decay; NULL ⇒ use `created_at` |

**Added field (migration 0004, the only schema change):**
`ALTER TABLE short_term_memory ADD COLUMN last_reactivated_at timestamptz;`
Nullable, **no** default, **no** backfill, **no** drop/cascade. Human-confirmed (XII).

**Derived (not stored) — effective significance (B):**
`effective_salience = salience × exp(-ln2 · age_days / DECAY_HALFLIFE_DAYS)`,
`age_days = (now − COALESCE(last_reactivated_at, created_at))`. Computed at read time;
`salience` itself is never mutated by decay (additive guarantee, VI).

---

## long_term_memory (Abstraction) — existing table, no change

| Field | Type | Used by | Role |
|---|---|---|---|
| `id` | uuid | C | abstraction identity |
| `content` | text | C | generalized text merged from a cluster |
| `embedding` | vector | C | abstraction embedding (for later retrieval/reuse) |
| `memory_type` | text | C | `'semantic'` |
| `domain` | text | C | inherited from cluster |
| `abstraction_level` | integer | C | ≥ 2 (above raw episodes) |
| `strength` | double precision | C | **accrues `+STRENGTH_PER_REPLAY` per replay hit** (was constant 0.5) |
| `reinforcement_count` | integer | C | **+1 per replay hit** — the competition counter |
| `last_reinforced_at` | timestamptz | C | stamped each replay hit |
| `decay_rate` | double precision | B | `0` for anchors (exempt); governs LTM-level decay |
| `source_memories` | uuid[] | C | **all** member episode ids of the merged cluster |
| `is_anchor` | boolean | B | anchored ground truth — never decays |

No columns added. The `strength`/`reinforcement_count`/`source_memories` columns existed but
were written with a constant 1→1 copy; C now uses them as intended.

---

## consolidation_runs — existing table

| Field | Used by | Role |
|---|---|---|
| `id`, `level`, `started_at`, `completed_at` | C | run bookkeeping (existing) |
| `memories_processed` | C | candidate episodes considered |
| `skills_created` | C | unchanged (0 here) |
| seed (logged in run note/level) | C | the replay RNG seed for reproducible audit |

> If a dedicated `seed`/`replay_budget` column is wanted for clean dashboarding it would be a
> *second* additive column — deferred unless tasks.md shows the run-note path is insufficient
> (keeps the migration to one column, XI).

---

## Settings (no schema; `fenrir/settings.py`)

| Setting | Default | Increment |
|---|---|---|
| `W_FAIL` | 0.2 | A |
| `W_UNVERIFIED` | 0.1 | A |
| `W_ESCALATED` | 1.5 | A |
| `W_CRYSTALLIZED` | 2.0 | A |
| `DECAY_HALFLIFE_DAYS` | 7.0 | B |
| `CLUSTER_SIM_FLOOR` | 0.85 | C |
| `REPLAY_BUDGET` | 64 | C |
| `STRENGTH_PER_REPLAY` | 0.1 | C |
| `COHERENCE_MAX_SPREAD` | 0.25 | C |
| `EFFECTIVE_SALIENCE_FLOOR` | 0.05 | C |

---

## Entity relationships

```
short_term_memory (raw, training pool)
   │  cluster by embedding cosine ≥ CLUSTER_SIM_FLOOR  (C)
   ▼
cluster (transient, in-pass)
   │  weighted-with-replacement replay × REPLAY_BUDGET  (C)
   │  per-cluster predictability gate + coherence guard (C, V)
   ▼
long_term_memory (one abstraction per cluster)
   strength += per replay hit; source_memories = all members
```

Decay (B) multiplies STM `salience` at read time wherever significance is consumed; anchors
(LTM `is_anchor`, `decay_rate=0`) are exempt. Bookmark (A) writes STM `salience` once from
`PE × value × (retrieval_count+1)`.

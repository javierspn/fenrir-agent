# Migrations

Versioned, append-only SQL applied by the in-house ordered applier
(`fenrir/db.py`, `python -m fenrir.db migrate`), tracked in `schema_migrations`
(research R1).

## The immutability rule (non-negotiable)

- **Never edit an applied migration file.** Once `NNNN_*.sql` has run anywhere, it
  is frozen — the applier records its version and never re-executes it, so an edit
  would silently diverge environments.
- **New structure ships only as a new, higher-numbered file** `NNNN_name.sql`
  (zero-padded 4 digits, lexical order = apply order).
- **Additive only** — no `DROP`/`DELETE` toward `short_term_memory`, no
  `ON DELETE CASCADE` to episodes (constitution VI / D1). Add columns/indexes/tables;
  migrate data forward; never destroy a source episode.
- Each file runs in **its own transaction**; a power cut mid-migration rolls back and
  the file re-applies cleanly on restart (D10).

## Files

- `0001_baseline_schema.sql` — the 14-table baseline (authoritative: `../../specs/001-infra-stack/data-model.md`).
- `0002_example_additive.sql` — sample additive migration (an index) demonstrating the pattern.

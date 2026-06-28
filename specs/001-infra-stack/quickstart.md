# Quickstart: 01-infra (bring-up & validation)

Run guide proving the feature works end-to-end. Implementation lives in `tasks.md` +
the source tree; this is the validation path.

## Prerequisites
- Docker + Docker Compose on the host.
- Ollama installed **natively** on the host, reachable at `OLLAMA_HOST`.
- `infra/.env` created from `infra/.env.example` with real values (never committed).

## Bring up
```bash
cd infra
cp .env.example .env          # then edit: DB_PASSWORD, GRAFANA_DB_RO_PASSWORD, GRAFANA_PASSWORD,
                              #            ANTHROPIC_API_KEY, OLLAMA_HOST, OWNER_TELEGRAM_CHAT_ID
docker compose up -d          # postgres, redis, grafana, (benchmark-loader one-shot)
docker compose ps             # expect all healthy
```

## Apply migrations + bootstrap
```bash
python -m fenrir.db migrate           # applies infra/migrations/*.sql in order
python -m fenrir.bootstrap            # idempotent: models, anchors, relations, benchmarks, marker
python -m fenrir.bootstrap            # run again → "already bootstrapped", zero changes
```

## Validate (maps to Success Criteria)
```bash
# SC-002: schema present (all tables + D1-D4 columns + salience index;
#         D5/D6: content_fts tsvector + GIN on both memory tables; skills.skill_kind + self_test)
pytest tests/integration/test_schema.py

# SC-003: bootstrap idempotent (row counts identical before/after 2nd run)
pytest tests/integration/test_idempotency.py

# SC-004: 50-100 anchors, all is_anchor at strength 1.0, decay leaves them untouched
pytest tests/integration/test_anchors.py

# SC-005: train/eval pools disjoint
pytest tests/integration/test_pools_disjoint.py

# SC-007: no schema path hard-deletes an episode (D1)
pytest tests/integration/test_no_episode_delete.py

# SC-011: required local models respond to a probe via OLLAMA_HOST
pytest tests/integration/test_models_available.py

# SC-012: grafana_ro role can SELECT but a write is rejected
pytest tests/integration/test_grafana_ro_readonly.py
```

## Power-loss recovery check (FR-002a)
```bash
# Simulate an unclean power-off: hard-kill the stack (no graceful shutdown), then bring it back.
docker compose kill            # SIGKILL — no clean flush, like a power cut
docker compose up -d           # restart: unless-stopped also auto-recovers on real reboot
python -m fenrir.db migrate    # no-op if already applied (idempotent after a torn run)
# Verify committed data intact + bootstrap marker present (SC-010):
pytest tests/integration/test_schema.py tests/integration/test_anchors.py

# SC-009: nightly backup artifact exists at a SEPARATE location and restores to identical counts
bash infra/backup/pg_backup.sh                       # writes to the separate backup target
ls -la "$BACKUP_DIR"/fenrir_*.sql                    # artifact present off the primary volume
# restore into a scratch DB and compare row counts:
psql "$SCRATCH_DB_URL" -f "$BACKUP_DIR"/fenrir_$(date +%F).sql
pytest tests/integration/test_backup_restore.py      # source vs restored counts match
```

## Manual spot checks
```bash
# anchors present + non-decaying
psql "$DB_URL" -c "SELECT count(*) FROM long_term_memory WHERE is_anchor AND decay_rate=0;"
# salience-ordered index exists
psql "$DB_URL" -c "\d short_term_memory" | grep salience
# Grafana reaches Postgres
open http://localhost:3000   # datasource = fenrir_core, status OK
# NO neo4j in the stack (D4)
docker compose ps | grep -i neo4j   # expect: no match
```

## Expected outcomes
- All services healthy on first `up` (SC-001); data survives `docker compose restart` (SC-006).
- Second bootstrap changes nothing (SC-003).
- Zero graph-DB services; zero episode-delete paths (SC-007).
- Missing env var → fast named failure (SC-008).

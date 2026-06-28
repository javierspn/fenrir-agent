# Contract: Configuration (`infra/.env.example`)

Fail-fast validation (`pydantic-settings`): every required var must be present and
non-empty at startup, else raise naming the variable (SC-008, FR-019/020).

| Variable | Purpose | Example (placeholder) |
|---|---|---|
| `DB_PASSWORD` | Password for the Postgres role that owns the `fenrir_core` database | `change-me` |
| `GRAFANA_DB_RO_PASSWORD` | Password for the read-only `grafana_ro` Postgres role (datasource; FR-004a) | `change-me` |
| `GRAFANA_PASSWORD` | Grafana admin (UI) password | `change-me` |
| `ANTHROPIC_API_KEY` | External API key (judge/fallback; captured day one, unused here) | `sk-ant-...` |
| `OLLAMA_HOST` | Native Ollama endpoint for model pulls | `http://host.docker.internal:11434` |
| `OWNER_TELEGRAM_CHAT_ID` | Owner notification whitelist id (interface out of scope) | `123456789` |

## Guarantees
- `.env.example` lists all six with **no real secret values**.
- Real `.env` is git-ignored (already covered by `.gitignore`).
- Missing/empty required var → fast, named failure 100% of the time; never an insecure
  default start.

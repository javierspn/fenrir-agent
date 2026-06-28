"""SC-008 — a missing required config value fails fast, naming the variable."""
from __future__ import annotations

import pytest
from pydantic import ValidationError


def test_missing_required_var_raises_naming_it(monkeypatch):
    for key in (
        "DB_PASSWORD", "GRAFANA_DB_RO_PASSWORD", "GRAFANA_PASSWORD",
        "ANTHROPIC_API_KEY", "OLLAMA_HOST", "OWNER_TELEGRAM_CHAT_ID",
    ):
        monkeypatch.setenv(key, "x")
    monkeypatch.delenv("DB_PASSWORD", raising=False)

    from fenrir.settings import Settings  # not via cached get_settings

    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    assert "DB_PASSWORD" in str(exc.value)

"""Unit-test fixtures (003). Pure-Python suites (no DB) still call get_settings()
via salience.value(); set the fail-fast required env so Settings validates, and clear
the lru_cache around each test so monkeypatched weights take effect."""
from __future__ import annotations

import pytest

_REQUIRED_ENV = {
    "DB_PASSWORD": "test-owner-pw",
    "GRAFANA_DB_RO_PASSWORD": "test-ro-pw",
    "GRAFANA_PASSWORD": "test-grafana-pw",
    "ANTHROPIC_API_KEY": "sk-ant-test",
    "OLLAMA_HOST": "http://localhost:11434",
    "OWNER_TELEGRAM_CHAT_ID": "0",
}


@pytest.fixture(autouse=True)
def unit_settings(monkeypatch):
    for key, val in _REQUIRED_ENV.items():
        monkeypatch.setenv(key, val)
    from fenrir.settings import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()

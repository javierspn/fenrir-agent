"""SC-011 / FR-013 — required local models respond via OLLAMA_HOST.

Needs a reachable Ollama with models pulled (set FENRIR_OLLAMA_UP=1).
"""
from __future__ import annotations

from fenrir.bootstrap.models import REQUIRED_MODELS, available_models
from tests.conftest import requires_ollama

pytestmark = requires_ollama


def test_required_models_present():
    import os

    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    present = available_models(host)
    missing = set(REQUIRED_MODELS) - present
    assert not missing, f"missing models: {missing}"

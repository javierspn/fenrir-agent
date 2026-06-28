"""Make the required local models available via Ollama (FR-013; research R8).

Pulls are idempotent — Ollama skips already-present models. On failure the caller
must NOT mark the system bootstrapped (the model/host is reported instead).
"""
from __future__ import annotations

import httpx

REQUIRED_MODELS = ("qwen2.5", "llama3.1", "nomic-embed-text")


def available_models(host: str, timeout: float = 10.0) -> set[str]:
    """Model names currently present in the Ollama instance (base name, no tag)."""
    resp = httpx.get(f"{host.rstrip('/')}/api/tags", timeout=timeout)
    resp.raise_for_status()
    names = set()
    for m in resp.json().get("models", []):
        name = m.get("name", "")
        names.add(name.split(":", 1)[0])
    return names


def ensure_models(
    host: str, models: tuple[str, ...] = REQUIRED_MODELS, timeout: float = 600.0
) -> None:
    """Pull each required model. Raises (naming model+host) if a pull fails."""
    for model in models:
        try:
            resp = httpx.post(
                f"{host.rstrip('/')}/api/pull",
                json={"name": model, "stream": False},
                timeout=timeout,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"failed to pull model {model!r} from {host}: {exc}") from exc


def all_present(host: str, models: tuple[str, ...] = REQUIRED_MODELS) -> bool:
    return set(models) <= available_models(host)

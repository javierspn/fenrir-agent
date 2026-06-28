"""Model routing: local Ollama vs frontier Anthropic (002, T009). Constitution VIII/X.

``model_class='small'`` → owned local solver (qwen2.5) via Ollama, cost 0.
``model_class='frontier'`` → teacher (claude-opus-4-8) via the Anthropic SDK,
adaptive thinking + effort=high (4.8 rejects budget_tokens / sampling params),
cost computed from usage × the configured per-1M rates.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from fenrir.settings import get_settings


@dataclass
class LLMResult:
    text: str
    model: str
    tokens: int
    cost_usd: float


def call_local(prompt: str, max_tokens: int = 1024) -> LLMResult:
    """Generate with the small owned model via Ollama. No cost (local)."""
    s = get_settings()
    resp = httpx.post(
        f"{s.OLLAMA_HOST}/api/generate",
        json={"model": s.SMALL_MODEL, "prompt": prompt, "stream": False,
              "options": {"num_predict": max_tokens}},
        timeout=120.0,
    )
    resp.raise_for_status()
    data = resp.json()
    tokens = int(data.get("eval_count", 0)) + int(data.get("prompt_eval_count", 0))
    return LLMResult(
        text=data.get("response", ""), model=s.SMALL_MODEL, tokens=tokens, cost_usd=0.0
    )


def call_frontier(prompt: str, max_tokens: int = 1024) -> LLMResult:
    """Escalate to the frontier teacher. Provider per TEACHER_PROVIDER (anthropic|deepseek)."""
    s = get_settings()
    return (_call_deepseek if s.TEACHER_PROVIDER == "deepseek" else _call_anthropic)(
        prompt, max_tokens
    )


def _cost(in_tok: int, out_tok: int) -> float:
    in_rate, out_rate = get_settings().teacher_rates_per_mtok
    return (in_tok / 1_000_000) * in_rate + (out_tok / 1_000_000) * out_rate


def _call_anthropic(prompt: str, max_tokens: int) -> LLMResult:
    import anthropic  # lazy: local-only runs don't need the SDK

    s = get_settings()
    client = anthropic.Anthropic(api_key=s.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=s.TEACHER_MODEL,
        max_tokens=max_tokens,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        messages=[{"role": "user", "content": prompt}],
    )
    text = next((b.text for b in msg.content if getattr(b, "type", None) == "text"), "")
    in_tok, out_tok = msg.usage.input_tokens, msg.usage.output_tokens
    return LLMResult(text, s.TEACHER_MODEL, in_tok + out_tok, _cost(in_tok, out_tok))


def _call_deepseek(prompt: str, max_tokens: int) -> LLMResult:
    """DeepSeek is OpenAI-compatible (chat/completions). Cheap, strong on math."""
    s = get_settings()
    resp = httpx.post(
        f"{s.DEEPSEEK_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {s.DEEPSEEK_API_KEY}"},
        json={"model": s.DEEPSEEK_MODEL, "max_tokens": max_tokens,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=180.0,
    )
    resp.raise_for_status()
    data = resp.json()
    text = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    in_tok = int(usage.get("prompt_tokens", 0))
    out_tok = int(usage.get("completion_tokens", 0))
    return LLMResult(text, s.DEEPSEEK_MODEL, in_tok + out_tok, _cost(in_tok, out_tok))

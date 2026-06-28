"""Internal budget-governed LLM proxy — fenrir:8080/llm (002, T010).

The single choke point for ALL model calls (Constitution X). Enforces the
semaphore (concurrency), the daily budget hard cap (Constitution IX, via
``budget.py``), and a per-call timeout. Nobody calls Ollama or Anthropic
directly. Contract: specs/002-cognitive-core/contracts/llm-proxy.contract.md
"""
from __future__ import annotations

import asyncio

from fastapi import FastAPI
from pydantic import BaseModel

from fenrir.db import connect
from fenrir.llm import budget, router
from fenrir.settings import get_settings

app = FastAPI(title="fenrir-llm-proxy")

_settings = get_settings()
_local_sema = asyncio.Semaphore(_settings.PROXY_LOCAL_SLOTS)
_frontier_sema = asyncio.Semaphore(_settings.PROXY_FRONTIER_SLOTS)
# rough projected frontier cost used by the pre-call budget gate (tunable)
_PROJECTED_FRONTIER_USD = 0.05


class LLMRequest(BaseModel):
    task_id: str
    role: str = "solver"
    model_class: str = "small"   # small | frontier
    prompt: str
    max_tokens: int = 1024


class LLMResponse(BaseModel):
    text: str = ""
    model: str | None = None
    tokens: int = 0
    cost_usd: float = 0.0
    escalated: bool = False
    refused: bool = False
    reason: str | None = None


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/llm", response_model=LLMResponse)
async def llm(req: LLMRequest) -> LLMResponse:
    frontier = req.model_class == "frontier"
    conn = connect()
    try:
        decision = budget.check(conn, _PROJECTED_FRONTIER_USD, frontier=frontier)
        if not decision.allowed:
            # budget exhausted → escalation suppressed, never silently exceeded (IX/SC-008)
            return LLMResponse(refused=True, reason=decision.reason)

        sema = _frontier_sema if frontier else _local_sema
        timeout = 120.0
        async with sema:
            fn = router.call_frontier if frontier else router.call_local
            result = await asyncio.wait_for(
                asyncio.to_thread(fn, req.prompt, req.max_tokens), timeout=timeout
            )
        budget.record(conn, result.cost_usd, escalated=frontier)
        return LLMResponse(
            text=result.text, model=result.model, tokens=result.tokens,
            cost_usd=result.cost_usd, escalated=frontier,
        )
    except asyncio.TimeoutError:
        return LLMResponse(refused=True, reason="timeout")
    finally:
        conn.close()

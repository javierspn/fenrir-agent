# Contract — Internal LLM Proxy (`fenrir:8080/llm`)

**Module**: `fenrir/llm/proxy.py` (FastAPI/uvicorn), `fenrir/llm/router.py`, `fenrir/llm/budget.py`
**Constitution**: IX (hard budget), X (sole network egress for sandboxes), VIII (separation).

## Why it exists
Every model call — local or frontier — goes through this one choke point. Nobody calls Ollama or the
Anthropic SDK directly. It enforces concurrency, per-task + daily budget, and timeout, and is the only
network endpoint a task sandbox may reach.

## Endpoint

`POST /llm`

```jsonc
// request
{
  "task_id": "uuid",            // for per-task budget accounting; required
  "role": "solver|teacher|crystallizer|consolidator",
  "model_class": "small|frontier",
  "prompt": "string",           // already-built prompt
  "max_tokens": 1024
}
// response (success)
{ "text": "string", "model": "qwen2.5|claude-opus-4-8", "tokens": 812, "cost_usd": 0.0, "escalated": false }
// response (budget refusal — NOT an error path the caller can bypass)
{ "refused": true, "reason": "daily_budget_exhausted", "model": null, "cost_usd": 0.0 }
```

## Routing (`router.py`)
- `model_class=small` → Ollama `SMALL_MODEL` (`qwen2.5`) via `OLLAMA_HOST`. Cost 0 (local).
- `model_class=frontier` → Anthropic `TEACHER_MODEL` (`claude-opus-4-8`):
  `client.messages.create(model="claude-opus-4-8", thinking={"type":"adaptive"},
  output_config={"effort":"high"}, max_tokens=…)`. No `budget_tokens`, no sampling params (4.8 rejects).
  Cost computed from `usage` × the model's per-1M rates ($5 in / $25 out for Opus 4.8).

## Budget enforcement (`budget.py`) — Constitution IX
- **Source of truth**: Postgres `budget_tracking` row for today (`daily_budget_usd` default 2.00).
- **Fast counter**: redis key (today's spend); rehydrated from Postgres on restart (D10 — a redis wipe
  loses zero durable budget state).
- **Pre-call gate**: if `model_class=frontier` and `spend_today + projected ≥ daily_budget_usd` →
  return `{refused:true, reason:"daily_budget_exhausted"}`. **Never** raise the cap silently.
- **Post-call**: increment redis counter, write `budget_tracking.llm_cost_usd += cost_usd`, bump
  `tasks_executed` / `concurrent_peak` / `rate_limit_hits` as applicable.

## Concurrency + timeout
- **Semaphore**: `PROXY_LOCAL_SLOTS` (default 2) for local; frontier capped lower. Excess calls queue.
- **Timeout**: per-call wall-clock; on timeout the call fails closed and is recorded, never hangs.

## Guarantees / tests
- A `frontier` call with the daily cap exhausted is **refused**, escalation suppressed, local solving
  continues or the task defers (SC-008, FR-012). `test_escalation_budget.py`.
- The cap is never exceeded across a run — asserted by summing `cost_usd` ≤ `daily_budget_usd`.
- The proxy is the only egress a sandbox can reach (Constitution X) — but verification/skill sandboxes
  use `--network none` and call nothing (see `sandbox.contract.md`).

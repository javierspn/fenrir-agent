# Contract — Network-Isolated Sandbox

**Module**: `fenrir/sandbox/runner.py`, `fenrir/sandbox/Dockerfile.sandbox`
**Constitution**: X (network isolation), VIII (separation of powers), II (verification).

## Why it exists
Untrusted code — the sympy verifier and any crystallized skill `self_test`/code — must run where it
cannot touch the host or the network. Arbitrary code execution + network is the primary blast radius.

## Mechanism
- **Ephemeral Docker container per execution**, started with **`--network none`**, spawned via the
  already-mounted `/var/run/docker.sock`. Removed after each run.
- **Image** (`Dockerfile.sandbox`): minimal `python:3.12-slim` + `sympy` only. No curl/wget/ssh, no
  network client libraries. Non-root user.
- **Limits**: CPU quota, memory cap, `SANDBOX_TIMEOUT` wall-clock (default 10 s). Read-only rootfs +
  a small tmpfs workdir.

## Interface
```python
run_in_sandbox(payload: SandboxJob) -> SandboxResult
# SandboxJob: { kind: "verify"|"skill_selftest"|"skill_apply", code: str, inputs: dict }
# SandboxResult: { ok: bool, stdout: str, stderr: str, return_code: int, timed_out: bool, verdict: ... }
```
- `kind=verify` → runs `sympy_oracle.py` logic on (candidate_answer, ground_truth) → symbolic-equivalence
  verdict (see `verifier.contract.md`). **No network needed.**
- `kind=skill_selftest` → runs a crystallized skill's `self_test`; pass/fail.
- `kind=skill_apply` → executes a verified skill against a new task input.

## Guarantees / tests
- **Fails closed on network**: any attempt to open a socket / resolve DNS inside the sandbox errors
  (no route) and the job is recorded as failed — never silently succeeds. `test_sandbox_isolation.py`.
- **No model calls inside the sandbox**: solving/escalation happen in the orchestrator via the proxy,
  not here — so the sandbox legitimately needs zero network (the strictest correct posture under X).
- **Independence**: the process that produces a verdict (sandbox) is separate from the process that
  proposed the answer (orchestrator/solver) — Constitution VIII, FR-014.
- **Bounded blast radius**: ephemeral + `--network none` + resource caps; one task's code cannot affect
  another or the host.

"""Ephemeral network-isolated sandbox (002, T011). Constitution X / VIII.

Each job runs in a throwaway Docker container started ``--network none`` with CPU/
memory/time limits, from the ``fenrir-sandbox`` image (python + sympy, no network
tooling). Verification and untrusted skill code execute here; model calls never do
(they go through the proxy from the orchestrator). The program is trusted code we
author; the candidate answer / skill input is passed as DATA via stdin (never eval'd
as code at the boundary). Contract: contracts/sandbox.contract.md
"""
from __future__ import annotations

import json
import subprocess  # nosec B404 — only ever invokes a fixed `docker run` for the isolated sandbox
from dataclasses import dataclass

from fenrir.settings import get_settings


@dataclass
class SandboxResult:
    ok: bool
    stdout: str
    stderr: str
    return_code: int
    timed_out: bool
    payload: dict | None = None   # parsed JSON the program printed on its last stdout line


def run(program: str, stdin_data: dict | None = None) -> SandboxResult:
    """Run ``python -c program`` in a fresh `--network none` container, feeding
    ``stdin_data`` as JSON on stdin. Returns the parsed last-line JSON if present."""
    s = get_settings()
    cmd = [
        "docker", "run", "--rm", "-i",
        "--network", "none",                 # Constitution X — fails closed on any egress
        "--cpus", "1", "--memory", "512m",
        "--read-only", "--tmpfs", "/work:rw,size=32m",
        "--security-opt", "no-new-privileges",
        s.SANDBOX_IMAGE,
        "python", "-c", program,
    ]
    try:
        proc = subprocess.run(  # nosec B603 — fixed docker argv; untrusted content is stdin DATA,
            cmd,                # isolated by --network none + read-only + no-new-privileges (X)
            input=json.dumps(stdin_data or {}),
            capture_output=True, text=True,
            timeout=s.SANDBOX_TIMEOUT,
        )
    except subprocess.TimeoutExpired as e:
        def _txt(v: bytes | str | None) -> str:
            return v.decode() if isinstance(v, bytes) else (v or "")
        return SandboxResult(False, _txt(e.stdout), _txt(e.stderr), -1, True, None)

    payload = None
    last = (proc.stdout or "").strip().splitlines()[-1:] or [""]
    try:
        payload = json.loads(last[0])
    except (json.JSONDecodeError, IndexError):
        payload = None
    return SandboxResult(
        ok=proc.returncode == 0,
        stdout=proc.stdout, stderr=proc.stderr,
        return_code=proc.returncode, timed_out=False, payload=payload,
    )

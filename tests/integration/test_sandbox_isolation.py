"""Foundational (T040): the sandbox runs `--network none` and fails closed on egress.
FR-011, Constitution X/VIII. Added post-/speckit-analyze (G1/X1).
"""
from __future__ import annotations

import os
import subprocess

import pytest

from fenrir.sandbox import runner


def test_runner_command_is_network_isolated(monkeypatch):
    """The docker invocation must hard-isolate the network and drop privileges."""
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd

        class R:
            returncode = 0
            stdout = '{"ok": true}'
            stderr = ""
        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner.run("print('hi')", {"x": 1})

    cmd = captured["cmd"]
    assert "--network" in cmd and cmd[cmd.index("--network") + 1] == "none"
    assert "--security-opt" in cmd and "no-new-privileges" in cmd
    assert "--read-only" in cmd


@pytest.mark.skipif(
    os.environ.get("FENRIR_SANDBOX_UP") != "1",
    reason="needs docker + the fenrir-sandbox image (set FENRIR_SANDBOX_UP=1)",
)
def test_network_attempt_fails_closed():
    """A real sandbox run that tries to open a socket must fail (no route)."""
    program = (
        "import json, socket\n"
        "ok = True\n"
        "try:\n"
        "    socket.create_connection(('1.1.1.1', 80), timeout=3); reached = True\n"
        "except OSError:\n"
        "    reached = False\n"
        "print(json.dumps({'reached_network': reached}))\n"
    )
    res = runner.run(program)
    # network must be unreachable inside --network none
    assert res.payload is not None and res.payload.get("reached_network") is False

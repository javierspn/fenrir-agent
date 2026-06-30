#!/usr/bin/env python3
"""Fenrir — contamination-safe problem generator (006, D13). STANDALONE / generation-host only.

A local open model (Qwen via LM Studio/Ollama) GENERATES problem prose + sympy ``solution_code``;
this host-side gate executes the code (restricted builtins + SIGALRM) and rejects anything unclean.
The model is NEVER trusted for the answer (II). The authoritative ground truth is re-derived in the
``--network none`` sandbox at LOAD time (``load_generated.py``); this gate is the fast first
a trusted off-node host (X1 carve-out; see specs/006 research R1).

Output: one accepted problem per JSONL line, INCLUDING ``solution_code`` so the loader can re-verify
(R8): ``{"question","answer","solution_code","family","n_steps","source":"qwen-gen"}``.

Usage (generation host, not the always-on node):
    python -m benchmark_loader.generate --backend lmstudio --model qwen2.5-14b-instruct \
        --per-family 200 --out problems.jsonl [--cross-check]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import sys
import time
import urllib.request
from pathlib import Path

import sympy
from sympy import nsimplify

from benchmark_loader.families import FAMILIES

DEFAULT_MODEL = {"lmstudio": "qwen2.5-14b-instruct", "ollama": "qwen2.5:14b"}

# Model-server base URLs — configurable so the generator runs on a bare host (localhost), inside a
# container (OLLAMA_HOST=http://host.docker.internal:11434), or a cloud GPU. Env overrides the
# localhost defaults; --ollama-url / --lmstudio-url override the env.
DEFAULT_OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_LMSTUDIO_URL = os.environ.get("LMSTUDIO_HOST", "http://localhost:1234")

SYSTEM = """You generate grade-school math word problems in the STRUCTURE of GSM8K \
(short arithmetic/algebra word problems), but with your own wording, names, and contexts.

Output STRICT JSON and nothing else. No markdown, no code fences, no text outside the JSON object.

Schema:
{
  "question": "<self-contained word problem, 2-4 sentences, a 10-year-old could follow>",
  "solution_code": "<Python using sympy that computes the result and assigns it to `answer`>",
  "answer_type": "integer" | "rational",
  "n_steps": <integer count of reasoning steps>
}

Hard rules:
- EVERY number in the question must appear as a literal in solution_code. No hidden constants.
- solution_code is deterministic: only sympy + basic Python. No randomness, no I/O, sympy only.
- Assign the final result to a variable named exactly `answer`.
- The answer MUST be a clean integer or rational. Never a decimal approximation, never irrational.
- NEVER state or hint the numeric answer anywhere in "question".
- The problem must be genuinely solvable and the solution_code must actually solve THIS problem."""

USER_TMPL = """Family (solution method): {fam_name} — {fam_desc}
Target difficulty: {n_steps} reasoning steps.
Generate ONE new problem of this family. Vary names, context, and numbers from any prior.
Remember: question must NOT contain the answer. Output only the JSON object."""


class _GateTimeout(Exception):  # noqa: N818
    pass


def _alarm(sig, frm):  # noqa: ANN001
    raise _GateTimeout()


def _strip_fences(raw: str) -> str:
    return re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()


def _execute(code: str) -> object | None:
    """Run solution_code under restricted builtins + a 5s SIGALRM. Returns `answer` or None.
    HOST-ONLY fast gate; the loader re-derives authoritatively in the --network none sandbox."""
    if any(bad in code for bad in ("import os", "import sys", "open(", "exec(", "eval(",
                                   "__", "subprocess", "socket", "input(")):
        return None
    def _safe_import(name, *a, **k):  # noqa: ANN001,ANN002,ANN003,ANN202
        # allow `import sympy [as sp]` only — matches the authoritative sandbox (which has full
        # sympy); everything else (os/sys/subprocess/…) stays blocked by the static guard above.
        if name == "sympy" or name.startswith("sympy."):
            return __import__(name, *a, **k)
        raise ImportError(name)

    ns: dict = {"__builtins__": {"range": range, "len": len, "sum": sum, "abs": abs,
                                 "min": min, "max": max, "int": int, "__import__": _safe_import}}
    for name in dir(sympy):
        if not name.startswith("_"):
            ns[name] = getattr(sympy, name)
    signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(5)
    try:
        # Deliberate restricted-builtins exec; HOST-ONLY fast gate on a trusted off-node
        # generation host (X1 carve-out). Untrusted model code is re-derived authoritatively in
        # the --network none sandbox at load time; nothing executed here is ever trusted.
        exec(code, ns)  # noqa: S102  # nosec B102
        return ns.get("answer")
    except Exception:
        return None
    finally:
        signal.alarm(0)


def _clean_rational(ans: object) -> str | None:
    try:
        r = nsimplify(ans, rational=True)
    except Exception:
        return None
    return str(r) if (r.is_Integer or r.is_Rational) else None


def validate(obj: dict) -> dict | None:
    """Parsed dict (+ injected _family) → clean record (with solution_code, R8) or None."""
    if not all(k in obj for k in ("question", "solution_code", "n_steps")):
        return None
    q, code = obj["question"], obj["solution_code"]
    if not isinstance(q, str) or not isinstance(code, str):
        return None
    q_nums = set(re.findall(r"\d+(?:\.\d+)?", q))
    code_nums = set(re.findall(r"\d+(?:\.\d+)?", code))
    if q_nums and not q_nums.issubset(code_nums):  # hidden constant
        return None
    ans = _execute(code)
    if ans is None:
        return None
    r = _clean_rational(ans)
    if r is None:  # decimal / irrational / non-numeric
        return None
    if r in re.findall(r"\d+", q):  # leaked answer
        return None
    return {
        "question": q, "answer": r, "solution_code": code,
        "family": obj.get("_family"), "n_steps": int(obj["n_steps"]), "source": "qwen-gen",
    }


def _post(url: str, payload: dict) -> dict:
    """POST JSON via stdlib urllib (no curl dependency — works in any container/host)."""
    # Fixed http(s) model-server base URL (not user input); no file:/custom scheme risk.
    req = urllib.request.Request(  # noqa: S310
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310  # nosec B310
        return json.loads(r.read().decode())


def _call_lmstudio(prompt: str, model: str, temperature: float, base_url: str) -> str:
    resp = _post(f"{base_url}/v1/chat/completions", {
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        "temperature": temperature, "top_p": 0.95, "max_tokens": 700,
        "response_format": {"type": "json_object"}})
    return resp["choices"][0]["message"]["content"]


def _call_ollama(prompt: str, model: str, temperature: float, base_url: str) -> str:
    resp = _post(f"{base_url}/api/generate", {
        "model": model, "system": SYSTEM, "prompt": prompt, "stream": False,
        "options": {"temperature": temperature, "top_p": 0.95, "num_predict": 700},
        "format": "json"})
    return resp.get("response", "")


BACKENDS = {"lmstudio": _call_lmstudio, "ollama": _call_ollama}


def ask_model(backend: str, fam_name: str, fam_desc: str, n_steps: int, model: str,
              base_url: str, temperature: float = 0.9) -> str:
    prompt = USER_TMPL.format(fam_name=fam_name, fam_desc=fam_desc, n_steps=n_steps)
    try:
        return BACKENDS[backend](prompt, model, temperature, base_url)
    except Exception:
        return ""


def _candidate(backend: str, name: str, desc: str, n_steps: int, model: str,
               base_url: str) -> dict | None:
    raw = ask_model(backend, name, desc, n_steps, model, base_url)
    if not raw:
        return None
    try:
        obj = json.loads(_strip_fences(raw))   # non-JSON/fenced tolerated; unparseable → skip (U3)
    except Exception:
        return None
    obj["_family"] = name
    return validate(obj)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="benchmark_loader.generate")
    ap.add_argument("--backend", choices=BACKENDS, default="lmstudio")
    ap.add_argument("--model", default=None)
    ap.add_argument("--per-family", type=int, default=200)
    ap.add_argument("--out", type=Path, default=Path("problems.jsonl"))
    ap.add_argument("--min-steps", type=int, default=2)
    ap.add_argument("--max-steps", type=int, default=5)
    ap.add_argument("--max-attempts-mult", type=int, default=4)
    ap.add_argument("--cross-check", action="store_true",
                    help="accept only if a 2nd independent solution agrees (R6; ~2x cost)")
    ap.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL,
                    help="Ollama base URL (env OLLAMA_HOST; default localhost:11434)")
    ap.add_argument("--lmstudio-url", default=DEFAULT_LMSTUDIO_URL,
                    help="LM Studio base URL (env LMSTUDIO_HOST; default localhost:1234)")
    args = ap.parse_args(argv)
    model = args.model or DEFAULT_MODEL[args.backend]
    base_url = args.ollama_url if args.backend == "ollama" else args.lmstudio_url

    targets = {n: args.per_family for n, _ in FAMILIES}
    accepted = {n: 0 for n, _ in FAMILIES}
    attempts = {n: 0 for n, _ in FAMILIES}
    seen: set[str] = set()
    cap = args.per_family * args.max_attempts_mult   # per-family attempt cap (U2)
    t0, n_written = time.time(), 0

    with args.out.open("w") as f:
        while any(accepted[n] < targets[n] and attempts[n] < cap for n, _ in FAMILIES):
            for name, desc in FAMILIES:
                if accepted[name] >= targets[name] or attempts[name] >= cap:
                    continue
                attempts[name] += 1
                n_steps = args.min_steps + (attempts[name] % (args.max_steps - args.min_steps + 1))
                prob = _candidate(args.backend, name, desc, n_steps, model, base_url)
                if prob is None:
                    continue
                if args.cross_check and not _cross_ok(
                        args.backend, name, desc, n_steps, model, base_url, prob):
                    continue
                key = re.sub(r"\s+", " ", prob["question"].lower()).strip()
                if key in seen:
                    continue
                seen.add(key)
                f.write(json.dumps(prob, ensure_ascii=False) + "\n")
                f.flush()
                accepted[name] += 1
                n_written += 1

    dt = time.time() - t0
    print(f"\nDone. {n_written} accepted in {dt / 60:.1f} min "
          f"({sum(attempts.values())} attempts).", file=sys.stderr)
    for name, _ in FAMILIES:   # per-family shortfall report (U2)
        flag = "" if accepted[name] >= targets[name] else "  ← SHORT"
        print(f"  {name:20s} {accepted[name]:4d}/{targets[name]} "
              f"({attempts[name]} attempts){flag}", file=sys.stderr)
    return 0


def _cross_ok(backend: str, name: str, desc: str, n_steps: int, model: str, base_url: str,
              prob: dict) -> bool:
    """Dual-solution cross-check (R6): a 2nd independent candidate must derive the same answer."""
    other = _candidate(backend, name, desc, n_steps, model, base_url)
    return other is not None and other["answer"] == prob["answer"]


if __name__ == "__main__":
    raise SystemExit(main())

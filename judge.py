"""judge.py — the fast judge: fixed questions about TEXT, answered with a
probability by a small local decision model (OpenJev, speaking TypeSafe's
Jev "system one" API).

This is NOT a verifier. Geometry is proven by the kernel and by `inspector`;
the judge only decides what to CHECK, ASK or STOP — "is a speaker opening
in this design?", never "is this body right?". A judge answer is a hint
with a probability, and the caller must stay correct without it:

    EVERY CALL FAILS OPEN. No server, a slow server, a malformed answer
    -> None, and the caller behaves exactly as it did before the judge
    existed.

Server: OpenJev (github.com/razorback16/openjev) with its Laya CPU backend
on 127.0.0.1:8080 — the laptop has no NVIDIA card, so the big backend is
out. Wire format (probed 2026-09-29, probes/openjev_laya.py):

    POST {URL}/v1/systemone
    {"state": "<text>", "model": "jev-latest",
     "questions": {"q1": {"type": "noul", "instructions": "<question>"}}}
    -> {"answers": {"q1": {"type": "noul", "noul": 0.93, ...}}}

Nothing here ever leaves the machine: the URL is loopback by default.
Env: TEXTCAD_JUDGE=0 switches it off; TEXTCAD_JUDGE_URL points elsewhere;
TEXTCAD_JUDGE_TIMEOUT (seconds) bounds one call.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

def _user_env(name: str) -> str | None:
    """An API key from the environment or the user registry — the same
    lookup studio._user_env does (copied: studio imports author imports
    this module, so it cannot be imported here). Never a file."""
    if os.environ.get(name):
        return os.environ[name]
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            return winreg.QueryValueEx(k, name)[0]
    except Exception:
        return None


# WHICH JUDGE. Measured 2026-09-29 (probes/openjev_laya.py): the free CPU
# models OpenJev can run on this laptop (Laya, Verdict) cannot tell a
# present element from an absent one on an 11-feature tree; the hosted Jev
# through OpenRouter separates them 0.94+ vs 0.20- in 0.3 s, for about
# 500 input tokens a call at $0.042 per million. So: OpenRouter when the
# key TextCAD's design model already uses is there (the same service
# already sees the whole tree on every chat message — no new exposure),
# else a local server. TEXTCAD_JUDGE_URL overrides either way.
OPENROUTER = "https://openrouter.ai/api"
LOCAL = "http://127.0.0.1:8080"
URL = (os.environ.get("TEXTCAD_JUDGE_URL")
       or (OPENROUTER if _user_env("OPENROUTER_API_KEY") else LOCAL)).rstrip("/")
ENABLED = os.environ.get("TEXTCAD_JUDGE", "1").strip().lower() not in (
    "0", "", "off", "no", "false")
# The hosted Jev speaks the same wire format behind a bearer token.
# TEXTCAD_JUDGE_KEY names a key for any other server.
KEY = _user_env("TEXTCAD_JUDGE_KEY") or (
    _user_env("OPENROUTER_API_KEY") if "openrouter.ai" in URL else None)
# Laya on this laptop's CPU answers about 0.8 s per question in a batch
# (measured 2026-09-29: 8 questions in 6.5-7.2 s); a checklist is asked
# once or twice per job, at "done", so a long bound costs nothing.
TIMEOUT_S = float(os.environ.get("TEXTCAD_JUDGE_TIMEOUT", "45"))
MODEL = "jev-latest"

# Laya reads at most 1,024 tokens of state + question + options. A state past
# this many characters is cut by the CALLER (it knows what matters); the
# judge only refuses to send something the model would truncate blindly.
STATE_CHARS = 2400

# After a failed call the judge stays quiet for this long, so a 40-step job
# does not pay one timeout per step when the server is down.
_QUIET_S = 30.0
_quiet_until = 0.0


def _post(body: dict) -> dict:
    """One HTTP round trip. Raised errors are the caller's to swallow."""
    headers = {"Content-Type": "application/json"}
    if KEY:
        headers["Authorization"] = f"Bearer {KEY}"
    req = urllib.request.Request(
        URL + "/v1/systemone", data=json.dumps(body).encode("utf-8"),
        headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ask(state: str, questions: dict[str, dict]) -> dict[str, dict] | None:
    """Answers keyed like `questions`, or None when the judge cannot answer.

    `questions` are Jev question objects ({"type": "noul"|"choice"|"score",
    "instructions": ..., "criteria": ...}). Never raises."""
    global _quiet_until
    if not ENABLED or not questions or time.monotonic() < _quiet_until:
        return None
    if len(state) > STATE_CHARS:
        state = state[:STATE_CHARS]
    try:
        out = _post({"state": state, "model": MODEL, "questions": questions})
        answers = out.get("answers") if isinstance(out, dict) else None
        if not isinstance(answers, dict):
            return None
        return {k: answers[k] for k in questions if isinstance(answers.get(k), dict)}
    except (urllib.error.URLError, OSError, ValueError, TypeError, KeyError):
        _quiet_until = time.monotonic() + _QUIET_S
        return None


def yes_no(state: str, questions: dict[str, str]) -> dict[str, float] | None:
    """{name: probability of YES} for plain yes/no questions, or None.

    A question whose answer came back malformed is left out, so a caller
    iterating the result only ever sees real probabilities."""
    got = ask(state, {k: {"type": "noul", "instructions": q}
                      for k, q in questions.items()})
    if got is None:
        return None
    out = {}
    for k, a in got.items():
        p = a.get("noul")
        if isinstance(p, (int, float)) and 0.0 <= p <= 1.0:
            out[k] = float(p)
    return out


def alive() -> bool:
    """True when the server answers its health check right now."""
    if not ENABLED:
        return False
    try:
        with urllib.request.urlopen(URL + "/health", timeout=2) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False
